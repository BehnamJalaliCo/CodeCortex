from pathlib import Path

from codecortex.backends.symbols import SymbolBackendAdapter
from codecortex.core.models import AgentRequest, RequestKind


def test_symbol_backend_server_is_project_scoped(tmp_path: Path) -> None:
    adapter = SymbolBackendAdapter(tmp_path)
    args = adapter.server_args()
    assert "--project" in args
    assert str(tmp_path.resolve()) in args
    assert args[:3] == ("start-mcp-server", "--transport", "stdio")


def test_symbol_backend_mutations_are_explicit() -> None:
    request = AgentRequest(query="AuthService", kind=RequestKind.REFACTOR)
    tool, arguments = SymbolBackendAdapter._plan(request)
    assert tool == "find_symbol"
    assert arguments["include_body"] is True


def test_symbol_backend_reference_plan_requires_path() -> None:
    request = AgentRequest(
        query="AuthService/refresh",
        metadata={"references": True, "relative_path": "src/auth.py"},
    )
    tool, arguments = SymbolBackendAdapter._plan(request)
    assert tool == "find_referencing_symbols"
    assert arguments["relative_path"] == "src/auth.py"
