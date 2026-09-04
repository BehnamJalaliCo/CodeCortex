"""Workspace-ready lifecycle manager for repository runtimes."""

from __future__ import annotations

import threading
from pathlib import Path

from codecortex.runtime import CortexRuntime, build_runtime


class CortexRuntimeManager:
    """Cache one runtime per resolved repository root with explicit eviction."""

    def __init__(self) -> None:
        self._runtimes: dict[Path, CortexRuntime] = {}
        self._lock = threading.RLock()

    def get(self, project_root: Path | str) -> CortexRuntime:
        root = Path(project_root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"repository root does not exist: {root}")
        with self._lock:
            runtime = self._runtimes.get(root)
            if runtime is None:
                runtime = build_runtime(root)
                self._runtimes[root] = runtime
            return runtime

    def remove(self, project_root: Path | str) -> bool:
        root = Path(project_root).expanduser().resolve()
        with self._lock:
            return self._runtimes.pop(root, None) is not None

    def roots(self) -> tuple[Path, ...]:
        with self._lock:
            return tuple(sorted(self._runtimes, key=str))

    def clear(self) -> None:
        with self._lock:
            self._runtimes.clear()
