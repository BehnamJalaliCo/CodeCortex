"""Small synchronous MCP stdio client used by isolated backend adapters."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from codecortex.backends.manager import BackendManager
from codecortex.backends.spec import BackendSpec


class MCPError(RuntimeError):
    pass


class MCPStdioClient:
    """Persistent JSON-RPC client for an MCP server using stdio transport."""

    def __init__(
        self,
        manager: BackendManager,
        spec: BackendSpec,
        server_args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.manager = manager
        self.spec = spec
        self.server_args = tuple(server_args)
        self.cwd = cwd
        self.env = dict(env or {})
        self.timeout_seconds = timeout_seconds
        self._process: subprocess.Popen[str] | None = None
        self._messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stderr: queue.Queue[str] = queue.Queue()
        self._request_id = 0
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None

    def __enter__(self) -> MCPStdioClient:
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.close()

    def start(self) -> None:
        if self._process is not None:
            return
        command = self.manager.ensure(self.spec)
        self._process = subprocess.Popen(
            [str(command), *self.server_args],
            cwd=str(self.cwd) if self.cwd else None,
            env={**os.environ, **self.env},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader.start()
        self._stderr_reader.start()
        self._initialize()

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

    def tools(self) -> list[dict[str, Any]]:
        result = self.request("tools/list", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return [item for item in tools if isinstance(item, dict)]

    def call_tool(self, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        result = self.request("tools/call", {"name": name, "arguments": dict(arguments or {})})
        if not isinstance(result, dict):
            raise MCPError(f"tool {name!r} returned a non-object result")
        if result.get("isError"):
            raise MCPError(self._content_text(result) or f"tool {name!r} failed")
        return result

    def request(self, method: str, params: Mapping[str, Any]) -> Any:
        self._request_id += 1
        request_id = self._request_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)})
        deadline = time.monotonic() + self.timeout_seconds
        deferred: list[dict[str, Any]] = []
        try:
            while time.monotonic() < deadline:
                self._raise_if_exited()
                try:
                    message = self._messages.get(
                        timeout=min(0.25, max(0.01, deadline - time.monotonic()))
                    )
                except queue.Empty:
                    continue
                if message.get("id") != request_id:
                    deferred.append(message)
                    continue
                if "error" in message:
                    raise MCPError(str(message["error"]))
                return message.get("result")
            raise TimeoutError(f"MCP request timed out: {method}")
        finally:
            for message in deferred:
                self._messages.put(message)

    @staticmethod
    def content_text(result: Mapping[str, Any]) -> str:
        return MCPStdioClient._content_text(result)

    def _initialize(self) -> None:
        protocol = os.getenv("CODECORTEX_MCP_PROTOCOL", "2025-06-18")
        self.request(
            "initialize",
            {
                "protocolVersion": protocol,
                "capabilities": {},
                "clientInfo": {"name": "CodeCortex", "version": "0.1.0"},
            },
        )
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def _send(self, payload: Mapping[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise MCPError("MCP process is not running")
        process.stdin.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n")
        process.stdin.flush()

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for raw in process.stdout:
            line = raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                self._messages.put(message)

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for raw in process.stderr:
            if raw.strip():
                self._stderr.put(raw.rstrip())

    def _raise_if_exited(self) -> None:
        process = self._process
        if process is None:
            raise MCPError("MCP process is not running")
        code = process.poll()
        if code is None:
            return
        lines: list[str] = []
        while not self._stderr.empty() and len(lines) < 20:
            lines.append(self._stderr.get_nowait())
        detail = "\n".join(lines)
        raise MCPError(f"MCP server exited with {code}: {detail}".strip())

    @staticmethod
    def _content_text(result: Mapping[str, Any]) -> str:
        chunks = result.get("content", [])
        texts: list[str] = []
        if isinstance(chunks, list):
            for chunk in chunks:
                if isinstance(chunk, dict) and chunk.get("type") == "text":
                    text = chunk.get("text")
                    if isinstance(text, str):
                        texts.append(text)
        return "\n".join(texts)
