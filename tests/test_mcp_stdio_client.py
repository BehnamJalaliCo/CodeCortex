import sys
from pathlib import Path

from codecortex.backends.mcp_client import MCPStdioClient
from codecortex.backends.spec import BackendSpec


class PythonManager:
    def ensure(self, spec: BackendSpec) -> Path:
        return Path(sys.executable)


def test_mcp_stdio_round_trip() -> None:
    fixture = Path(__file__).parent / "fixtures" / "fake_mcp_server.py"
    spec = BackendSpec(
        key="fixture",
        package="fixture",
        source_url="https://example.invalid/fixture.git",
        revision="0" * 40,
        command="python",
        license_id="MIT",
        capabilities=("test",),
    )
    with MCPStdioClient(PythonManager(), spec, (str(fixture),)) as client:  # type: ignore[arg-type]
        tools = client.tools()
        assert tools[0]["name"] == "echo"
        result = client.call_tool("echo", {"text": "hello"})
        assert client.content_text(result) == "hello"
