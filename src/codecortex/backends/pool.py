"""Warm process/session pool for long-lived isolated MCP backends."""

from __future__ import annotations

import atexit
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codecortex.backends.manager import BackendManager
from codecortex.backends.mcp_client import MCPStdioClient
from codecortex.backends.spec import BackendSpec


@dataclass(slots=True)
class _Session:
    client: MCPStdioClient
    lock: threading.RLock


class BackendSessionPool:
    """Keep MCP backend processes warm and serialize traffic per process.

    A failed request invalidates the process and retries once with a clean session. This
    removes repeated process startup/initialize latency while keeping recovery bounded.
    """

    def __init__(self, manager: BackendManager) -> None:
        self.manager = manager
        self._sessions: dict[tuple[object, ...], _Session] = {}
        self._lock = threading.RLock()
        atexit.register(self.close_all)

    @staticmethod
    def _key(
        spec: BackendSpec,
        server_args: Sequence[str],
        cwd: Path | None,
        env: Mapping[str, str] | None,
    ) -> tuple[object, ...]:
        return (
            spec.key,
            spec.revision,
            tuple(server_args),
            str(cwd.resolve()) if cwd else None,
            tuple(sorted((env or {}).items())),
        )

    def _session(
        self,
        spec: BackendSpec,
        server_args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> tuple[tuple[object, ...], _Session]:
        key = self._key(spec, server_args, cwd, env)
        with self._lock:
            session = self._sessions.get(key)
            if session is None:
                client = MCPStdioClient(
                    self.manager,
                    spec,
                    server_args,
                    cwd=cwd,
                    env=env,
                )
                client.start()
                session = _Session(client=client, lock=threading.RLock())
                self._sessions[key] = session
            return key, session

    def invalidate(self, key: tuple[object, ...]) -> None:
        with self._lock:
            session = self._sessions.pop(key, None)
        if session is not None:
            session.client.close()

    def call_tool(
        self,
        spec: BackendSpec,
        server_args: Sequence[str],
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(2):
            key, session = self._session(spec, server_args, cwd=cwd, env=env)
            try:
                with session.lock:
                    return session.client.call_tool(name, arguments)
            except Exception as exc:
                last = exc
                self.invalidate(key)
                if attempt:
                    raise
        assert last is not None
        raise last

    def tools(
        self,
        spec: BackendSpec,
        server_args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        key, session = self._session(spec, server_args, cwd=cwd, env=env)
        try:
            with session.lock:
                return session.client.tools()
        except Exception:
            self.invalidate(key)
            key, session = self._session(spec, server_args, cwd=cwd, env=env)
            with session.lock:
                return session.client.tools()

    def close_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.client.close()
