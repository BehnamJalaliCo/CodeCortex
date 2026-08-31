from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from codecortex.distributed.memory_sync import (
    MemoryMutation,
    SharedMemoryReplica,
    compare_clocks,
    merge_clocks,
)
from codecortex.distributed.remote_mcp import (
    BearerTokenAuthenticator,
    RemoteAccessPolicy,
    RemoteMCPClient,
    RemoteMCPServer,
    RemoteMCPSettings,
)
from codecortex.distributed.vector_store import (
    SQLiteVectorStore,
    VectorMatch,
    open_vector_store,
    register_vector_store_provider,
)


def test_vector_clock_relations_and_shared_memory_sync(tmp_path: Path) -> None:
    assert compare_clocks({}, {}) == "equal"
    assert compare_clocks({"a": 1}, {"a": 2}) == "before"
    assert compare_clocks({"a": 2}, {"a": 1}) == "after"
    assert compare_clocks({"a": 2}, {"b": 1}) == "concurrent"
    assert merge_clocks({"a": 1}, {"a": 2, "b": 1}) == {"a": 2, "b": 1}

    a = SharedMemoryReplica(tmp_path / "a.db", "a")
    b = SharedMemoryReplica(tmp_path / "b.db", "b")
    first = a.put("project", "decision", "use sqlite")
    assert a.value("project", "decision") == "use sqlite"
    exported = a.export()
    assert exported[0][1] == first
    assert a.export(after_sequence=exported[-1][0]) == []

    result = b.apply([mutation for _, mutation in exported])
    assert result.applied == 1 and result.conflicts == 0
    assert b.value("project", "decision") == "use sqlite"
    assert b.apply([first]).ignored == 1

    local_a = a.put("project", "decision", "A choice")
    local_b = b.put("project", "decision", "B choice")
    assert compare_clocks(local_a.clock, local_b.clock) == "concurrent"
    forced_b = MemoryMutation(
        local_b.namespace,
        local_b.key,
        local_b.value,
        local_b.node_id,
        local_b.clock,
        "9999-01-01T00:00:00+00:00",
    )
    conflict = a.apply([forced_b])
    assert conflict.conflicts == 1 and conflict.applied == 1
    assert a.value("project", "decision") == "B choice"
    merged = a.get("project", "decision")
    assert merged and merged.clock == {"a": 2, "b": 1}

    older = MemoryMutation(
        "project", "decision", "old", "old", {"a": 1}, "2000-01-01T00:00:00+00:00"
    )
    assert a.apply([older]).ignored == 1
    tombstone = a.delete("project", "decision")
    assert tombstone.tombstone and a.value("project", "decision") is None
    assert MemoryMutation.from_dict(tombstone.to_dict()) == tombstone
    with pytest.raises(ValueError):
        MemoryMutation.from_dict({**tombstone.to_dict(), "clock": "bad"})
    with pytest.raises(ValueError):
        SharedMemoryReplica(tmp_path / "bad.db", "")
    with pytest.raises(ValueError):
        a.put("", "x", "y")


def test_persistent_vector_store_and_provider_registry(tmp_path: Path) -> None:
    path = tmp_path / "vectors.db"
    store = SQLiteVectorStore(path)
    store.upsert("repo", "auth", [1.0, 0.0], {"path": "auth.py"})
    store.upsert("repo", "payments", [0.0, 1.0], {"path": "payments.py"})
    store.upsert("repo", "mixed", [1.0, 1.0], {"path": "mixed.py"})
    store.upsert("other", "auth", [1.0, 0.0], {})
    assert store.count("repo") == 3
    matches = store.search("repo", [1.0, 0.0], 2)
    assert [item.key for item in matches] == ["auth", "mixed"]
    assert matches[0].score == pytest.approx(1.0)
    assert matches[0].payload == {"path": "auth.py"}

    reopened = SQLiteVectorStore(path)
    assert reopened.count("repo") == 3
    reopened.upsert("repo", "auth", [1.0, 0.0], {"updated": True})
    assert reopened.search("repo", [1.0, 0.0], 1)[0].payload == {"updated": True}
    assert reopened.delete("repo", "payments")
    assert not reopened.delete("repo", "missing")
    assert reopened.count("repo") == 2
    reopened.upsert("repo", "3d", [1.0, 0.0, 0.0])
    assert "3d" not in {match.key for match in reopened.search("repo", [1.0, 0.0], 10)}

    assert isinstance(open_vector_store(path), SQLiteVectorStore)
    assert isinstance(open_vector_store(str(path)), SQLiteVectorStore)
    uri_store = open_vector_store(f"sqlite://{path}")
    assert isinstance(uri_store, SQLiteVectorStore)

    class FakeStore:
        def upsert(self, namespace: str, key: str, vector: list[float], payload=None) -> None:
            del namespace, key, vector, payload

        def delete(self, namespace: str, key: str) -> bool:
            del namespace, key
            return False

        def search(self, namespace: str, vector: list[float], limit: int = 10) -> list[VectorMatch]:
            del namespace, vector, limit
            return []

        def count(self, namespace: str) -> int:
            del namespace
            return 7

    register_vector_store_provider("fake", lambda uri: FakeStore())
    assert open_vector_store("fake://cluster/collection").count("x") == 7
    with pytest.raises(ValueError, match="cannot replace sqlite"):
        register_vector_store_provider("sqlite", lambda uri: FakeStore())
    with pytest.raises(ValueError, match="unknown vector store provider"):
        open_vector_store("missing://cluster")
    for vector in ([], [0.0, 0.0], [float("nan"), 1.0]):
        with pytest.raises(ValueError):
            store.upsert("repo", "invalid", vector)
    with pytest.raises(ValueError):
        store.upsert("", "x", [1.0])


def test_remote_auth_policy_quota_and_live_client() -> None:
    auth = BearerTokenAuthenticator({"agent": "secret", "admin": "admin-token"})
    assert auth.authenticate(None) is None
    assert auth.authenticate("Basic secret") is None
    assert auth.authenticate("Bearer wrong") is None
    assert auth.authenticate("Bearer secret") == "agent"
    with pytest.raises(ValueError):
        BearerTokenAuthenticator({})

    policy = RemoteAccessPolicy(
        allowed_tools={"agent": frozenset({"echo"}), "admin": frozenset({"*"})},
        denied_tools=frozenset({"danger"}),
    )
    assert policy.allows("agent", "echo")
    assert not policy.allows("agent", "other")
    assert policy.allows("admin", "other")
    assert not policy.allows("admin", "danger")

    quota_server = RemoteMCPServer(
        lambda tool, args: {"tool": tool, **args},
        auth,
        policy,
        RemoteMCPSettings(max_requests_per_minute=1),
    )
    assert quota_server.handle_call(None, {"tool": "echo"})[0] == 401
    assert quota_server.handle_call("Bearer secret", {"tool": "other"})[0] == 403
    assert quota_server.handle_call("Bearer secret", {"tool": "echo", "arguments": []})[0] == 400
    status, payload = quota_server.handle_call(
        "Bearer secret", {"tool": "echo", "arguments": {"value": 1}}
    )
    assert status == 200 and payload["result"]["value"] == 1
    assert quota_server.handle_call("Bearer secret", {"tool": "echo"})[0] == 429

    async def dispatcher(tool: str, args: dict[str, object]) -> dict[str, object]:
        return {"tool": tool, "arguments": args}

    server = RemoteMCPServer(
        dispatcher,
        BearerTokenAuthenticator({"agent": "secret"}),
        RemoteAccessPolicy(allowed_tools={"agent": frozenset({"echo"})}),
        RemoteMCPSettings(host="127.0.0.1", port=0, max_requests_per_minute=10),
    )
    address = server.start()
    host, port = address
    assert server.address == address
    with urlopen(f"http://{host}:{port}/health", timeout=5) as response:
        assert json.loads(response.read()) == {"status": "ok"}
    client = RemoteMCPClient(f"http://{host}:{port}", "secret")
    result = client.call("echo", {"hello": "world"})
    assert result == {"tool": "echo", "arguments": {"hello": "world"}}
    with pytest.raises(RuntimeError, match="401"):
        RemoteMCPClient(f"http://{host}:{port}", "wrong").call("echo")
    with pytest.raises(HTTPError):
        urlopen(f"http://{host}:{port}/missing", timeout=5)
    server.close()
    server.close()

    with pytest.raises(ValueError, match="configured together"):
        RemoteMCPSettings(tls_cert="cert.pem")
    with pytest.raises(ValueError):
        RemoteMCPSettings(port=70000)
    with pytest.raises(ValueError):
        RemoteMCPSettings(max_requests_per_minute=0)
