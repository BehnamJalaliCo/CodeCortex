from __future__ import annotations

from pathlib import Path

import pytest

from codecortex.distributed.service import DistributedMCPApplication
from codecortex.runtime import build_runtime


@pytest.mark.asyncio
async def test_distributed_mcp_sync_and_worker_tools(tmp_path: Path) -> None:
    runtime = build_runtime(tmp_path)
    application = DistributedMCPApplication(runtime, node_id="coordinator")
    names = {tool["name"] for tool in application.tools()}
    assert {
        "cortex_sync_pull",
        "cortex_sync_push",
        "cortex_worker_register",
        "cortex_worker_claim",
        "cortex_worker_complete",
        "cortex_semantic_search",
    }.issubset(names)

    mutation = application.memory.put("project", "decision", "distributed")
    pulled = await application.call("cortex_sync_pull", {"after_sequence": 0})
    assert pulled["node_id"] == "coordinator"
    assert pulled["changes"][0]["mutation"]["value"] == "distributed"

    pushed = await application.call(
        "cortex_sync_push", {"mutations": [mutation.to_dict()]}
    )
    assert pushed["ignored"] == 1
    with pytest.raises(ValueError):
        await application.call("cortex_sync_push", {"mutations": "bad"})

    registered = await application.call(
        "cortex_worker_register",
        {"node_id": "worker-1", "capabilities": ["index"], "metadata": {"zone": "a"}},
    )
    assert registered["node_id"] == "worker-1"
    with pytest.raises(ValueError):
        await application.call(
            "cortex_worker_register", {"node_id": "worker-2", "capabilities": "bad"}
        )

    task = application.workers.enqueue(
        "index", {"path": "."}, required_capabilities=("index",), task_id="job-1"
    )
    assert task.status == "queued"
    claimed = await application.call("cortex_worker_claim", {"node_id": "worker-1"})
    assert claimed["task"]["task_id"] == "job-1"
    empty = await application.call("cortex_worker_claim", {"node_id": "worker-1"})
    assert empty == {"task": None}
    completed = await application.call(
        "cortex_worker_complete",
        {"node_id": "worker-1", "task_id": "job-1", "result": {"files": 10}},
    )
    assert completed == {"task_id": "job-1", "status": "completed"}
