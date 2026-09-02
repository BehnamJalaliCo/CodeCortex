"""Cluster-level scheduling and graph publication."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from codecortex.distributed.graph_store import DistributedGraphStore
from codecortex.distributed.workers import DistributedTask, WorkerCoordinator
from codecortex.indexing.graph import ProjectGraph


@dataclass(frozen=True, slots=True)
class ClusterStatus:
    workers: int
    active_workers: int
    queued: int
    leased: int
    completed: int
    failed: int
    graph_repositories: int


class ClusterCoordinator:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir.resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.workers = WorkerCoordinator(self.state_dir / "workers.db")
        self.graphs = DistributedGraphStore(self.state_dir / "graphs.db")

    def schedule_index(
        self,
        repository: str,
        paths: list[str],
        revision: str,
        *,
        shard_size: int = 5_000,
    ) -> list[DistributedTask]:
        if not repository.strip() or not revision.strip():
            raise ValueError("repository and revision are required")
        if shard_size < 1:
            raise ValueError("shard_size must be positive")
        tasks: list[DistributedTask] = []
        for offset in range(0, len(paths), shard_size):
            shard = paths[offset : offset + shard_size]
            tasks.append(
                self.workers.enqueue(
                    "index-shard",
                    {
                        "repository": repository,
                        "revision": revision,
                        "paths": shard,
                        "offset": offset,
                    },
                    required_capabilities=("index",),
                    task_id=f"index-{uuid.uuid4().hex}",
                )
            )
        return tasks

    def schedule_retrieval(
        self,
        query: str,
        repository: str,
        revision: str | None = None,
    ) -> DistributedTask:
        if not query.strip() or not repository.strip():
            raise ValueError("query and repository are required")
        payload: dict[str, object] = {"query": query, "repository": repository}
        if revision:
            payload["revision"] = revision
        return self.workers.enqueue(
            "retrieve",
            payload,
            required_capabilities=("retrieve",),
        )

    def publish_graph(self, repository: str, revision: str, graph: ProjectGraph) -> None:
        self.graphs.replace(repository, revision, graph)

    def status(self, *, active_within_seconds: float = 60.0) -> ClusterStatus:
        workers = self.workers.workers()
        return ClusterStatus(
            workers=len(workers),
            active_workers=len(self.workers.workers(active_within_seconds=active_within_seconds)),
            queued=len(self.workers.list_tasks("queued", 10_000)),
            leased=len(self.workers.list_tasks("leased", 10_000)),
            completed=len(self.workers.list_tasks("completed", 10_000)),
            failed=len(self.workers.list_tasks("failed", 10_000)),
            graph_repositories=len(self.graphs.repositories()),
        )
