"""Distributed MCP application that composes the local MCP surface with cluster tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codecortex.distributed.memory_sync import MemoryMutation, SharedMemoryReplica
from codecortex.distributed.workers import WorkerCoordinator
from codecortex.mcp.server import MCPApplication
from codecortex.runtime import CortexRuntime


class DistributedMCPApplication:
    """Add memory replication and worker coordination to the standard MCP application."""

    def __init__(
        self,
        runtime: CortexRuntime,
        *,
        node_id: str,
        state_dir: Path | None = None,
    ) -> None:
        self.base = MCPApplication(runtime)
        root = state_dir or runtime.config.state_dir / "distributed"
        root.mkdir(parents=True, exist_ok=True)
        self.memory = SharedMemoryReplica(root / "shared-memory.db", node_id)
        self.workers = WorkerCoordinator(root / "workers.db")
        self.node_id = node_id

    def tools(self) -> list[dict[str, Any]]:
        return [
            *self.base.tools(),
            {
                "name": "cortex_sync_pull",
                "description": "Pull versioned shared-memory mutations from this node.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "after_sequence": {"type": "integer", "minimum": 0, "default": 0},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 1000},
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "cortex_sync_push",
                "description": "Apply versioned shared-memory mutations with conflict resolution.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"mutations": {"type": "array"}},
                    "required": ["mutations"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "cortex_worker_register",
                "description": "Register or heartbeat an indexing/retrieval worker node.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string", "minLength": 1},
                        "capabilities": {"type": "array", "items": {"type": "string"}},
                        "metadata": {"type": "object"},
                    },
                    "required": ["node_id", "capabilities"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "cortex_worker_claim",
                "description": "Claim the next task compatible with a worker's capabilities.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"node_id": {"type": "string", "minLength": 1}},
                    "required": ["node_id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "cortex_worker_complete",
                "description": "Complete a leased distributed task.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string", "minLength": 1},
                        "task_id": {"type": "string", "minLength": 1},
                        "result": {"type": "object"},
                    },
                    "required": ["node_id", "task_id", "result"],
                    "additionalProperties": False,
                },
            },
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "cortex_sync_pull":
            rows = self.memory.export(
                int(arguments.get("after_sequence", 0)), int(arguments.get("limit", 1000))
            )
            return {
                "node_id": self.node_id,
                "changes": [
                    {"sequence": sequence, "mutation": mutation.to_dict()}
                    for sequence, mutation in rows
                ],
            }
        if name == "cortex_sync_push":
            raw = arguments.get("mutations", [])
            if not isinstance(raw, list):
                raise ValueError("mutations must be a list")
            mutations = [
                MemoryMutation.from_dict(item)
                for item in raw
                if isinstance(item, dict)
            ]
            result = self.memory.apply(mutations)
            return {
                "applied": result.applied,
                "ignored": result.ignored,
                "conflicts": result.conflicts,
            }
        if name == "cortex_worker_register":
            raw_capabilities = arguments.get("capabilities", [])
            if not isinstance(raw_capabilities, list):
                raise ValueError("capabilities must be a list")
            raw_metadata = arguments.get("metadata", {})
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            worker = self.workers.register_worker(
                str(arguments["node_id"]),
                tuple(str(item) for item in raw_capabilities),
                metadata,
            )
            return {
                "node_id": worker.node_id,
                "capabilities": list(worker.capabilities),
                "last_seen": worker.last_seen,
            }
        if name == "cortex_worker_claim":
            task = self.workers.claim(str(arguments["node_id"]))
            if task is None:
                return {"task": None}
            return {
                "task": {
                    "task_id": task.task_id,
                    "kind": task.kind,
                    "payload": task.payload,
                    "attempts": task.attempts,
                }
            }
        if name == "cortex_worker_complete":
            raw_result = arguments.get("result", {})
            result = raw_result if isinstance(raw_result, dict) else {}
            task = self.workers.complete(
                str(arguments["task_id"]), str(arguments["node_id"]), result
            )
            return {"task_id": task.task_id, "status": task.status}
        return await self.base.call(name, arguments)
