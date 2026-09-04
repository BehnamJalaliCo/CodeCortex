"""Extended MCP application exposing guarded semantic editing tools."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from codecortex.editing import EditService
from codecortex.mcp.server import MCPApplication, MCPServer
from codecortex.mcp.validation import validate_tool_call
from codecortex.runtime import build_runtime
from codecortex.structural import StructuralRewriteService


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


#: Tools that mutate source. Remote deployments gate these through the
#: mutation-principal policy in ``codecortex.distributed.remote_mcp``.
_EDIT_TOOLS = {
    "cortex_rename_symbol",
    "cortex_replace_symbol_body",
    "cortex_insert_before_symbol",
    "cortex_insert_after_symbol",
    "cortex_rewrite_apply",
}


class ExtendedMCPApplication(MCPApplication):
    def tools(self) -> list[dict[str, Any]]:
        tools = super().tools()
        text = {"type": "string", "minLength": 1}
        tools.extend(
            [
                {
                    "name": "cortex_rename_symbol",
                    "description": "Rename a symbol across the codebase using language-server refactoring.",
                    "inputSchema": _schema(
                        {"path": text, "name_path": text, "new_name": text},
                        ["path", "name_path", "new_name"],
                    ),
                },
                {
                    "name": "cortex_replace_symbol_body",
                    "description": "Replace one symbol definition after a semantic preflight read.",
                    "inputSchema": _schema(
                        {"path": text, "name_path": text, "body": text},
                        ["path", "name_path", "body"],
                    ),
                },
                {
                    "name": "cortex_insert_before_symbol",
                    "description": "Insert code immediately before a semantic symbol.",
                    "inputSchema": _schema(
                        {"path": text, "name_path": text, "body": text},
                        ["path", "name_path", "body"],
                    ),
                },
                {
                    "name": "cortex_insert_after_symbol",
                    "description": "Insert code immediately after a semantic symbol.",
                    "inputSchema": _schema(
                        {"path": text, "name_path": text, "body": text},
                        ["path", "name_path", "body"],
                    ),
                },
                {
                    "name": "cortex_rewrite_apply",
                    "description": (
                        "Apply a structural rewrite previously returned by "
                        "cortex_rewrite_preview. Refuses expired previews and files "
                        "that changed after the preview was taken."
                    ),
                    "inputSchema": _schema(
                        {"preview_id": {"type": "string", "minLength": 1, "maxLength": 64}},
                        ["preview_id"],
                    ),
                },
            ]
        )
        return tools

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.runtime.telemetry.emit("mcp.tool.called", tool=name)
        if name not in _EDIT_TOOLS:
            return await super().call(name, arguments)
        if name == "cortex_rewrite_apply":
            validate_tool_call(self.tools(), name, arguments)
            rewrites = StructuralRewriteService(self.root, self.runtime.config)
            result = await rewrites.apply(str(arguments["preview_id"]))
            self.runtime.telemetry.emit(
                "structural.rewrite.applied",
                preview_id=result.preview_id,
                applied=result.applied,
                files=result.files_changed,
            )
            return result.model_dump(mode="json")
        service = EditService(self.runtime)
        path = str(arguments["path"])
        name_path = str(arguments["name_path"])
        if name == "cortex_rename_symbol":
            payload = await asyncio.to_thread(
                service.rename,
                path,
                name_path,
                str(arguments["new_name"]),
            )
        elif name == "cortex_replace_symbol_body":
            payload = await asyncio.to_thread(
                service.replace,
                path,
                name_path,
                str(arguments["body"]),
            )
        elif name == "cortex_insert_before_symbol":
            payload = await asyncio.to_thread(
                service.insert_before,
                path,
                name_path,
                str(arguments["body"]),
            )
        else:
            payload = await asyncio.to_thread(
                service.insert_after,
                path,
                name_path,
                str(arguments["body"]),
            )
        return {"edited": True, "operation": name, "backend_result": payload}


def run_stdio(project_root: Path | None = None) -> None:
    runtime = build_runtime(project_root)
    asyncio.run(MCPServer(ExtendedMCPApplication(runtime)).serve_stdio())
