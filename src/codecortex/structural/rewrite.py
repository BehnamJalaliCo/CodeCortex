"""Guarded structural rewrites: search, preview, authorize, apply, verify.

A rewrite is never one opaque destructive call. A preview is produced first and
persisted with the SHA-256 of every file it was computed from. ``apply`` refuses
to run against a preview that has expired, that exceeds the configured limits,
or whose files changed after the preview was taken. Files are replaced
atomically and restored from the recorded originals if any write fails.
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codecortex.config import CortexConfig
from codecortex.core.models import AgentRequest
from codecortex.engines.builtin.validation import ValidationEngine
from codecortex.indexing.impact import ImpactAnalyzer
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.state import AtomicJsonFile
from codecortex.structural.models import (
    RewriteFileOutcome,
    RewriteFilePreview,
    RewritePreview,
    RewriteRejected,
    RewriteResult,
    StructuralError,
    StructuralMatch,
)
from codecortex.structural.search import StructuralSearch, contain_path

#: Number of unified-diff context lines kept in a preview.
DIFF_CONTEXT_LINES = 2

#: Cap on diff text stored per file so a preview stays small enough to review.
MAX_DIFF_CHARS = 20_000


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class _PlannedFile:
    path: str
    original: bytes
    updated: bytes
    matches: int
    digest: str


class RewriteStore:
    """Persist preview plans, including the original bytes needed for rollback."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, preview_id: str) -> Path:
        if not preview_id or any(char in preview_id for char in "/\\.") or len(preview_id) > 64:
            raise RewriteRejected(f"invalid preview id: {preview_id!r}")
        return self.directory / f"{preview_id}.json"

    def save(self, preview: RewritePreview, planned: list[_PlannedFile]) -> None:
        payload = {
            "preview": preview.model_dump(mode="json"),
            "files": [
                {
                    "path": item.path,
                    "digest": item.digest,
                    "matches": item.matches,
                    "original": item.original.decode("utf-8", errors="surrogateescape"),
                    "updated": item.updated.decode("utf-8", errors="surrogateescape"),
                }
                for item in planned
            ],
        }
        state = AtomicJsonFile(self._path(preview.preview_id))
        state.write(payload)
        if os.name != "nt":
            try:
                state.path.chmod(0o600)
            except OSError:  # pragma: no cover - platform specific
                pass

    def load(self, preview_id: str) -> tuple[RewritePreview, list[_PlannedFile]]:
        payload = AtomicJsonFile(self._path(preview_id)).read(None)
        if not isinstance(payload, dict) or "preview" not in payload:
            raise RewriteRejected(f"unknown rewrite preview: {preview_id}")
        try:
            preview = RewritePreview.model_validate(payload["preview"])
        except ValueError as exc:
            raise RewriteRejected(f"corrupt rewrite preview: {preview_id}") from exc
        planned = [
            _PlannedFile(
                path=str(item["path"]),
                original=str(item["original"]).encode("utf-8", errors="surrogateescape"),
                updated=str(item["updated"]).encode("utf-8", errors="surrogateescape"),
                matches=int(item["matches"]),
                digest=str(item["digest"]),
            )
            for item in payload.get("files", [])
            if isinstance(item, dict)
        ]
        return preview, planned

    def discard(self, preview_id: str) -> None:
        try:
            self._path(preview_id).unlink()
        except OSError:
            pass


class StructuralRewriteService:
    """Produce and apply reviewable structural migrations."""

    def __init__(
        self,
        root: Path,
        config: CortexConfig | None = None,
        search: StructuralSearch | None = None,
    ) -> None:
        self.root = root.resolve()
        self.config = config or CortexConfig.load(self.root)
        self.settings = self.config.structural
        self.search = search or StructuralSearch(self.root, self.config)
        self.store = RewriteStore(self.config.runtime_dir / "rewrites")

    # -- preview ------------------------------------------------------------

    def preview(
        self,
        pattern: str,
        replacement: str,
        language: str,
        *,
        include: tuple[str, ...] = (),
        exclude: tuple[str, ...] = (),
        paths: tuple[str, ...] = (),
    ) -> RewritePreview:
        """Plan a rewrite without touching any source file."""
        if not replacement.strip():
            raise StructuralError("structural rewrite requires a replacement")
        matches = self.search.search(
            pattern,
            language,
            rewrite=replacement,
            include=include,
            exclude=exclude,
            paths=paths,
        )
        if not matches:
            raise RewriteRejected("structural pattern matched nothing; nothing to preview")
        self._enforce_limits(matches)
        planned, warnings = self._plan(matches)
        if not planned:
            raise RewriteRejected("no file could be rewritten from the matched pattern")
        total_bytes = sum(
            abs(len(item.updated) - len(item.original)) + item.matches for item in planned
        )
        if total_bytes > self.settings.max_rewrite_bytes:
            raise RewriteRejected(
                f"rewrite would change {total_bytes} bytes, above the configured limit of "
                f"{self.settings.max_rewrite_bytes}"
            )
        symbols, tests, risk = self._impact([item.path for item in planned])
        created, expires = RewritePreview.expiry(self.settings.preview_ttl_seconds)
        preview = RewritePreview(
            preview_id=uuid.uuid4().hex,
            pattern=pattern,
            replacement=replacement,
            language=language,
            files=[
                RewriteFilePreview(
                    path=item.path,
                    matches=item.matches,
                    original_sha256=item.digest,
                    changed_bytes=abs(len(item.updated) - len(item.original)) + item.matches,
                    diff=self._diff(item),
                )
                for item in planned
            ],
            total_matches=sum(item.matches for item in planned),
            total_changed_bytes=total_bytes,
            risk_score=risk,
            affected_symbols=symbols,
            affected_tests=tests,
            created_at=created,
            expires_at=expires,
            warnings=warnings,
        )
        self.store.save(preview, planned)
        return preview

    def _enforce_limits(self, matches: list[StructuralMatch]) -> None:
        files = {match.path for match in matches}
        if len(files) > self.settings.max_rewrite_files:
            raise RewriteRejected(
                f"rewrite spans {len(files)} files, above the configured limit of "
                f"{self.settings.max_rewrite_files}"
            )
        if len(matches) > self.settings.max_rewrite_matches:
            raise RewriteRejected(
                f"rewrite has {len(matches)} matches, above the configured limit of "
                f"{self.settings.max_rewrite_matches}"
            )

    def _plan(self, matches: list[StructuralMatch]) -> tuple[list[_PlannedFile], list[str]]:
        """Apply replacements to in-memory copies, newest offset first."""
        grouped: dict[str, list[StructuralMatch]] = {}
        warnings: list[str] = []
        for match in matches:
            if match.replacement is None:
                warnings.append(f"{match.path}:{match.start_line}: engine produced no replacement")
                continue
            grouped.setdefault(match.path, []).append(match)
        planned: list[_PlannedFile] = []
        for relative, items in sorted(grouped.items()):
            target = contain_path(self.root, relative)
            try:
                original = target.read_bytes()
            except OSError as exc:
                warnings.append(f"{relative}: unreadable ({exc.strerror or exc})")
                continue
            updated = original
            for match in sorted(items, key=lambda item: item.byte_start, reverse=True):
                if match.byte_end > len(updated) or match.byte_start > match.byte_end:
                    warnings.append(f"{relative}:{match.start_line}: stale match offset skipped")
                    continue
                replacement = (match.replacement or "").encode("utf-8")
                updated = updated[: match.byte_start] + replacement + updated[match.byte_end :]
            if updated == original:
                warnings.append(f"{relative}: replacement produced no change")
                continue
            planned.append(
                _PlannedFile(
                    path=relative,
                    original=original,
                    updated=updated,
                    matches=len(items),
                    digest=hashlib.sha256(original).hexdigest(),
                )
            )
        return planned, warnings

    @staticmethod
    def _diff(item: _PlannedFile) -> str:
        diff = difflib.unified_diff(
            item.original.decode("utf-8", errors="replace").splitlines(keepends=True),
            item.updated.decode("utf-8", errors="replace").splitlines(keepends=True),
            fromfile=f"a/{item.path}",
            tofile=f"b/{item.path}",
            n=DIFF_CONTEXT_LINES,
        )
        return "".join(diff)[:MAX_DIFF_CHARS]

    def _impact(self, paths: list[str]) -> tuple[list[str], list[str], float]:
        """Estimate blast radius using the existing project graph."""
        try:
            graph = IncrementalGraphIndex(self.root).refresh()[0]
        except (OSError, ValueError):  # pragma: no cover - defensive
            return [], [], 0.0
        analyzer = ImpactAnalyzer(graph)
        symbols: list[str] = []
        tests: set[str] = set()
        risks: list[float] = []
        for relative in paths:
            for node in graph.nodes_for_path(relative):
                if node.kind in {"file", "module", "reference"}:
                    continue
                symbols.append(node.name)
                try:
                    report = analyzer.analyze(node.name)
                except ValueError:
                    continue
                risks.append(report.risk_score)
                tests.update(item.node.path or item.node.name for item in report.affected_tests)
        breadth = min(1.0, len(paths) / max(1, self.settings.max_rewrite_files))
        depth = max(risks) if risks else 0.0
        return (
            sorted(set(symbols))[:50],
            sorted(tests)[:50],
            round(min(1.0, 0.6 * depth + 0.4 * breadth), 4),
        )

    # -- apply --------------------------------------------------------------

    async def apply(self, preview_id: str, *, authorized: bool = True) -> RewriteResult:
        """Apply a previously reviewed preview, verifying nothing moved underneath it."""
        if not authorized:
            raise RewriteRejected("structural rewrite was not authorized by policy")
        if not self.settings.allow_apply:
            raise RewriteRejected("structural rewrite application is disabled in configuration")
        preview, planned = self.store.load(preview_id)
        if preview.expired:
            raise RewriteRejected(
                f"rewrite preview {preview_id} expired at {preview.expires_at.isoformat()}"
            )
        self._verify_unchanged(planned)

        written: list[tuple[Path, bytes]] = []
        outcomes: list[RewriteFileOutcome] = []
        try:
            for item in planned:
                target = contain_path(self.root, item.path)
                written.append((target, item.original))
                self._atomic_write(target, item.updated)
                outcomes.append(
                    RewriteFileOutcome(path=item.path, applied=True, matches=item.matches)
                )
        except OSError as exc:
            restored = self._rollback(written)
            return RewriteResult(
                preview_id=preview_id,
                applied=False,
                files=[
                    *outcomes,
                    RewriteFileOutcome(
                        path=item.path, applied=False, reason=str(exc.strerror or exc)
                    ),
                ],
                rolled_back=restored,
                detail=f"rewrite failed and {'was rolled back' if restored else 'could not be fully rolled back'}: {exc}",
            )

        reindexed = self._reindex()
        validation = await self._validate()
        post_impact = self._post_impact([item.path for item in planned])
        self.store.discard(preview_id)
        return RewriteResult(
            preview_id=preview_id,
            applied=True,
            files=outcomes,
            files_changed=len(planned),
            matches_applied=sum(item.matches for item in planned),
            reindexed_files=reindexed,
            validation=validation,
            post_impact=post_impact,
            detail=f"applied at {datetime.now(UTC).isoformat()}",
        )

    def _verify_unchanged(self, planned: list[_PlannedFile]) -> None:
        """Refuse to overwrite a file that changed after the preview was taken."""
        for item in planned:
            target = contain_path(self.root, item.path)
            if not target.is_file():
                raise RewriteRejected(f"file disappeared after the preview: {item.path}")
            if sha256_file(target) != item.digest:
                raise RewriteRejected(
                    f"file changed after the preview was taken: {item.path}; regenerate the preview"
                )

    @staticmethod
    def _atomic_write(target: Path, payload: bytes) -> None:
        handle, raw = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
        )
        temporary = Path(raw)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass

    @staticmethod
    def _rollback(written: list[tuple[Path, bytes]]) -> bool:
        restored = True
        for target, original in written:
            try:
                target.write_bytes(original)
            except OSError:  # pragma: no cover - filesystem failure during recovery
                restored = False
        return restored

    def _reindex(self) -> int:
        try:
            _, stats = IncrementalGraphIndex(self.root).refresh()
        except (OSError, ValueError):  # pragma: no cover - defensive
            return 0
        return stats.files_reparsed

    async def _validate(self) -> dict[str, object]:
        engine = ValidationEngine(self.root)
        result = await engine.execute(
            AgentRequest(query="validate structural rewrite", project_root=str(self.root))
        )
        issues = int(result.metadata.get("issues", 0))
        return {
            "passed": issues == 0,
            "issues": issues,
            "checked": int(result.metadata.get("checked", 0)),
            "detail": result.content[:2_000],
        }

    def _post_impact(self, paths: list[str]) -> dict[str, object]:
        symbols, tests, risk = self._impact(paths)
        return {
            "affected_symbols": symbols,
            "affected_tests": tests,
            "residual_risk": risk,
        }

    def apply_sync(self, preview_id: str, *, authorized: bool = True) -> RewriteResult:
        """Synchronous wrapper for CLI callers."""
        return asyncio.run(self.apply(preview_id, authorized=authorized))

    def load_preview(self, preview_id: str) -> RewritePreview:
        return self.store.load(preview_id)[0]

    def preview_payload(self, preview: RewritePreview) -> dict[str, Any]:
        """Return the preview as plain JSON types, ready for CLI or MCP output."""
        payload: dict[str, Any] = json.loads(preview.model_dump_json())
        return payload
