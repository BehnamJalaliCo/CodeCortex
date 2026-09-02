from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from codecortex.distributed.organization import AuditLog, OrganizationPolicyStore
from codecortex.distributed.performance import PerformanceHistoryStore
from codecortex.distributed.workers import WorkerCoordinator


def test_worker_coordinator_capabilities_leases_and_results(tmp_path: Path) -> None:
    coordinator = WorkerCoordinator(tmp_path / "workers.db")
    indexer = coordinator.register_worker("index-1", ("index",), {"region": "us-east"})
    retriever = coordinator.register_worker(
        "retrieve-1", ("retrieve", "vector"), {"region": "eu-central"}
    )
    assert indexer.capabilities == ("index",)
    assert retriever.capabilities == ("retrieve", "vector")
    assert len(coordinator.workers()) == 2
    assert len(coordinator.workers(active_within_seconds=60)) == 2
    with pytest.raises(ValueError):
        coordinator.register_worker("", ("index",))
    with pytest.raises(ValueError):
        coordinator.register_worker("node", ())
    with pytest.raises(KeyError):
        coordinator.heartbeat("missing")

    retrieval = coordinator.enqueue(
        "retrieve",
        {"query": "auth"},
        required_capabilities=("retrieve", "vector"),
        task_id="task-retrieve",
    )
    indexing = coordinator.enqueue(
        "index", {"path": "."}, required_capabilities=("index",), task_id="task-index"
    )
    assert retrieval.status == indexing.status == "queued"
    assert coordinator.claim("index-1") == coordinator.get_task("task-index")
    assert coordinator.claim("index-1") is None
    claimed = coordinator.claim("retrieve-1", lease_seconds=30)
    assert claimed and claimed.task_id == "task-retrieve"
    assert claimed.assigned_to == "retrieve-1" and claimed.attempts == 1
    coordinator.renew_lease(claimed.task_id, "retrieve-1", lease_seconds=30)
    completed = coordinator.complete(claimed.task_id, "retrieve-1", {"hits": 3})
    assert completed.status == "completed" and completed.result == {"hits": 3}
    with pytest.raises(RuntimeError):
        coordinator.complete(claimed.task_id, "retrieve-1", {})

    claimed_index = coordinator.get_task("task-index")
    assert claimed_index and claimed_index.status == "leased"
    failed = coordinator.fail("task-index", "index-1", "parser failed")
    assert failed.status == "failed" and failed.error == "parser failed"
    assert len(coordinator.list_tasks("failed")) == 1
    assert len(coordinator.list_tasks()) == 2

    expiring = coordinator.enqueue(
        "index", {}, required_capabilities=("index",), task_id="expiring"
    )
    assert expiring.status == "queued"
    leased = coordinator.claim("index-1", lease_seconds=30)
    assert leased and leased.task_id == "expiring"
    with coordinator._connect() as connection:
        connection.execute(
            "UPDATE tasks SET lease_expires_at = ? WHERE task_id = ?",
            ((datetime.now(UTC) - timedelta(minutes=1)).isoformat(), "expiring"),
        )
    assert coordinator.requeue_expired() == 1
    reclaimed = coordinator.claim("index-1")
    assert reclaimed and reclaimed.task_id == "expiring" and reclaimed.attempts == 2
    with pytest.raises(RuntimeError):
        coordinator.renew_lease("missing", "index-1")
    with pytest.raises(ValueError):
        coordinator.enqueue("", {})


def test_performance_history_persistence_trends_and_export(tmp_path: Path) -> None:
    store = PerformanceHistoryStore(tmp_path / "performance.db")
    first = store.record(
        "a" * 40,
        "production",
        {"latency_ms": 100.0, "throughput": 10, "unknown": None},
        recorded_at="2026-01-01T00:00:00+00:00",
        snapshot_id="one",
    )
    second = store.record(
        "b" * 40,
        "production",
        {"latency_ms": 80.0, "throughput": 15},
        metadata={"runner": "ci"},
        recorded_at="2026-01-02T00:00:00+00:00",
        snapshot_id="two",
    )
    assert first.snapshot_id == "one" and second.metadata == {"runner": "ci"}
    assert [item.snapshot_id for item in store.history("production")] == ["two", "one"]
    trend = store.trend("production", "latency_ms")
    assert trend.samples == 2
    assert trend.first == 100.0 and trend.latest == 80.0
    assert trend.minimum == 80.0 and trend.maximum == 100.0
    assert trend.average == 90.0 and trend.change_percent == pytest.approx(-20.0)
    assert store.trend("production", "missing").samples == 0

    zero = store.record(
        "c" * 40,
        "zero",
        {"metric": 0},
        recorded_at="2026-01-01T00:00:00+00:00",
        snapshot_id="zero-one",
    )
    assert zero.metrics["metric"] == 0
    store.record(
        "d" * 40,
        "zero",
        {"metric": 1},
        recorded_at="2026-01-02T00:00:00+00:00",
        snapshot_id="zero-two",
    )
    assert store.trend("zero", "metric").change_percent is None

    exported = store.export_json(tmp_path / "history.json")
    imported = PerformanceHistoryStore(tmp_path / "imported.db")
    assert imported.import_json(exported) == 4
    assert len(imported.history()) == 4
    with pytest.raises(ValueError):
        store.record("", "suite", {})
    with pytest.raises(TypeError):
        store.record("commit", "suite", {"bad": "text"})  # type: ignore[dict-item]

    bad = tmp_path / "bad.json"
    bad.write_text('{"snapshots": {}}', encoding="utf-8")
    with pytest.raises(ValueError):
        imported.import_json(bad)


def test_organization_workspace_policy_and_audit_retention(tmp_path: Path) -> None:
    path = tmp_path / "organization.db"
    store = OrganizationPolicyStore(path, audit_retention_days=30)
    store.create_organization("acme", "Acme Engineering", owner="alice")
    assert store.role("acme", "alice") == "owner"
    assert store.role("acme", "nobody") is None
    store.set_member("acme", "alice", "bob", "admin")
    store.set_member("acme", "bob", "carol", "member")
    assert store.role("acme", "bob") == "admin"
    with pytest.raises(PermissionError):
        store.set_member("acme", "carol", "dave", "member")

    store.create_workspace("acme", "bob", "payments", project_root="/srv/payments")
    policy = store.set_policy(
        "acme",
        "bob",
        "payments",
        allowed_tools=("semantic", "impact"),
        max_context_tokens=100_000,
        remote_access=True,
        metadata={"classification": "internal"},
    )
    assert policy.remote_access and policy.max_context_tokens == 100_000
    loaded = store.policy("acme", "payments")
    assert loaded == policy
    assert store.policy("acme", "missing") is None
    assert store.authorize_tool("acme", "payments", "carol", "semantic", remote=True)
    assert not store.authorize_tool("acme", "payments", "carol", "delete", remote=True)
    assert not store.authorize_tool("acme", "payments", "outsider", "semantic", remote=True)

    locked = store.set_policy(
        "acme", "alice", "payments", allowed_tools=("semantic",), remote_access=False
    )
    assert not locked.remote_access
    assert not store.authorize_tool("acme", "payments", "carol", "semantic", remote=True)
    assert store.authorize_tool("acme", "payments", "carol", "semantic", remote=False)
    with pytest.raises(ValueError):
        store.set_policy("acme", "alice", "payments", max_context_tokens=0)
    with pytest.raises(ValueError):
        store.create_organization("", "bad", owner="alice")
    with pytest.raises(ValueError):
        store.create_workspace("acme", "alice", "")

    events = store.audit.query("acme")
    assert events and any(event.action == "workspace.policy.update" for event in events)
    assert store.audit.query("acme", actor="carol")
    assert store.audit.query("acme", workspace="payments")

    old_time = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    store.audit.record(
        "acme",
        "alice",
        "old.event",
        "old",
        created_at=old_time,
        metadata={"old": True},
    )
    assert store.audit.prune() >= 1
    assert not any(event.action == "old.event" for event in store.audit.query("acme"))
    with pytest.raises(ValueError):
        AuditLog(tmp_path / "bad-retention.db", retention_days=0)
