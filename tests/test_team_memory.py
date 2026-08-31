import pytest

from codecortex.memory import RevisionConflict, TeamMemoryStore


@pytest.mark.asyncio
async def test_team_memory_versions_entries_and_supports_search(tmp_path) -> None:
    store = TeamMemoryStore(tmp_path / "team.sqlite3")
    first = store.put_entry(
        "project",
        "auth-decision",
        "Use rotating refresh tokens",
        actor="alice",
        tags=("auth", "security"),
        expected_revision=0,
    )
    second = store.put_entry(
        "project",
        "auth-decision",
        "Use rotating refresh tokens with reuse detection",
        actor="bob",
        tags=("auth", "security"),
        expected_revision=1,
    )
    assert first.revision == 1
    assert second.revision == 2
    assert await store.get("project", "auth-decision") == second.value
    assert "reuse detection" in (await store.search("project", "refresh tokens"))[0]
    assert len(store.history("project", "auth-decision")) == 2

    with pytest.raises(RevisionConflict):
        store.put_entry(
            "project",
            "auth-decision",
            "stale update",
            expected_revision=1,
        )
