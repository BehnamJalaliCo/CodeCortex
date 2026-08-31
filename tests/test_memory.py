import pytest

from codecortex.memory import JsonMemoryStore


@pytest.mark.asyncio
async def test_memory_round_trip(tmp_path) -> None:
    store = JsonMemoryStore(tmp_path)

    await store.put("project", "database", "PostgreSQL is the primary database")

    assert await store.get("project", "database") == "PostgreSQL is the primary database"
    assert await store.search("project", "database") == ["PostgreSQL is the primary database"]
