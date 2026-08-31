"""Persistent incremental repository index."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_EXCLUDED = {
    ".git",
    ".codecortex",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
}


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
    """Track repository files by content hash and persist the result locally."""

    VERSION = 1

    def __init__(
        self,
        root: Path,
        state_path: Path | None = None,
        max_file_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        self.root = root.resolve()
        self.state_path = state_path or self.root / ".codecortex" / "index" / "manifest.json"
        self.max_file_bytes = max_file_bytes

    def _iter_files(self) -> list[Path]:
        files: list[Path] = []
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(self.root)
            if any(part in _EXCLUDED for part in relative.parts):
                continue
            try:
                if path.stat().st_size > self.max_file_bytes:
                    continue
            except OSError:
                continue
            files.append(path)
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
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if payload.get("version") != self.VERSION:
            return {}
        result: dict[str, FileState] = {}
        for name, value in payload.get("files", {}).items():
            try:
                result[name] = FileState(
                    digest=str(value["digest"]),
                    size=int(value["size"]),
                    mtime_ns=int(value["mtime_ns"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
        return result

    def _save(self, files: dict[str, FileState]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "version": self.VERSION,
            "root": str(self.root),
            "files": {name: asdict(state) for name, state in sorted(files.items())},
        }
        temp_path = self.state_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp_path, self.state_path)

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
                    digest=self._digest(path),
                    size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
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
