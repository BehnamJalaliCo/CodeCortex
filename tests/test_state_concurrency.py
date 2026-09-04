from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from codecortex.distributed.memory_sync import SharedMemoryReplica
from codecortex.memory.json_store import JsonMemoryStore
from codecortex.state import AtomicJsonFile, FileMutex


def test_atomic_json_update_keeps_concurrent_writes(tmp_path) -> None:
    state = AtomicJsonFile(tmp_path / "state.json")
    state.write({})

    def write(index: int) -> None:
        def transform(current: object):
            data = dict(current) if isinstance(current, dict) else {}
            data[str(index)] = index
            return data

        state.update(transform, default={})

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write, range(40)))
    payload = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert len(payload) == 40



def test_file_mutex_retries_transient_permission_error(tmp_path, monkeypatch) -> None:
    mutex = FileMutex(tmp_path / ".state.lock", timeout_seconds=1.0)
    original_mkdir = Path.mkdir
    injected = False

    def flaky_mkdir(path: Path, *args, **kwargs):
        nonlocal injected
        if path == mutex.path and not injected:
            injected = True
            raise PermissionError("simulated Windows lock-directory race")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", flaky_mkdir)

    with mutex:
        assert mutex.path.is_dir()

    assert injected
    assert not mutex.path.exists()


def test_json_memory_namespaces_do_not_collide_and_writes_are_serialized(tmp_path) -> None:
    store = JsonMemoryStore(tmp_path / "memory")

    async def run() -> None:
        await asyncio.gather(
            *(store.put("a/b", f"k{i}", str(i)) for i in range(20)),
            *(store.put("a_b", f"x{i}", str(i)) for i in range(20)),
        )

    asyncio.run(run())
    assert len(store._load("a/b")) == 20
    assert len(store._load("a_b")) == 20
    assert store._path("a/b") != store._path("a_b")


def test_shared_memory_local_clock_increment_is_transactional(tmp_path) -> None:
    replica = SharedMemoryReplica(tmp_path / "shared.db", "node-a")

    def put(index: int) -> None:
        replica.put("project", "key", str(index))

    with ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(put, range(12)))
    mutation = replica.get("project", "key")
    assert mutation is not None
    assert mutation.clock["node-a"] == 12
