"""Distributed MCP application that composes local and cluster tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codecortex.distributed.memory_sync import MemoryMutation, SharedMemoryReplica
from codecortex.distributed.workers import WorkerCoordinator
from codecortex.mcp.server import MCPApplication
from codecortex.mcp.validation import validate_tool_call
from codecortex.runtime import CortexRuntime


class DistributedMCPApplication:
    def __init__(self, runtime: CortexRuntime, *, node_id: str, state_dir: Path | None = None) -> None:
        self.base = MCPApplication(runtime)
        root = state_dir or runtime.config.state_dir / "distributed"
        root.mkdir(parents=True, exist_ok=True)
        self.memory = SharedMemoryReplica(root / "shared-memory.db", node_id)
        self.workers = WorkerCoordinator(root / "workers.db")
        self.node_id = node_id

    def tools(self) -> list[dict[str, Any]]:
        return [*self.base.tools(),
            {"name": "cortex_sync_pull", "description": "Pull versioned shared-memory mutations from this node.", "inputSchema": {"type": "object", "properties": {"after_sequence": {"type": "integer", "minimum": 0, "default": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 1000}}, "additionalProperties": False}},
            {"name": "cortex_sync_push", "description": "Apply versioned shared-memory mutations with conflict resolution.", "inputSchema": {"type": "object", "properties": {"mutations": {"type": "array", "items": {"type": "object"}}}, "required": ["mutations"], "additionalProperties": False}},
            {"name": "cortex_worker_register", "description": "Register a worker. Remote identity is always the authenticated principal.", "inputSchema": {"type": "object", "properties": {"node_id": {"type": "string", "minLength": 1}, "capabilities": {"type": "array", "items": {"type": "string"}}, "metadata": {"type": "object"}}, "required": ["capabilities"], "additionalProperties": False}},
            {"name": "cortex_worker_claim", "description": "Claim the next task compatible with the authenticated worker.", "inputSchema": {"type": "object", "properties": {"node_id": {"type": "string", "minLength": 1}}, "additionalProperties": False}},
            {"name": "cortex_worker_complete", "description": "Complete a leased task using its fencing token.", "inputSchema": {"type": "object", "properties": {"node_id": {"type": "string", "minLength": 1}, "task_id": {"type": "string", "minLength": 1}, "lease_token": {"type": "string", "minLength": 1}, "result": {"type": "object"}}, "required": ["task_id", "lease_token", "result"], "additionalProperties": False}},
        ]

    async def call_as(self, principal: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not principal.strip():
            raise PermissionError("authenticated principal is required")
        scoped = dict(arguments)
        if name.startswith("cortex_worker_"):
            supplied = scoped.get("node_id")
            if supplied is not None and str(supplied) != principal:
                raise PermissionError("worker node_id must match the authenticated principal")
            scoped["node_id"] = principal
        return await self.call(name, scoped)

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        validate_tool_call(self.tools(), name, arguments)
        if name == "cortex_sync_pull":
            rows = self.memory.export(int(arguments.get("after_sequence", 0)), int(arguments.get("limit", 1000)))
            return {"node_id": self.node_id, "changes": [{"sequence": sequence, "mutation": mutation.to_dict()} for sequence, mutation in rows]}
        if name == "cortex_sync_push":
            raw = arguments.get("mutations", [])
            assert isinstance(raw, list)
            result = self.memory.apply([MemoryMutation.from_dict(item) for item in raw if isinstance(item, dict)])
            return {"applied": result.applied, "ignored": result.ignored, "conflicts": result.conflicts}
        if name == "cortex_worker_register":
            node_id = str(arguments.get("node_id") or self.node_id)
            raw_capabilities = arguments.get("capabilities", [])
            assert isinstance(raw_capabilities, list)
            raw_metadata = arguments.get("metadata", {})
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            worker = self.workers.register_worker(node_id, tuple(str(item) for item in raw_capabilities), metadata)
            return {"node_id": worker.node_id, "capabilities": list(worker.capabilities), "last_seen": worker.last_seen}
        if name == "cortex_worker_claim":
            node_id = str(arguments.get("node_id") or self.node_id)
            task = self.workers.claim(node_id)
            if task is None:
                return {"task": None}
            return {"task": {"task_id": task.task_id, "kind": task.kind, "payload": task.payload, "attempts": task.attempts, "lease_token": task.lease_token}}
        if name == "cortex_worker_complete":
            node_id = str(arguments.get("node_id") or self.node_id)
            raw_result = arguments.get("result", {})
            task_result: dict[str, object] = raw_result if isinstance(raw_result, dict) else {}
            completed = self.workers.complete(str(arguments["task_id"]), node_id, task_result, lease_token=str(arguments["lease_token"]))
            return {"task_id": completed.task_id, "status": completed.status}
        return await self.base.call(name, arguments)
