"""Production context compression backend adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from codecortex.backends.manager import BackendManager
from codecortex.backends.mcp_client import MCPStdioClient
from codecortex.backends.spec import BACKENDS
from codecortex.core.contracts import Engine
from codecortex.core.models import AgentRequest, Capability, ContextChunk, EngineResult


class ContextBackendAdapter(Engine):
    """Delegate compression, reversible retrieval and stats to the pinned context engine."""

    capability = Capability.CONTEXT

    def __init__(self, project_root: Path, manager: BackendManager | None = None) -> None:
        self.project_root = project_root.resolve()
        self.manager = manager or BackendManager()
        self.spec = BACKENDS["context"]

    async def health(self) -> bool:
        return self.manager.probe(self.spec, provision=False)

    def server_args(self) -> tuple[str, ...]:
        return ("mcp", "serve", "--transport", "stdio")

    def tools(self) -> list[dict[str, Any]]:
        with self._client() as client:
            return client.tools()

    def compress(self, content: str) -> dict[str, Any]:
        return self.call("headroom_compress", {"content": content})

    def retrieve(self, hash_key: str) -> dict[str, Any]:
        return self.call("headroom_retrieve", {"hash": hash_key})

    def stats(self) -> dict[str, Any]:
        return self.call("headroom_stats", {})

    def call(self, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        with self._client() as client:
            return client.call_tool(tool, arguments)

    async def execute(self, request: AgentRequest) -> EngineResult:
        tool = request.metadata.get("context_tool")
        arguments = request.metadata.get("context_arguments")
        if isinstance(tool, str):
            payload = self.call(tool, dict(arguments) if isinstance(arguments, Mapping) else {})
        else:
            tool = "headroom_compress"
            payload = self.compress(request.query)
        content = MCPStdioClient.content_text(payload)
        if not content:
            content = json.dumps(payload, ensure_ascii=False)
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
            ] if content else [],
            metadata=metadata,
        )

    def _client(self) -> MCPStdioClient:
        workspace = self.project_root / ".codecortex" / "context-backend"
        workspace.mkdir(parents=True, exist_ok=True)
        return MCPStdioClient(
            self.manager,
            self.spec,
            self.server_args(),
            cwd=self.project_root,
            env={"HEADROOM_WORKSPACE_DIR": str(workspace)},
        )
