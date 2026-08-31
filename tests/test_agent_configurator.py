import json
from pathlib import Path

import pytest

from codecortex.integrations.agents import (
    AgentConfigurationError,
    AgentConfigurator,
    AgentTarget,
)


def test_json_agent_config_preserves_existing_settings(tmp_path: Path) -> None:
    target = tmp_path / ".mcp.json"
    target.write_text(json.dumps({"keep": True, "mcpServers": {"other": {"command": "x"}}}))
    result = AgentConfigurator(tmp_path).configure_one(AgentTarget.CLAUDE)
    payload = json.loads(target.read_text())
    assert result.changed is True
    assert result.backup is not None
    assert payload["keep"] is True
    assert payload["mcpServers"]["other"]["command"] == "x"
    assert payload["mcpServers"]["codecortex"]["command"] == "cortex"


def test_dry_run_does_not_create_file(tmp_path: Path) -> None:
    target = tmp_path / ".gemini" / "settings.json"
    result = AgentConfigurator(tmp_path).configure_one(AgentTarget.GEMINI, dry_run=True)
    assert result.changed is True
    assert not target.exists()


def test_codex_managed_block_is_idempotent(tmp_path: Path) -> None:
    configurator = AgentConfigurator(tmp_path)
    first = configurator.configure_one(AgentTarget.CODEX)
    second = configurator.configure_one(AgentTarget.CODEX)
    text = (tmp_path / ".codex" / "config.toml").read_text()
    assert first.changed is True
    assert second.changed is False
    assert text.count("[mcp_servers.codecortex]") == 1


def test_codex_refuses_unmanaged_collision(tmp_path: Path) -> None:
    path = tmp_path / ".codex" / "config.toml"
    path.parent.mkdir()
    path.write_text('[mcp_servers.codecortex]\ncommand = "something-else"\n')
    with pytest.raises(AgentConfigurationError):
        AgentConfigurator(tmp_path).configure_one(AgentTarget.CODEX)
