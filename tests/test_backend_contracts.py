from pathlib import Path

from codecortex.backends import ContextIntelligence, GraphIntelligence, SymbolIntelligence
from codecortex.backends.context import ContextBackendAdapter
from codecortex.backends.graph import GraphBackendAdapter
from codecortex.backends.symbols import SymbolBackendAdapter


def test_adapters_implement_stable_protocols(tmp_path: Path) -> None:
    assert isinstance(GraphBackendAdapter(tmp_path), GraphIntelligence)
    assert isinstance(SymbolBackendAdapter(tmp_path), SymbolIntelligence)
    assert isinstance(ContextBackendAdapter(tmp_path), ContextIntelligence)
