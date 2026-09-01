"""Native stateless MCP server with validated stdio transport."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codecortex.architecture import ArchitectureDriftDetector, ArchitectureFingerprint, ArchitectureInferenceEngine
from codecortex.context import ContextPipeline
from codecortex.git_intelligence import GitIntelligence
from codecortex.indexing.impact import ImpactAnalyzer
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.memory import TeamMemoryStore
from codecortex.memory.knowledge import ProjectKnowledgeExtractor
from codecortex.mcp.validation import validate_tool_call
from codecortex.pr_intelligence import PRIntelligence
from codecortex.retrieval import RepositorySemanticIndex
from codecortex.runtime import CortexRuntime, build_runtime
from codecortex.tracing import TaskTraceRecorder
from codecortex.workspace import MultiRepositoryWorkspace

PROTOCOL_VERSION = "2026-07-28"
SUPPORTED_PROTOCOLS = frozenset({PROTOCOL_VERSION, "2025-06-18"})
SERVER_INFO = {"name": "codecortex", "version": "0.1.0a3"}


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def _log_internal_error(root: Path, error_id: str, exc: Exception) -> None:
    path = root / ".codecortex" / "runtime" / "mcp-errors.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"error_id": error_id, "created_at": datetime.now(UTC).isoformat(), "type": type(exc).__name__, "detail": str(exc)[:4000]}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    if os.name != "nt":
        try:
            path.chmod(0o600)
        except OSError:
            pass


class MCPApplication:
    def __init__(self, runtime: CortexRuntime) -> None:
        self.runtime = runtime
        self.root = runtime.config.project_root

    def tools(self) -> list[dict[str, Any]]:
        text = {"type": "string", "minLength": 1}
        positive_int = {"type": "integer", "minimum": 1}
        return [
            {"name": "cortex_repository_map", "description": "Inspect repository graph counts and matching nodes.", "inputSchema": _schema({"query": {"type": "string", "default": ""}})},
            {"name": "cortex_find_symbol", "description": "Find code symbols across supported languages.", "inputSchema": _schema({"query": text}, ["query"])},
            {"name": "cortex_find_references", "description": "Find graph references to a symbol or file.", "inputSchema": _schema({"query": text}, ["query"])},
            {"name": "cortex_dependency_graph", "description": "Return dependency and call relationships around a target.", "inputSchema": _schema({"query": text}, ["query"])},
            {"name": "cortex_impact", "description": "Estimate impact and risk of changing a target.", "inputSchema": _schema({"query": text}, ["query"])},
            {"name": "cortex_semantic_search", "description": "Hybrid semantic, lexical, and structural repository search.", "inputSchema": _schema({"query": text, "limit": {**positive_int, "default": 20}}, ["query"])},
            {"name": "cortex_context", "description": "Build compact query-specific context.", "inputSchema": _schema({"query": text, "budget": {"type": "integer", "minimum": 128, "default": 32000}}, ["query"])},
            {"name": "cortex_architecture", "description": "Infer repository architecture with evidence and confidence.", "inputSchema": _schema({})},
            {"name": "cortex_architecture_drift", "description": "Compare current architecture with a saved baseline fingerprint.", "inputSchema": _schema({})},
            {"name": "cortex_symbol_history", "description": "Return Git history, blame, and ownership for a symbol line range.", "inputSchema": _schema({"path": text, "start": positive_int, "end": positive_int}, ["path", "start", "end"])},
            {"name": "cortex_pr_intelligence", "description": "Analyze a Git diff for changed symbols, impact, tests, and risk.", "inputSchema": _schema({"base_ref": text, "head_ref": {"type": "string", "default": "HEAD"}}, ["base_ref"])},
            {"name": "cortex_memory_search", "description": "Search local project memory and extracted knowledge.", "inputSchema": _schema({"query": text}, ["query"])},
            {"name": "cortex_team_memory_search", "description": "Search revisioned shared team memory.", "inputSchema": _schema({"query": text, "namespace": {"type": "string", "default": "project"}}, ["query"])},
            {"name": "cortex_remember", "description": "Save a project decision or durable fact.", "inputSchema": _schema({"key": text, "value": text}, ["key", "value"])},
            {"name": "cortex_workspace_search", "description": "Search all repositories registered in the current workspace.", "inputSchema": _schema({"query": text, "limit": {**positive_int, "default": 40}}, ["query"])},
            {"name": "cortex_trace_summary", "description": "Summarize a recorded agent task trace.", "inputSchema": _schema({"trace_id": text}, ["trace_id"])},
            {"name": "cortex_validate", "description": "Run validation for a coding request.", "inputSchema": _schema({"query": text}, ["query"])},
            {"name": "cortex_stats", "description": "Return index, Git, graph, and runtime statistics.", "inputSchema": _schema({})},
        ]

    def _graph(self):
        return IncrementalGraphIndex(self.root).refresh()[0]

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        validate_tool_call(self.tools(), name, arguments)
        if name == "cortex_repository_map":
            graph = self._graph()
            query = str(arguments.get("query", "")).strip()
            matches = graph.search(query, 30) if query else []
            return {"counts": graph.counts(), "edges": len(graph.edges), "matches": [node.model_dump(mode="json") for node in matches]}
        if name == "cortex_find_symbol":
            matches = [node for node in self._graph().search(str(arguments["query"]), 80) if node.kind not in {"file", "module", "reference"}]
            return {"symbols": [node.model_dump(mode="json") for node in matches[:50]]}
        if name in {"cortex_find_references", "cortex_dependency_graph"}:
            graph = self._graph()
            matches = graph.search(str(arguments["query"]), 3)
            if not matches:
                return {"nodes": [], "edges": []}
            ids = {node.id for node in matches}
            edges = [edge for edge in graph.edges if edge.source in ids or edge.target in ids]
            if name == "cortex_find_references":
                edges = [edge for edge in edges if edge.target in ids]
            connected = ids | {edge.source for edge in edges} | {edge.target for edge in edges}
            nodes = [node for node in graph.nodes if node.id in connected]
            return {"nodes": [node.model_dump(mode="json") for node in nodes], "edges": [edge.model_dump(mode="json") for edge in edges]}
        if name == "cortex_impact":
            report = ImpactAnalyzer(self._graph()).analyze(str(arguments["query"]))
            return {"target": report.target.model_dump(mode="json"), "risk_score": report.risk_score, "direct": [self._impact_item(item) for item in report.direct], "indirect": [self._impact_item(item) for item in report.indirect], "affected_tests": [self._impact_item(item) for item in report.affected_tests]}
        if name == "cortex_semantic_search":
            semantic = RepositorySemanticIndex(self.root)
            semantic.refresh(self._graph())
            hits = semantic.search(str(arguments["query"]), int(arguments.get("limit", 20)))
            return {"hits": [{"id": hit.document.id, "score": hit.score, "vector_score": hit.vector_score, "lexical_score": hit.lexical_score, "structural_score": hit.structural_score, "metadata": hit.document.metadata} for hit in hits]}
        if name == "cortex_context":
            query = str(arguments["query"])
            budget = self.runtime.config.validate_budget(int(arguments.get("budget", 32000)))
            execution = await self.runtime.gateway.query(query, str(self.root))
            chunks = [chunk for result in execution.results for chunk in result.chunks]
            prepared = await ContextPipeline(self.root, self._graph()).prepare(query, chunks, budget)
            return {"chunks": [chunk.model_dump(mode="json") for chunk in prepared.chunks], "metrics": asdict(prepared.metrics), "trace_id": execution.metadata.get("trace_id")}
        if name == "cortex_architecture":
            return asdict(ArchitectureInferenceEngine().analyze(self._graph()))
        if name == "cortex_architecture_drift":
            detector = ArchitectureDriftDetector()
            current = detector.fingerprint(self._graph())
            baseline = ArchitectureFingerprint.load(self.root / ".codecortex" / "architecture" / "baseline.json")
            if baseline is None:
                return {"baseline": "missing", "current": asdict(current), "hint": "Create a baseline with the architecture-baseline CLI command."}
            return {"baseline": asdict(baseline), "current": asdict(current), "drift": asdict(detector.compare(baseline, current))}
        if name == "cortex_symbol_history":
            return asdict(GitIntelligence(self.root).symbol_history(str(arguments["path"]), int(arguments["start"]), int(arguments["end"])))
        if name == "cortex_pr_intelligence":
            report = PRIntelligence(self.root, self._graph()).analyze(str(arguments["base_ref"]), str(arguments.get("head_ref", "HEAD")))
            return {"base_ref": report.base_ref, "head_ref": report.head_ref, "risk_score": report.risk_score, "risk_level": report.risk_level, "affected_tests": list(report.affected_tests), "files": [asdict(item) for item in report.files], "symbols": [{"node": item.node.model_dump(mode="json"), "impact_risk": item.impact_risk, "affected_nodes": item.affected_nodes, "affected_tests": item.affected_tests} for item in report.symbols]}
        if name == "cortex_memory_search":
            query = str(arguments["query"])
            project = await self.runtime.memory.search("project", query, 10)
            knowledge = await self.runtime.memory.search("project_knowledge", query, 10)
            return {"results": [*project, *knowledge][:20]}
        if name == "cortex_team_memory_search":
            store = TeamMemoryStore(self.root / ".codecortex" / "memory" / "team.sqlite3")
            return {"results": [asdict(entry) for entry in store.search_entries(str(arguments.get("namespace", "project")), str(arguments["query"]), 20)]}
        if name == "cortex_remember":
            await self.runtime.gateway.remember(str(arguments["key"]), str(arguments["value"]))
            return {"saved": True}
        if name == "cortex_workspace_search":
            workspace = MultiRepositoryWorkspace(self.root / ".codecortex" / "workspace.json")
            hits = workspace.search(str(arguments["query"]), int(arguments.get("limit", 40)))
            return {"hits": [{"repository": hit.repository, "score": hit.score, "node": hit.node.model_dump(mode="json")} for hit in hits]}
        if name == "cortex_trace_summary":
            return asdict(TaskTraceRecorder(self.root / ".codecortex" / "runtime" / "traces.jsonl").summarize(str(arguments["trace_id"])))
        if name == "cortex_validate":
            result = await self.runtime.gateway.query(str(arguments["query"]), str(self.root))
            return {"validation": [item.model_dump(mode="json") for item in result.results if item.capability.value == "validation"], "trace_id": result.metadata.get("trace_id")}
        if name == "cortex_stats":
            graph, graph_stats = IncrementalGraphIndex(self.root).refresh()
            git = GitIntelligence(self.root).analyze(300)
            knowledge = ProjectKnowledgeExtractor(self.root).extract()
            return {"index": {"tracked": graph_stats.index.tracked, "added": len(graph_stats.index.added), "changed": len(graph_stats.index.changed), "removed": len(graph_stats.index.removed), "files_reparsed": graph_stats.files_reparsed, "full_rebuild": graph_stats.full_rebuild, "duration_ms": graph_stats.index.duration_ms}, "graph": {"nodes": len(graph.nodes), "edges": len(graph.edges), **graph.counts()}, "git": {"commits": git.commits, "hot_files": [item.path for item in git.hot_files[:10]]}, "knowledge": knowledge.facts(), "health": await self.runtime.gateway.health()}
        raise KeyError(f"Unknown tool: {name}")

    @staticmethod
    def _impact_item(item: Any) -> dict[str, Any]:
        return {"node": item.node.model_dump(mode="json"), "depth": item.depth, "via": item.via, "risk": item.risk}


class MCPServer:
    def __init__(self, application: MCPApplication) -> None:
        self.application = application

    async def dispatch(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get("id")
        method = message.get("method")
        if request_id is None:
            return None
        try:
            if method == "initialize":
                params = message.get("params") or {}
                if not isinstance(params, dict):
                    raise ValueError("initialize params must be an object")
                requested = str(params.get("protocolVersion", ""))
                if requested not in SUPPORTED_PROTOCOLS:
                    raise ValueError(f"unsupported protocolVersion: {requested}")
                return self._result(request_id, self._discovery(requested))
            if method == "server/discover":
                return self._result(request_id, self._discovery(PROTOCOL_VERSION))
            if method == "ping":
                return self._result(request_id, {})
            if method == "tools/list":
                return self._result(request_id, {"tools": self.application.tools(), "ttlMs": 300000})
            if method == "tools/call":
                params = message.get("params") or {}
                if not isinstance(params, dict):
                    raise ValueError("tools/call params must be an object")
                raw_args = params.get("arguments", {})
                if not isinstance(raw_args, dict):
                    raise ValueError("tool arguments must be an object")
                payload = await self.application.call(str(params.get("name", "")), raw_args)
                return self._result(request_id, self._tool_result(payload))
            return self._error(request_id, -32601, f"Method not found: {method}")
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(request_id, -32602, str(exc))
        except Exception as exc:  # pragma: no cover - integration boundary
            error_id = uuid.uuid4().hex
            _log_internal_error(self.application.root, error_id, exc)
            return self._error(request_id, -32603, f"Internal error; id={error_id}")

    @staticmethod
    def _discovery(protocol_version: str) -> dict[str, Any]:
        return {"protocolVersion": protocol_version, "serverInfo": SERVER_INFO, "capabilities": {"tools": {"listChanged": False}}}

    @staticmethod
    def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return {"content": [{"type": "text", "text": text}], "structuredContent": payload, "isError": False}

    @staticmethod
    def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    async def serve_stdio(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                return
            try:
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError("message must be an object")
            except (json.JSONDecodeError, ValueError):
                response = self._error(None, -32700, "Parse error")
            else:
                response = await self.dispatch(message)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()


def run_stdio(project_root: Path | None = None) -> None:
    runtime = build_runtime(project_root)
    asyncio.run(MCPServer(MCPApplication(runtime)).serve_stdio())
