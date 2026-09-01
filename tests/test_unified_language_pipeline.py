import asyncio

from codecortex.core.models import AgentRequest
from codecortex.engines.builtin.symbols import SymbolEngine
from codecortex.indexing.indexer import ProjectIndexer
from codecortex.languages import LanguageRegistry


def test_python_methods_preserve_container_identity() -> None:
    units = LanguageRegistry(native=False).parse(
        __import__("pathlib").Path("service.py"),
        "class A:\n    def save(self):\n        return 1\nclass B:\n    def save(self):\n        return 2\n",
    )
    saves = [unit for unit in units if unit.name == "save"]
    assert [(unit.kind, unit.container) for unit in saves] == [("method", "A"), ("method", "B")]


def test_project_indexer_uses_language_registry_for_typescript(tmp_path) -> None:
    (tmp_path / "service.ts").write_text(
        "export class Service {}\nexport function run() { return 1 }\n",
        encoding="utf-8",
    )
    graph = ProjectIndexer(tmp_path).build()
    assert any(node.name == "Service" for node in graph.nodes)
    assert any(node.name == "run" for node in graph.nodes)


def test_builtin_symbol_engine_matches_same_unified_symbols(tmp_path) -> None:
    (tmp_path / "service.py").write_text("class Service:\n    def run(self):\n        return 1\n", encoding="utf-8")
    engine = SymbolEngine(tmp_path)
    result = asyncio.run(engine.execute(AgentRequest(query="run")))
    assert "method run" in result.content
