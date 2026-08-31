import pytest

from codecortex.runtime import build_runtime


@pytest.mark.asyncio
async def test_runtime_health(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    runtime = build_runtime(tmp_path)

    health = await runtime.gateway.health()

    assert health["repository"] is True
    assert health["symbols"] is True
    assert health["memory"] is True
    assert health["validation"] is True


@pytest.mark.asyncio
async def test_runtime_query_returns_context(tmp_path) -> None:
    (tmp_path / "auth.py").write_text(
        "class AuthManager:\n    def refresh_token(self):\n        return True\n",
        encoding="utf-8",
    )
    runtime = build_runtime(tmp_path)

    result = await runtime.gateway.query("Find refresh_token in authentication code")

    assert result.context_tokens > 0
    assert any(engine.capability.value == "symbols" for engine in result.results)
