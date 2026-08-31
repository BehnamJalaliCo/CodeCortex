"""Protocol-neutral tool bridge for MCP-compatible hosts."""

from __future__ import annotations

from typing import Any

from codecortex.gateway import CodeCortexGateway


class MCPBridge:
    """Expose stable tool definitions without coupling the core to one transport."""

    def __init__(self, gateway: CodeCortexGateway) -> None:
        self.gateway = gateway

    def tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "cortex_route",
                "description": "Classify a coding request and return the selected capabilities.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": "cortex_query",
                "description": "Run repository intelligence for a coding request.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": "cortex_remember",
                "description": "Save a project decision or reusable fact.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["key", "value"],
                },
            },
            {
                "name": "cortex_health",
                "description": "Return CodeCortex engine health.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "cortex_route":
            return self.gateway.route(str(arguments["query"])).model_dump(mode="json")
        if name == "cortex_query":
            result = await self.gateway.query(str(arguments["query"]))
            return result.model_dump(mode="json")
        if name == "cortex_remember":
            await self.gateway.remember(str(arguments["key"]), str(arguments["value"]))
            return {"saved": True}
        if name == "cortex_health":
            return await self.gateway.health()
        raise KeyError(f"Unknown tool: {name}")
