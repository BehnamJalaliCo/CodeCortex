"""High-fidelity repository graph backend adapter."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from codecortex.backends.base import ManagedAdapterMixin
from codecortex.backends.manager import BackendManager
from codecortex.backends.spec import BACKENDS
from codecortex.core.contracts import Engine
from codecortex.core.models import AgentRequest, Capability, ContextChunk, EngineResult


class GraphBackendAdapter(ManagedAdapterMixin, Engine):
    capability = Capability.REPOSITORY

    def __init__(self, project_root: Path, manager: BackendManager | None = None) -> None:
        self.project_root = project_root.resolve()
        self.manager = manager or BackendManager()
        self.spec = BACKENDS["graph"]

    async def health(self) -> bool:
        return await asyncio.to_thread(self.manager.probe, self.spec, False)

    def build(self) -> dict[str, Any]:
        self.manager.run(self.spec, (".",), cwd=self.project_root)
        graph_path = self.project_root / "graphify-out" / "graph.json"
        if not graph_path.exists():
            raise RuntimeError("graph backend completed without graph.json")
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("graph backend emitted an invalid graph payload")
        return payload

    def query(self, query: str) -> str:
        return self.manager.run(
            self.spec,
            ("query", query),
            cwd=self.project_root,
            timeout_seconds=90,
        ).stdout.strip()

    def explain(self, node: str) -> str:
        return self.manager.run(
            self.spec,
            ("explain", node),
            cwd=self.project_root,
            timeout_seconds=60,
        ).stdout.strip()

    def path(self, source: str, target: str) -> str:
        return self.manager.run(
            self.spec,
            ("path", source, target),
            cwd=self.project_root,
            timeout_seconds=60,
        ).stdout.strip()

    async def execute(self, request: AgentRequest) -> EngineResult:
        return await asyncio.to_thread(self._execute_sync, request)

    def _execute_sync(self, request: AgentRequest) -> EngineResult:
        mode = str(request.metadata.get("graph_mode", "query"))
        if mode == "build":
            content = json.dumps(self.build(), ensure_ascii=False)
        elif mode == "explain":
            content = self.explain(request.query)
        elif mode == "path":
            target = str(request.metadata.get("target", "")).strip()
            if not target:
                raise ValueError("graph path mode requires metadata.target")
            content = self.path(request.query, target)
        else:
            content = self.query(request.query)
        tokens = max(1, len(content) // 4) if content else 0
        return EngineResult(
            capability=self.capability,
            content=content,
            chunks=[
                ContextChunk(
                    source="repository-graph",
                    content=content,
                    tokens=tokens,
                    relevance=0.95,
                    metadata={"backend": self.spec.key, "revision": self.spec.revision},
                )
            ]
            if content
            else [],
            metadata={"backend": self.spec.key, "revision": self.spec.revision},
        )
