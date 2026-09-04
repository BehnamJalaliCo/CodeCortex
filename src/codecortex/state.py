"""Crash-safe and process-safe local JSON state primitives."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
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
        # Serialize callers that share this FileMutex instance before touching
        # the cross-process lock directory. Without this local guard, a thread
        # can observe another thread's release/recreate window on Windows and
        # receive WinError 5 while mkdir races with rmtree.
        self._thread_lock = threading.Lock()
        self._held = False

    def acquire(self) -> None:
        deadline = time.monotonic() + self.timeout_seconds
        remaining = max(0.0, deadline - time.monotonic())
        if not self._thread_lock.acquire(timeout=remaining):
            raise TimeoutError(f"timed out waiting for state lock: {self.path}") from None

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            while True:
                try:
                    self.path.mkdir()
                except (FileExistsError, PermissionError):
                    # On Windows, mkdir may briefly report access denied while
                    # another owner is removing the lock directory. Treat that
                    # transient state as contention and retry within the same
                    # bounded timeout instead of leaking a platform-specific
                    # PermissionError to callers.
                    self._break_stale_lock()
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"timed out waiting for state lock: {self.path}"
                        ) from None
                    time.sleep(0.05)
                    continue

                marker = self.path / "owner.json"
                try:
                    marker.write_text(
                        json.dumps({"pid": os.getpid(), "created": time.time()}),
                        encoding="utf-8",
                    )
                except BaseException:
                    shutil.rmtree(self.path, ignore_errors=True)
                    raise

                self._held = True
                return
        except BaseException:
            self._thread_lock.release()
            raise

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
        try:
            shutil.rmtree(self.path, ignore_errors=True)
        finally:
            self._held = False
            self._thread_lock.release()

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
