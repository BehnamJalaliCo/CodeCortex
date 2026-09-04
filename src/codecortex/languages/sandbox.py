"""Crash-isolated wrapper around the native Tree-sitter provider.

Why this exists
---------------
The native grammars are third-party C/Rust code reached through
``tree_sitter_language_pack``. A malformed or merely unlucky input can fault
inside that extension, and a fault there is a **process** death: no Python
exception is raised, ``try/except`` cannot see it, and the whole ``cortex
index`` run dies with SIGSEGV having written nothing.

That was not theoretical. Indexing a repository containing an ordinary 26 KB
``.jsx`` file killed the indexer every time, and the same file parsed cleanly
on roughly one run in three — the signature of memory corruption inside the
extension rather than a logic error in the walk above it.

CodeCortex cannot fix a grammar it does not ship, but it must not lose an
entire index because one file upset one grammar. So the native parse runs in a
worker process:

* the worker dies -> the pool is rebuilt, the offending file falls back to the
  language-agnostic parser, and indexing continues;
* the worker hangs -> the same, bounded by ``timeout``;
* after ``max_restarts`` deaths in one run the native path is switched off
  entirely, because a grammar that keeps faulting will keep faulting and every
  restart costs a process spawn.

Set ``CODECORTEX_NATIVE_INPROCESS=1`` to parse in this process instead (faster,
and what the test suite uses for the provider's own unit tests).
"""

from __future__ import annotations

import multiprocessing
import os
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from codecortex.languages.native import NativeUnit, TreeSitterParserProvider

__all__ = ["IsolatedParserProvider", "native_provider"]

#: Seconds a single file may spend in the native parser before it is abandoned.
DEFAULT_TIMEOUT = 20.0

#: Worker deaths tolerated in one run before the native path is disabled.
DEFAULT_MAX_RESTARTS = 3

_WORKER_PROVIDER: TreeSitterParserProvider | None = None


def _worker_parse(language: str, source: str) -> list[NativeUnit]:
    """Parse inside the worker process, reusing one provider per worker."""
    global _WORKER_PROVIDER
    if _WORKER_PROVIDER is None:
        _WORKER_PROVIDER = TreeSitterParserProvider()
    return _WORKER_PROVIDER.parse(language, source)


class IsolatedParserProvider:
    """Same surface as :class:`TreeSitterParserProvider`, crash-isolated."""

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_restarts: int = DEFAULT_MAX_RESTARTS,
    ) -> None:
        self.timeout = timeout
        self.max_restarts = max_restarts
        self._pool: ProcessPoolExecutor | None = None
        self._restarts = 0
        self._disabled = False

    @classmethod
    def available(cls) -> bool:
        return TreeSitterParserProvider.available()

    @property
    def degraded(self) -> bool:
        """True once the native path has been abandoned for this run."""
        return self._disabled

    def parse(self, language: str, source: str) -> list[NativeUnit]:
        if self._disabled:
            return []
        try:
            pool = self._ensure_pool()
            return list(pool.submit(_worker_parse, language, source).result(self.timeout))
        except (BrokenExecutor, FutureTimeout, OSError):
            # The worker died or wedged on this input. Drop the pool and let the
            # caller fall back; an empty list is the provider's "nothing found".
            self._discard_pool()
            self._restarts += 1
            if self._restarts >= self.max_restarts:
                self._disabled = True
            return []
        except Exception:
            return []

    def close(self) -> None:
        self._discard_pool()

    def __del__(self) -> None:  # best effort; pools must not outlive the run
        try:
            self._discard_pool()
        except Exception:
            pass

    def _ensure_pool(self) -> ProcessPoolExecutor:
        if self._pool is None:
            # "spawn", not the platform default: CodeCortex is also used from
            # servers and agents that already have threads running, and forking
            # a multi-threaded process can deadlock the child.
            self._pool = ProcessPoolExecutor(
                max_workers=1, mp_context=multiprocessing.get_context("spawn")
            )
        return self._pool

    def _discard_pool(self) -> None:
        pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
            # `_processes` is None once shutdown has torn the pool down.
            for process in list((getattr(pool, "_processes", None) or {}).values()):
                if process.is_alive():
                    process.kill()


def native_provider() -> TreeSitterParserProvider | IsolatedParserProvider | None:
    """Return the configured native provider, or None when unavailable."""
    if not TreeSitterParserProvider.available():
        return None
    if os.getenv("CODECORTEX_NATIVE_INPROCESS", "").strip() in {"1", "true", "yes"}:
        return TreeSitterParserProvider()
    return IsolatedParserProvider()
