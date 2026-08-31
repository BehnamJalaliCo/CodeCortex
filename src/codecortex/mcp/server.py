"""Native stateless MCP server with stdio transport."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from codecortex.context import ContextPipeline
from codecortex.git_intelligence import GitIntelligence
from codecortex.indexing.impact import ImpactAnalyzer
from codecortex.indexing.incremental import IncrementalIndex
from codecortex.indexing.indexer import ProjectIndexer
from codecortex.memory.knowledge import ProjectKnowledgeExtractor
from codecortex.runtime import CortexRuntime, build_runtime

PROTOCOL_VERSION = "2026-07-28"
SERVER_INFO = {"name": "codecortex", "version": "0.1.0"}


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


class MCPApplication:
    def __init__(self, runtime: CortexRuntime) -> None:
        self.runtime = runtime
        self.root = runtime.config.project_root

    def tools(self) -> list[dict[str, Any]]:
        text = {"type": "string", "minLength": 1}
        return [
            {
                "name": "cortex_repository_map",
                "description": "Inspect repository graph counts and matching nodes.",
                "inputSchema": _schema({"query": {"type": "string", "default": ""}}),
            },
            {
                "name": "cortex_find_symbol",
                "description": "Find classes, functions, methods, interfaces, and types.",
                "inputSchema": _schema({"query": text}, ["query"]),
            },
            {
                "name": "cortex_find_references",
                "description": "Find graph references to a symbol or file.",
                "inputSchema": _schema({"query": text}, ["query"]),
            },
            {
                "name": "cortex_dependency_graph",
                "description": "Return dependency and call relationships around a target.",
                "inputSchema": _schema({"query": text}, ["query"]),
            },
            {
                "name": "cortex_impact",
                "description": "Estimate the impact and risk of changing a target.",
                "inputSchema": _schema({"query": text}, ["query"]),
            },
            {
                "name": "cortex_context",
                "description": "Build compact query-specific context within a token budget.",
                "inputSchema": _schema(
                    {
                        "query": text,
                        "budget": {"type": "integer", "minimum": 128, "default": 32000},
                    },
                    ["query"],
                ),
            },
            {
                "name": "cortex_memory_search",
                "description": "Search saved project memory and extracted knowledge.",
                "inputSchema": _schema({"query": text}, ["query"]),
            },
            {
                "name": "cortex_remember",
                "description": "Save a project decision or durable fact.",
                "inputSchema": _schema({"key": text, "value": text}, ["key", "value"]),
            },
            {
                "name": "cortex_validate",
                "description": "Run the validation capability for a coding request.",
                "inputSchema": _schema({"query": text}, ["query"]),
            },
            {
                "name": "cortex_stats",
                "description": "Return index, Git, graph, and runtime statistics.",
                "inputSchema": _schema({}),
            },
        ]

    def _graph(self):
        return ProjectIndexer(self.root).build()

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "cortex_repository_map":
            graph = self._graph()
            query = str(arguments.get("query", "")).strip()
            matches = graph.search(query, 30) if query else []
            return {
                "counts": graph.counts(),
                "edges": len(graph.edges),
                "matches": [node.model_dump(mode="json") for node in matches],
            }
        if name == "cortex_find_symbol":
            graph = self._graph()
            matches = [
                node
                for node in graph.search(str(arguments["query"]), 80)
                if node.kind not in {"file", "module", "reference"}
            ]
            return {"symbols": [node.model_dump(mode="json") for node in matches[:50]]}
        if name in {"cortex_find_references", "cortex_dependency_graph"}:
            graph = self._graph()
            matches = graph.search(str(arguments["query"]), 3)
            if not matches:
                return {"nodes": [], "edges": []}
            ids = {node.id for node in matches}
            edges = [
                edge
                for edge in graph.edges
                if edge.source in ids or edge.target in ids
            ]
            connected_ids = ids | {edge.source for edge in edges} | {edge.target for edge in edges}
            nodes = [node for node in graph.nodes if node.id in connected_ids]
            if name == "cortex_find_references":
                edges = [edge for edge in edges if edge.target in ids]
            return {
                "nodes": [node.model_dump(mode="json") for node in nodes],
                "edges": [edge.model_dump(mode="json") for edge in edges],
            }
        if name == "cortex_impact":
            report = ImpactAnalyzer(self._graph()).analyze(str(arguments["query"]))
            return {
                "target": report.target.model_dump(mode="json"),
                "risk_score": report.risk_score,
                "direct": [self._impact_item(item) for item in report.direct],
                "indirect": [self._impact_item(item) for item in report.indirect],
                "affected_tests": [self._impact_item(item) for item in report.affected_tests],
            }
        if name == "cortex_context":
            query = str(arguments["query"])
            budget = int(arguments.get("budget", 32000))
            execution = await self.runtime.gateway.query(query, str(self.root))
            chunks = [chunk for result in execution.results for chunk in result.chunks]
            prepared = await ContextPipeline(self.root, self._graph()).prepare(
                query,
                chunks,
                budget,
            )
            return {
                "chunks": [chunk.model_dump(mode="json") for chunk in prepared.chunks],
                "metrics": prepared.metrics.__dict__,
            }
        if name == "cortex_memory_search":
            query = str(arguments["query"])
            project = await self.runtime.memory.search("project", query, 10)
            knowledge = await self.runtime.memory.search("project_knowledge", query, 10)
            return {"results": [*project, *knowledge][:20]}
        if name == "cortex_remember":
            await self.runtime.gateway.remember(
                str(arguments["key"]),
                str(arguments["value"]),
            )
            return {"saved": True}
        if name == "cortex_validate":
            result = await self.runtime.gateway.query(str(arguments["query"]), str(self.root))
            validation = [
                item.model_dump(mode="json")
                for item in result.results
                if item.capability.value == "validation"
            ]
            return {"validation": validation}
        if name == "cortex_stats":
            index = IncrementalIndex(self.root).refresh()
            graph = self._graph()
            git = GitIntelligence(self.root).analyze(300)
            knowledge = ProjectKnowledgeExtractor(self.root).extract()
            return {
                "index": {
                    "tracked": index.tracked,
                    "added": len(index.added),
                    "changed": len(index.changed),
                    "removed": len(index.removed),
                    "duration_ms": index.duration_ms,
                },
                "graph": {"nodes": len(graph.nodes), "edges": len(graph.edges), **graph.counts()},
                "git": {"commits": git.commits, "hot_files": [item.path for item in git.hot_files[:10]]},
                "knowledge": knowledge.facts(),
                "health": await self.runtime.gateway.health(),
            }
        raise KeyError(f"Unknown tool: {name}")

    @staticmethod
    def _impact_item(item: Any) -> dict[str, Any]:
        return {
            "node": item.node.model_dump(mode="json"),
            "depth": item.depth,
            "via": item.via,
            "risk": item.risk,
        }


class MCPServer:
    def __init__(self, application: MCPApplication) -> None:
        self.application = application

    async def dispatch(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get("id")
        method = message.get("method")
        if request_id is None:
            return None
        try:
            if method in {"server/discover", "initialize"}:
                return self._result(request_id, self._discovery())
            if method == "ping":
                return self._result(request_id, {})
            if method == "tools/list":
                return self._result(
                    request_id,
                    {
                        "tools": self.application.tools(),
                        "ttlMs": 300000,
                    },
                )
            if method == "tools/call":
                params = message.get("params") or {}
                name = str(params.get("name", ""))
                arguments = params.get("arguments") or {}
                payload = await self.application.call(name, dict(arguments))
                return self._result(request_id, self._tool_result(payload))
            return self._error(request_id, -32601, f"Method not found: {method}")
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(request_id, -32602, str(exc))
        except Exception as exc:  # pragma: no cover - defensive protocol boundary
            return self._error(request_id, -32603, f"Internal error: {exc}")

    def _discovery(self) -> dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "serverInfo": SERVER_INFO,
            "capabilities": {"tools": {"listChanged": False}},
        }

    @staticmethod
    def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": payload,
            "isError": False,
        }

    @staticmethod
    def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    async def serve_stdio(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                return
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                response = self._error(None, -32700, "Parse error")
            else:
                response = await self.dispatch(message)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()


def run_stdio(project_root: Path | None = None) -> None:
    runtime = build_runtime(project_root)
    server = MCPServer(MCPApplication(runtime))
    asyncio.run(server.serve_stdio())
