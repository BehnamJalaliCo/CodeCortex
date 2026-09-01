"""Crash-safe and process-safe local JSON state primitives."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


class FileMutex:
    """Portable inter-process mutex implemented with an atomic lock directory."""

    def __init__(
        self,
        path: Path,
        *,
        timeout_seconds: float = 10.0,
        stale_seconds: float = 300.0,
    ) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.stale_seconds = stale_seconds
        self._held = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                self.path.mkdir()
                marker = self.path / "owner.json"
                marker.write_text(
                    json.dumps({"pid": os.getpid(), "created": time.time()}),
                    encoding="utf-8",
                )
                self._held = True
                return
            except FileExistsError:
                self._break_stale_lock()
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out waiting for state lock: {self.path}") from None
                time.sleep(0.05)

    def _break_stale_lock(self) -> None:
        try:
            age = time.time() - self.path.stat().st_mtime
        except OSError:
            return
        if age <= self.stale_seconds:
            return
        shutil.rmtree(self.path, ignore_errors=True)

    def release(self) -> None:
        if not self._held:
            return
        shutil.rmtree(self.path, ignore_errors=True)
        self._held = False

    def __enter__(self) -> FileMutex:
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb
        self.release()


class AtomicJsonFile:
    """Serialize JSON state updates with a mutex and atomic replace."""

    def __init__(self, path: Path, *, timeout_seconds: float = 10.0) -> None:
        self.path = path
        self.mutex = FileMutex(
            path.with_name(f".{path.name}.lock"), timeout_seconds=timeout_seconds
        )

    def read(self, default: Any = None) -> Any:
        with self.mutex:
            return self._read_unlocked(default)

    def write(self, payload: Any) -> None:
        with self.mutex:
            self._write_unlocked(payload)

    def update(self, transform: Callable[[Any], Any], *, default: Any = None) -> Any:
        with self.mutex:
            current = self._read_unlocked(default)
            updated = transform(current)
            self._write_unlocked(updated)
            return updated

    def _read_unlocked(self, default: Any) -> Any:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def _write_unlocked(self, payload: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_path = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temp = Path(raw_path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally:
            try:
                temp.unlink()
            except OSError:
                pass
