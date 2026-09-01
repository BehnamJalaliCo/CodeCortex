import json

import pytest

from codecortex.config import CortexConfig
from codecortex.runtime import build_runtime


def test_runtime_loads_project_config(tmp_path) -> None:
    state = tmp_path / ".codecortex"
    state.mkdir()
    (state / "config.json").write_text(
        json.dumps({"version": 1, "context_budget": 4096, "hard_context_limit": 8192, "telemetry": False}),
        encoding="utf-8",
    )
    runtime = build_runtime(tmp_path)
    assert runtime.config.default_context_budget == 4096
    assert runtime.config.hard_context_limit == 8192
    assert runtime.router.default_budget == 4096
    assert runtime.telemetry.enabled is False


def test_environment_overrides_project_config(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    state = tmp_path / ".codecortex"
    state.mkdir()
    (state / "config.json").write_text(
        json.dumps({"context_budget": 4096, "hard_context_limit": 8192}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODECORTEX_CONTEXT_BUDGET", "6000")
    monkeypatch.setenv("CODECORTEX_HARD_CONTEXT_LIMIT", "10000")
    config = CortexConfig.load(tmp_path)
    assert config.default_context_budget == 6000
    assert config.hard_context_limit == 10000


def test_hard_context_limit_is_enforced(tmp_path) -> None:
    with pytest.raises(ValueError):
        CortexConfig(project_root=tmp_path, default_context_budget=9000, hard_context_limit=8000)
    config = CortexConfig(project_root=tmp_path, default_context_budget=4000, hard_context_limit=8000)
    assert config.validate_budget(8000) == 8000
    with pytest.raises(ValueError):
        config.validate_budget(8001)
