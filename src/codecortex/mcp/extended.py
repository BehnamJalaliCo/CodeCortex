"""Extended MCP application exposing guarded semantic editing tools."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from codecortex.editing import EditService
from codecortex.mcp.server import MCPApplication, MCPServer
from codecortex.runtime import build_runtime


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
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
            ]
        )
        return tools

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not name.startswith("cortex_") or name not in {
            "cortex_rename_symbol",
            "cortex_replace_symbol_body",
            "cortex_insert_before_symbol",
            "cortex_insert_after_symbol",
        }:
            return await super().call(name, arguments)
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
