import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from codecortex.distributed.organization import OrganizationPolicyStore
from codecortex.distributed.remote_mcp import BearerTokenAuthenticator, RemoteAccessPolicy, RemoteMCPServer
from codecortex.distributed.service import DistributedMCPApplication
from codecortex.distributed.workers import WorkerCoordinator
from codecortex.runtime import build_runtime


def test_fencing_token_rejects_stale_completion(tmp_path) -> None:
    coordinator = WorkerCoordinator(tmp_path / "workers.db")
    coordinator.register_worker("worker", ("index",))
    coordinator.enqueue("index", {}, required_capabilities=("index",), task_id="t")
    first = coordinator.claim("worker", lease_seconds=30)
    assert first and first.lease_token
    with coordinator._connect() as connection:
        connection.execute("UPDATE tasks SET lease_expires_at = ? WHERE task_id = 't'", ((datetime.now(UTC) - timedelta(minutes=1)).isoformat(),))
    coordinator.requeue_expired()
    second = coordinator.claim("worker", lease_seconds=30)
    assert second and second.lease_token and second.lease_token != first.lease_token
    with pytest.raises(RuntimeError):
        coordinator.complete("t", "worker", {}, lease_token=first.lease_token)
    assert coordinator.complete("t", "worker", {"ok": True}, lease_token=second.lease_token).status == "completed"


def test_remote_dispatch_receives_authenticated_principal() -> None:
    seen = {}
    async def dispatcher(tool, arguments, principal):
        seen["principal"] = principal
        return {"ok": True}
    server = RemoteMCPServer(dispatcher, BearerTokenAuthenticator({"worker-a": "secret"}), RemoteAccessPolicy(allowed_tools={"worker-a": frozenset({"read"})}))
    status, _ = server.handle_call("Bearer secret", {"tool": "read", "arguments": {}})
    assert status == 200
    assert seen["principal"] == "worker-a"


def test_remote_worker_identity_cannot_be_spoofed(tmp_path) -> None:
    app = DistributedMCPApplication(build_runtime(tmp_path), node_id="coordinator")
    with pytest.raises(PermissionError):
        asyncio.run(app.call_as("worker-a", "cortex_worker_register", {"node_id": "worker-b", "capabilities": ["index"]}))
    result = asyncio.run(app.call_as("worker-a", "cortex_worker_register", {"capabilities": ["index"]}))
    assert result["node_id"] == "worker-a"


def test_organization_policy_is_in_remote_authorization_path(tmp_path) -> None:
    store = OrganizationPolicyStore(tmp_path / "org.db")
    store.create_organization("acme", "Acme", owner="alice")
    store.create_workspace("acme", "alice", "repo")
    store.set_policy("acme", "alice", "repo", allowed_tools=("read",), remote_access=True)
    policy = RemoteAccessPolicy(
        allowed_tools={"alice": frozenset({"read", "write"})},
        authorizer=lambda principal, tool: store.authorize_tool("acme", "repo", principal, tool, remote=True),
    )
    assert policy.allows("alice", "read")
    assert not policy.allows("alice", "write")
