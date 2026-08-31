"""IDE-grade semantic symbol backend adapter with guarded edits."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from codecortex.backends.base import ManagedAdapterMixin
from codecortex.backends.manager import BackendManager
from codecortex.backends.mcp_client import MCPStdioClient
from codecortex.backends.pool import BackendSessionPool
from codecortex.backends.spec import BACKENDS
from codecortex.core.contracts import Engine
from codecortex.core.models import AgentRequest, Capability, ContextChunk, EngineResult, RequestKind


class SymbolBackendAdapter(ManagedAdapterMixin, Engine):
    capability = Capability.SYMBOLS
    required_tools = {"find_symbol", "find_referencing_symbols"}
    editing_tools = {
        "rename_symbol",
        "replace_symbol_body",
        "insert_before_symbol",
        "insert_after_symbol",
    }

    def __init__(self, project_root: Path, manager: BackendManager | None = None) -> None:
        self.project_root = project_root.resolve()
        self.manager = manager or BackendManager()
        self.spec = BACKENDS["symbols"]
        self.pool = BackendSessionPool(self.manager)

    async def health(self) -> bool:
        return await asyncio.to_thread(self.manager.probe, self.spec, False)

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
        tools = self.pool.tools(
            self.spec,
            self.server_args(),
            cwd=self.project_root,
        )
        self.require_tools(tools, self.required_tools)
        return tools

    def call(self, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self.pool.call_tool(
            self.spec,
            self.server_args(),
            tool,
            arguments,
            cwd=self.project_root,
        )

    def _relative_path(self, value: str) -> str:
        candidate = (self.project_root / value).resolve()
        try:
            relative = candidate.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError("symbol edits must stay inside the project root") from exc
        if not candidate.exists():
            raise ValueError(f"path does not exist: {value}")
        if not candidate.is_file():
            raise ValueError(f"expected a file path: {value}")
        return relative.as_posix()

    def _require_edit_tool(self, name: str) -> None:
        available = {str(item.get("name")) for item in self.tools()}
        if name not in available:
            raise RuntimeError(f"symbol backend does not expose required edit tool: {name}")

    def preflight_symbol(self, name_path: str, relative_path: str) -> dict[str, Any]:
        relative_path = self._relative_path(relative_path)
        return self.call(
            "find_symbol",
            {
                "name_path_pattern": name_path,
                "relative_path": relative_path,
                "include_body": True,
                "max_matches": 2,
            },
        )

    def rename_symbol(self, name_path: str, relative_path: str, new_name: str) -> dict[str, Any]:
        relative_path = self._relative_path(relative_path)
        if not new_name.strip():
            raise ValueError("new_name cannot be empty")
        self._require_edit_tool("rename_symbol")
        self.preflight_symbol(name_path, relative_path)
        return self.call(
            "rename_symbol",
            {"name_path": name_path, "relative_path": relative_path, "new_name": new_name},
        )

    def replace_symbol_body(self, name_path: str, relative_path: str, body: str) -> dict[str, Any]:
        relative_path = self._relative_path(relative_path)
        if not body.strip():
            raise ValueError("replacement body cannot be empty")
        self._require_edit_tool("replace_symbol_body")
        self.preflight_symbol(name_path, relative_path)
        return self.call(
            "replace_symbol_body",
            {"name_path": name_path, "relative_path": relative_path, "body": body},
        )

    def insert_before_symbol(self, name_path: str, relative_path: str, body: str) -> dict[str, Any]:
        relative_path = self._relative_path(relative_path)
        self._require_edit_tool("insert_before_symbol")
        self.preflight_symbol(name_path, relative_path)
        return self.call(
            "insert_before_symbol",
            {"name_path": name_path, "relative_path": relative_path, "body": body},
        )

    def insert_after_symbol(self, name_path: str, relative_path: str, body: str) -> dict[str, Any]:
        relative_path = self._relative_path(relative_path)
        self._require_edit_tool("insert_after_symbol")
        self.preflight_symbol(name_path, relative_path)
        return self.call(
            "insert_after_symbol",
            {"name_path": name_path, "relative_path": relative_path, "body": body},
        )

    async def execute(self, request: AgentRequest) -> EngineResult:
        return await asyncio.to_thread(self._execute_sync, request)

    def _execute_sync(self, request: AgentRequest) -> EngineResult:
        explicit_tool = request.metadata.get("symbol_tool")
        explicit_args = request.metadata.get("symbol_arguments")
        if isinstance(explicit_tool, str):
            arguments = dict(explicit_args) if isinstance(explicit_args, Mapping) else {}
            result = self.call(explicit_tool, arguments)
            tool = explicit_tool
        else:
            tool, arguments = self._plan(request)
            result = self.call(tool, arguments)
        content = MCPStdioClient.content_text(result) or json.dumps(result, ensure_ascii=False)
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
            ]
            if content
            else [],
            metadata={"backend": self.spec.key, "revision": self.spec.revision, "tool": tool},
        )

    @staticmethod
    def _plan(request: AgentRequest) -> tuple[str, dict[str, Any]]:
        relative_path = request.metadata.get("relative_path")
        if request.kind in {RequestKind.REFACTOR, RequestKind.CHANGE}:
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
