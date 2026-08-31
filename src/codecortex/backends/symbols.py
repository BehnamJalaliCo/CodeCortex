"""IDE-grade semantic symbol backend adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from codecortex.backends.manager import BackendManager
from codecortex.backends.mcp_client import MCPStdioClient
from codecortex.backends.spec import BACKENDS
from codecortex.core.contracts import Engine
from codecortex.core.models import AgentRequest, Capability, ContextChunk, EngineResult, RequestKind


class SymbolBackendAdapter(Engine):
    """Expose language-server-backed retrieval and editing through one Engine contract."""

    capability = Capability.SYMBOLS

    def __init__(self, project_root: Path, manager: BackendManager | None = None) -> None:
        self.project_root = project_root.resolve()
        self.manager = manager or BackendManager()
        self.spec = BACKENDS["symbols"]

    async def health(self) -> bool:
        return self.manager.probe(self.spec, provision=False)

    def server_args(self) -> tuple[str, ...]:
        return (
            "start-mcp-server",
            "--transport",
            "stdio",
            "--project",
            str(self.project_root),
            "--enable-web-dashboard",
            "false",
            "--open-web-dashboard",
            "false",
        )

    def tools(self) -> list[dict[str, Any]]:
        with MCPStdioClient(self.manager, self.spec, self.server_args(), cwd=self.project_root) as client:
            return client.tools()

    def call(self, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        with MCPStdioClient(self.manager, self.spec, self.server_args(), cwd=self.project_root) as client:
            return client.call_tool(tool, arguments)

    async def execute(self, request: AgentRequest) -> EngineResult:
        explicit_tool = request.metadata.get("symbol_tool")
        explicit_args = request.metadata.get("symbol_arguments")
        if isinstance(explicit_tool, str):
            arguments = dict(explicit_args) if isinstance(explicit_args, Mapping) else {}
            result = self.call(explicit_tool, arguments)
            tool = explicit_tool
        else:
            tool, arguments = self._plan(request)
            result = self.call(tool, arguments)
        content = MCPStdioClient.content_text(result)
        if not content:
            content = json.dumps(result, ensure_ascii=False)
        return EngineResult(
            capability=self.capability,
            content=content,
            chunks=[
                ContextChunk(
                    source=f"symbol:{tool}",
                    content=content,
                    tokens=max(1, len(content) // 4),
                    relevance=0.98,
                    metadata={"backend": self.spec.key, "tool": tool},
                )
            ] if content else [],
            metadata={"backend": self.spec.key, "revision": self.spec.revision, "tool": tool},
        )

    @staticmethod
    def _plan(request: AgentRequest) -> tuple[str, dict[str, Any]]:
        relative_path = request.metadata.get("relative_path")
        if request.kind in {RequestKind.REFACTOR, RequestKind.CHANGE}:
            # Mutating operations must be explicit; default routing stays read-only.
            return "find_symbol", {
                "name_path_pattern": request.query,
                "include_body": True,
                **({"relative_path": relative_path} if isinstance(relative_path, str) else {}),
            }
        if request.metadata.get("references") and isinstance(relative_path, str):
            return "find_referencing_symbols", {
                "name_path": request.query,
                "relative_path": relative_path,
            }
        return "find_symbol", {
            "name_path_pattern": request.query,
            "include_body": request.kind in {RequestKind.DEBUG, RequestKind.REVIEW},
            "depth": 1,
            **({"relative_path": relative_path} if isinstance(relative_path, str) else {}),
        }
