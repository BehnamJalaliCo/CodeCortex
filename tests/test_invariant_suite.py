from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from codecortex.distributed.memory_sync import SharedMemoryReplica
from codecortex.distributed.workers import WorkerCoordinator
from codecortex.indexing.graph import ProjectGraph
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.indexing.indexer import ProjectIndexer
from codecortex.mcp.server import MCPApplication, MCPServer
from codecortex.runtime import build_runtime
from codecortex.state import AtomicJsonFile, FileMutex


def _edges(graph):
    return {(edge.source, edge.target, edge.kind) for edge in graph.edges}


def test_incremental_property_matches_full_rebuild_across_change_sequences(tmp_path) -> None:
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    c = tmp_path / "c.py"
    a.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    b.write_text("def beta():\n    return alpha()\n", encoding="utf-8")
    c.write_text("def gamma():\n    return beta()\n", encoding="utf-8")
    index = IncrementalGraphIndex(tmp_path)
    index.refresh()

    mutations = [
        "# shift\ndef alpha():\n    return 2\n",
        "def alpha():\n    return 3\n\ndef extra():\n    return alpha()\n",
        "def alpha():\n    return 4\n",
    ]
    for source in mutations:
        a.write_text(source, encoding="utf-8")
        incremental, _ = index.refresh()
        full = ProjectIndexer(tmp_path).build()
        assert {node.id for node in incremental.nodes} == {node.id for node in full.nodes}
        assert _edges(incremental) == _edges(full)


def test_corrupt_json_state_recovers_without_propagating_corruption(tmp_path) -> None:
    path = tmp_path / "graph.json"
    path.write_text("{broken", encoding="utf-8")
    assert ProjectGraph.load(path) == ProjectGraph()
    state = AtomicJsonFile(path)
    state.update(lambda current: {"healthy": True}, default={})
    assert state.read({}) == {"healthy": True}


def test_stale_filesystem_lock_is_recovered(tmp_path) -> None:
    lock_path = tmp_path / ".state.lock"
    lock_path.mkdir()
    marker = lock_path / "owner.json"
    marker.write_text("{}", encoding="utf-8")
    old = datetime.now(UTC).timestamp() - 600
    import os
    os.utime(lock_path, (old, old))
    lock = FileMutex(lock_path, timeout_seconds=1, stale_seconds=1)
    with lock:
        assert lock_path.exists()
    assert not lock_path.exists()


def test_multi_node_memory_conflicts_converge(tmp_path) -> None:
    left = SharedMemoryReplica(tmp_path / "left.db", "left")
    right = SharedMemoryReplica(tmp_path / "right.db", "right")
    left_mutation = left.put("project", "decision", "left-value")
    right_mutation = right.put("project", "decision", "right-value")
    left.apply([right_mutation])
    right.apply([left_mutation])
    # Exchange conflict-resolved mutations once more; replicas must converge.
    left_changes = [mutation for _, mutation in left.export()]
    right_changes = [mutation for _, mutation in right.export()]
    left.apply(right_changes)
    right.apply(left_changes)
    assert left.value("project", "decision") == right.value("project", "decision")
    assert left.get("project", "decision").clock == right.get("project", "decision").clock  # type: ignore[union-attr]


def test_worker_lease_survives_restart_and_expired_lease_is_recoverable(tmp_path) -> None:
    path = tmp_path / "workers.db"
    first = WorkerCoordinator(path)
    first.register_worker("worker", ("index",))
    first.enqueue("index", {}, required_capabilities=("index",), task_id="task")
    leased = first.claim("worker")
    assert leased and leased.lease_token

    restarted = WorkerCoordinator(path)
    persisted = restarted.get_task("task")
    assert persisted and persisted.status == "leased" and persisted.lease_token == leased.lease_token
    with restarted._connect() as connection:
        connection.execute(
            "UPDATE tasks SET lease_expires_at = ? WHERE task_id = 'task'",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),),
        )
    assert restarted.requeue_expired() == 1
    reclaimed = restarted.claim("worker")
    assert reclaimed and reclaimed.attempts == 2 and reclaimed.lease_token != leased.lease_token


def test_adversarial_mcp_inputs_are_rejected_by_schema(tmp_path) -> None:
    server = MCPServer(MCPApplication(build_runtime(tmp_path)))
    cases = [
        {"name": "cortex_semantic_search", "arguments": {"query": "x", "limit": 0}},
        {"name": "cortex_context", "arguments": {"query": "x", "budget": "many"}},
        {"name": "cortex_symbol_history", "arguments": {"path": "x.py", "start": 0, "end": 2}},
        {"name": "cortex_find_symbol", "arguments": {"query": "x", "extra": "no"}},
    ]
    for index, params in enumerate(cases, 1):
        response = asyncio.run(server.dispatch({"jsonrpc": "2.0", "id": index, "method": "tools/call", "params": params}))
        assert response is not None
        assert response["error"]["code"] == -32602
