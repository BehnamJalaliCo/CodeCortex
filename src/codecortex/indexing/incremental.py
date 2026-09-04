"""Persistent incremental repository index."""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from codecortex.indexing.discovery import EXCLUDED_PARTS, iter_repository_files
from codecortex.state import AtomicJsonFile

_EXCLUDED = EXCLUDED_PARTS


@dataclass(frozen=True, slots=True)
class FileState:
    digest: str
    size: int
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class IndexStats:
    tracked: int
    added: tuple[str, ...]
    changed: tuple[str, ...]
    removed: tuple[str, ...]
    unchanged: int
    duration_ms: float

    @property
    def dirty(self) -> bool:
        return bool(self.added or self.changed or self.removed)


class IncrementalIndex:
    VERSION = 1

    def __init__(
        self, root: Path, state_path: Path | None = None, max_file_bytes: int = 4 * 1024 * 1024
    ) -> None:
        self.root = root.resolve()
        self.state_path = state_path or self.root / ".codecortex" / "index" / "manifest.json"
        self.max_file_bytes = max_file_bytes

    def _iter_files(self) -> list[Path]:
        files = iter_repository_files(self.root, max_bytes=self.max_file_bytes)
        files.sort(key=lambda item: item.relative_to(self.root).as_posix())
        return files

    @staticmethod
    def _digest(path: Path) -> str:
        hasher = hashlib.blake2b(digest_size=20)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _load(self) -> dict[str, FileState]:
        payload = AtomicJsonFile(self.state_path).read({})
        if not isinstance(payload, dict) or payload.get("version") != self.VERSION:
            return {}
        result: dict[str, FileState] = {}
        raw_files = payload.get("files", {})
        if not isinstance(raw_files, dict):
            return result
        for name, value in raw_files.items():
            if not isinstance(value, dict):
                continue
            try:
                result[str(name)] = FileState(
                    digest=str(value["digest"]),
                    size=int(value["size"]),
                    mtime_ns=int(value["mtime_ns"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
        return result

    def _save(self, files: dict[str, FileState]) -> None:
        payload: dict[str, Any] = {
            "version": self.VERSION,
            "root": str(self.root),
            "files": {name: asdict(state) for name, state in sorted(files.items())},
        }
        AtomicJsonFile(self.state_path).write(payload)

    def refresh(self) -> IndexStats:
        started = time.perf_counter()
        previous = self._load()
        current: dict[str, FileState] = {}
        added: list[str] = []
        changed: list[str] = []
        unchanged = 0
        for path in self._iter_files():
            relative = path.relative_to(self.root).as_posix()
            try:
                stat = path.stat()
            except OSError:
                continue
            old = previous.get(relative)
            if old and old.size == stat.st_size and old.mtime_ns == stat.st_mtime_ns:
                current[relative] = old
                unchanged += 1
                continue
            try:
                state = FileState(
                    digest=self._digest(path), size=stat.st_size, mtime_ns=stat.st_mtime_ns
                )
            except OSError:
                continue
            current[relative] = state
            if old is None:
                added.append(relative)
            elif old.digest != state.digest:
                changed.append(relative)
            else:
                unchanged += 1
        removed = sorted(set(previous) - set(current))
        self._save(current)
        return IndexStats(
            tracked=len(current),
            added=tuple(added),
            changed=tuple(changed),
            removed=tuple(removed),
            unchanged=unchanged,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
