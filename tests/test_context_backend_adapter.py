from pathlib import Path

from codecortex.backends.context import ContextBackendAdapter
from codecortex.backends.spec import BACKENDS


def test_context_backend_has_no_embedded_source() -> None:
    spec = BACKENDS["context"]
    assert spec.key == "context"
    assert {"compression", "mcp"}.issubset(spec.capabilities)
    assert not spec.configured


def test_context_backend_uses_project_workspace(tmp_path: Path) -> None:
    adapter = ContextBackendAdapter(tmp_path)
    client = adapter._client()
    assert client.server_args == ("mcp", "serve", "--transport", "stdio")
    assert client.env["CODECORTEX_CONTEXT_WORKSPACE_DIR"].startswith(str(tmp_path.resolve()))
