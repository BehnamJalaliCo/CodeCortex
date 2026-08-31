"""Production context compression backend adapter."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from codecortex.backends.base import ManagedAdapterMixin
from codecortex.backends.manager import BackendManager
from codecortex.backends.mcp_client import MCPStdioClient
from codecortex.backends.pool import BackendSessionPool
from codecortex.backends.spec import BACKENDS
from codecortex.core.contracts import Engine
from codecortex.core.models import AgentRequest, Capability, ContextChunk, EngineResult


class ContextBackendAdapter(ManagedAdapterMixin, Engine):
    capability = Capability.CONTEXT
    required_tools = {"headroom_compress", "headroom_retrieve", "headroom_stats"}

    def __init__(self, project_root: Path, manager: BackendManager | None = None) -> None:
        self.project_root = project_root.resolve()
        self.manager = manager or BackendManager()
        self.spec = BACKENDS["context"]
        self.pool = BackendSessionPool(self.manager)

    async def health(self) -> bool:
        return await asyncio.to_thread(self.manager.probe, self.spec, False)

    def server_args(self) -> tuple[str, ...]:
        return ("mcp", "serve", "--transport", "stdio")

    def _env(self) -> dict[str, str]:
        workspace = self.project_root / ".codecortex" / "context-backend"
        workspace.mkdir(parents=True, exist_ok=True)
        return {"HEADROOM_WORKSPACE_DIR": str(workspace)}

    def _client(self) -> MCPStdioClient:
        """Return an unstarted correctly scoped client for compatibility and diagnostics."""
        return MCPStdioClient(
            self.manager,
            self.spec,
            self.server_args(),
            cwd=self.project_root,
            env=self._env(),
        )

    def tools(self) -> list[dict[str, Any]]:
        tools = self.pool.tools(
            self.spec,
            self.server_args(),
            cwd=self.project_root,
            env=self._env(),
        )
        self.require_tools(tools, self.required_tools)
        return tools

    def compress(self, content: str) -> dict[str, Any]:
        return self.call("headroom_compress", {"content": content})

    def compress_batch(self, contents: Sequence[str]) -> list[dict[str, Any]]:
        return [self.compress(content) for content in contents]

    def retrieve(self, hash_key: str) -> dict[str, Any]:
        return self.call("headroom_retrieve", {"hash": hash_key})

    def stats(self) -> dict[str, Any]:
        return self.call("headroom_stats", {})

    def call(self, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self.pool.call_tool(
            self.spec,
            self.server_args(),
            tool,
            arguments,
            cwd=self.project_root,
            env=self._env(),
        )

    async def execute(self, request: AgentRequest) -> EngineResult:
        return await asyncio.to_thread(self._execute_sync, request)

    def _execute_sync(self, request: AgentRequest) -> EngineResult:
        tool = request.metadata.get("context_tool")
        arguments = request.metadata.get("context_arguments")
        payload = (
            self.call(tool, dict(arguments) if isinstance(arguments, Mapping) else {})
            if isinstance(tool, str)
            else self.compress(request.query)
        )
        tool = tool if isinstance(tool, str) else "headroom_compress"
        content = MCPStdioClient.content_text(payload) or json.dumps(payload, ensure_ascii=False)
        metadata: dict[str, Any] = {
            "backend": self.spec.key,
            "revision": self.spec.revision,
            "tool": tool,
        }
        structured = payload.get("structuredContent")
        if isinstance(structured, dict):
            metadata["compression"] = structured
        return EngineResult(
            capability=self.capability,
            content=content,
            chunks=[
                ContextChunk(
                    source=f"context:{tool}",
                    content=content,
                    tokens=max(1, len(content) // 4),
                    relevance=1.0,
                    metadata=metadata,
                )
            ]
            if content
            else [],
            metadata=metadata,
        )
