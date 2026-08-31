from pathlib import Path

from codecortex.backends.graph import GraphBackendAdapter
from codecortex.backends.manager import ProcessResult


class FakeManager:
    def probe(self, spec, provision=False):  # noqa: ANN001, ANN201
        return True

    def run(self, spec, args, **kwargs):  # noqa: ANN001, ANN003, ANN201
        return ProcessResult(
            argv=(spec.command, *args),
            returncode=0,
            stdout="Node: AuthService",
            stderr="",
            duration_ms=1.0,
        )


def test_graph_adapter_query_delegates_to_pinned_backend(tmp_path: Path) -> None:
    adapter = GraphBackendAdapter(tmp_path, manager=FakeManager())  # type: ignore[arg-type]
    assert adapter.query("auth") == "Node: AuthService"
