"""Discovery, caching, and freshness tracking for the precision index."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from codecortex.config import CortexConfig, PrecisionIndexConfig
from codecortex.precision.importer import import_index
from codecortex.precision.models import PrecisionIndex, PrecisionIndexError

#: Locations searched when no explicit path is configured, in priority order.
DEFAULT_INDEX_LOCATIONS: tuple[str, ...] = (
    ".codecortex/precision/index.scip",
    "index.scip",
    ".scip/index.scip",
    "build/index.scip",
)

#: How many indexed documents are sampled for freshness checks. Full scans of a
#: very large index would dominate the cost of an otherwise cheap MCP call.
FRESHNESS_SAMPLE_SIZE = 400


@dataclass(frozen=True, slots=True)
class PrecisionStatus:
    """Capability report for the precision layer, safe to show to agents."""

    configured: bool
    available: bool
    path: str | None = None
    stale: bool = False
    stale_reason: str = ""
    detail: str = ""
    documents: int = 0
    symbols: int = 0
    occurrences: int = 0
    tool: str = ""
    generator_configured: bool = False

    @property
    def label(self) -> str:
        if not self.configured:
            return "disabled"
        if not self.available:
            return "unavailable"
        return "stale" if self.stale else "available"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.label,
            "configured": self.configured,
            "available": self.available,
            "path": self.path,
            "stale": self.stale,
            "stale_reason": self.stale_reason,
            "detail": self.detail,
            "documents": self.documents,
            "symbols": self.symbols,
            "occurrences": self.occurrences,
            "indexer": self.tool,
            "generator_configured": self.generator_configured,
        }


@dataclass(slots=True)
class _CacheEntry:
    fingerprint: tuple[int, int]
    index: PrecisionIndex


@dataclass(slots=True)
class PrecisionIndexStore:
    """Load a precision index at most once per (path, size, mtime) fingerprint."""

    root: Path
    config: PrecisionIndexConfig = field(default_factory=PrecisionIndexConfig)
    _cache: dict[str, _CacheEntry] = field(default_factory=dict, repr=False)
    _last_error: str = field(default="", repr=False)

    @classmethod
    def from_config(cls, config: CortexConfig) -> PrecisionIndexStore:
        return cls(root=config.project_root, config=config.precision_index)

    def candidate_paths(self) -> tuple[Path, ...]:
        if self.config.path:
            return (self._resolve(self.config.path),)
        return tuple(self._resolve(item) for item in DEFAULT_INDEX_LOCATIONS)

    def _resolve(self, value: str) -> Path:
        candidate = Path(value)
        return candidate if candidate.is_absolute() else self.root / candidate

    def locate(self) -> Path | None:
        """Return the first readable index file among the candidate locations."""
        for candidate in self.candidate_paths():
            try:
                if candidate.is_file():
                    return candidate
            except OSError:  # pragma: no cover - platform specific stat failure
                continue
        return None

    def load(self) -> PrecisionIndex | None:
        """Return the imported index, or None when it is missing or unusable."""
        self._last_error = ""
        if not self.config.enabled:
            self._last_error = "precision intelligence is disabled in configuration"
            return None
        path = self.locate()
        if path is None:
            self._last_error = "no precision index found"
            return None
        try:
            stat = path.stat()
        except OSError as exc:
            self._last_error = f"precision index is unreadable: {exc.strerror or exc}"
            return None
        if stat.st_size > self.config.max_index_bytes:
            self._last_error = (
                f"precision index exceeds the configured limit of "
                f"{self.config.max_index_bytes} bytes"
            )
            return None
        key = str(path)
        fingerprint = (stat.st_size, stat.st_mtime_ns)
        cached = self._cache.get(key)
        if cached is not None and cached.fingerprint == fingerprint:
            return cached.index
        try:
            payload = path.read_bytes()
        except OSError as exc:
            self._last_error = f"precision index is unreadable: {exc.strerror or exc}"
            return None
        try:
            index = import_index(payload)
        except PrecisionIndexError as exc:
            self._last_error = str(exc)
            return None
        self._cache[key] = _CacheEntry(fingerprint=fingerprint, index=index)
        return index

    def freshness(self, index: PrecisionIndex, index_path: Path) -> tuple[bool, str]:
        """Return ``(stale, reason)`` by comparing the index against the worktree.

        An index that predates a source edit reports positions that no longer
        exist, so it must never be presented as exact.
        """
        try:
            index_mtime = index_path.stat().st_mtime_ns
        except OSError:  # pragma: no cover - the file was just read successfully
            return True, "precision index disappeared while it was being used"
        missing: list[str] = []
        newer: list[str] = []
        for relative in index.paths()[:FRESHNESS_SAMPLE_SIZE]:
            source = self.root / relative
            try:
                source_mtime = source.stat().st_mtime_ns
            except OSError:
                missing.append(relative)
                if len(missing) >= 3:
                    break
                continue
            if source_mtime > index_mtime:
                newer.append(relative)
                if len(newer) >= 3:
                    break
        if newer:
            return True, f"source changed after indexing: {', '.join(sorted(newer))}"
        if missing:
            return True, f"indexed files are missing: {', '.join(sorted(missing))}"
        return False, ""

    def status(self) -> PrecisionStatus:
        """Report capability state without mutating the repository."""
        generator = bool(self.config.generator_command)
        if not self.config.enabled:
            return PrecisionStatus(
                configured=False,
                available=False,
                detail="precision intelligence is disabled in configuration",
                generator_configured=generator,
            )
        path = self.locate()
        index = self.load()
        if index is None:
            return PrecisionStatus(
                configured=True,
                available=False,
                path=str(path) if path else None,
                detail=self._last_error or "no precision index found",
                generator_configured=generator,
            )
        assert path is not None  # load() only succeeds when locate() found a file
        stale, reason = self.freshness(index, path)
        return PrecisionStatus(
            configured=True,
            available=True,
            path=str(path),
            stale=stale,
            stale_reason=reason,
            detail="" if not stale else "reindex to restore exact navigation",
            documents=index.document_count,
            symbols=index.symbol_count,
            occurrences=index.occurrence_count,
            tool=" ".join(part for part in (index.tool_name, index.tool_version) if part),
            generator_configured=generator,
        )

    def relative_path(self, value: str) -> str:
        """Normalize a caller-supplied path to a repository-relative POSIX path.

        Raises:
            ValueError: when the path escapes the project root.
        """
        candidate = Path(value)
        resolved = (candidate if candidate.is_absolute() else self.root / candidate).resolve()
        root = self.root.resolve()
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError("precision queries must stay inside the project root") from exc

    def invalidate(self) -> None:
        """Drop cached index state, forcing the next load to re-read from disk."""
        self._cache.clear()


def default_index_path(root: Path) -> Path:
    return root / DEFAULT_INDEX_LOCATIONS[0].replace("/", os.sep)
