from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from codecortex.config import CortexConfig
from codecortex.context.slicing import AstContextSlicer
from codecortex.core.models import Capability
from codecortex.distributed.graph_store import DistributedGraphStore
from codecortex.evaluation.retrieval_quality import (
    RetrievalQualityBenchmark,
    RetrievalQualityCase,
    RetrievalQualityReport,
)
from codecortex.feedback import AgentFeedbackStore
from codecortex.indexing.graph import GraphEdge, GraphNode, ProjectGraph
from codecortex.mcp.validation import validate_tool_call
from codecortex.retrieval.repository import RepositorySemanticIndex
from codecortex.state import AtomicJsonFile, FileMutex


def test_config_load_env_validation_and_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / ".codecortex"
    state.mkdir()
    (state / "config.json").write_text(
        json.dumps(
            {
                "state_dir_name": ".state",
                "context_budget": 4000,
                "hard_context_limit": 9000,
                "telemetry": False,
            }
        ),
        encoding="utf-8",
    )
    config = CortexConfig.load(tmp_path)
    assert config.project_root == tmp_path.resolve()
    assert config.state_dir_name == ".state"
    assert config.default_context_budget == 4000
    assert config.hard_context_limit == 9000
    assert config.telemetry_enabled is False
    assert config.state_dir == tmp_path.resolve() / ".state"
    assert config.memory_dir == config.state_dir / "memory"
    assert config.config_path == config.state_dir / "config.json"
    config.ensure_directories()
    assert config.memory_dir.is_dir()
    assert config.validate_budget(1) == 1
    assert config.validate_budget(9000) == 9000
    with pytest.raises(ValueError, match="positive"):
        config.validate_budget(0)
    with pytest.raises(ValueError, match="exceeds hard limit"):
        config.validate_budget(9001)

    monkeypatch.setenv("CODECORTEX_CONTEXT_BUDGET", "123")
    monkeypatch.setenv("CODECORTEX_HARD_CONTEXT_LIMIT", "456")
    monkeypatch.setenv("CODECORTEX_TELEMETRY", "off")
    overridden = CortexConfig.load(tmp_path)
    assert overridden.default_context_budget == 123
    assert overridden.hard_context_limit == 456
    assert overridden.telemetry_enabled is False

    monkeypatch.delenv("CODECORTEX_CONTEXT_BUDGET")
    monkeypatch.delenv("CODECORTEX_HARD_CONTEXT_LIMIT")
    monkeypatch.delenv("CODECORTEX_TELEMETRY")
    (state / "config.json").write_text("not-json", encoding="utf-8")
    defaults = CortexConfig.load(tmp_path)
    assert defaults.default_context_budget == 32_000
    assert defaults.hard_context_limit == 128_000
    with pytest.raises(ValueError, match="cannot exceed"):
        CortexConfig(default_context_budget=10, hard_context_limit=9)


def test_mcp_schema_validation_all_supported_types() -> None:
    tools = [
        {
            "name": "demo",
            "inputSchema": {
                "type": "object",
                "required": ["name", "items", "count", "ratio", "enabled"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "minLength": 2},
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 2,
                        "items": {"type": "integer", "minimum": 1, "maximum": 3},
                    },
                    "count": {"type": "integer", "minimum": 0, "maximum": 5},
                    "ratio": {"type": "number"},
                    "enabled": {"type": "boolean"},
                },
            },
        }
    ]
    valid = {"name": "ok", "items": [1, 3], "count": 2, "ratio": 1.5, "enabled": True}
    validate_tool_call(tools, "demo", valid)

    with pytest.raises(KeyError):
        validate_tool_call(tools, "missing", {})
    with pytest.raises(ValueError, match="object"):
        validate_tool_call(tools, "demo", [])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="missing required"):
        validate_tool_call(tools, "demo", {})
    with pytest.raises(ValueError, match="unknown fields"):
        validate_tool_call(tools, "demo", {**valid, "extra": 1})
    with pytest.raises(ValueError, match="at least 2"):
        validate_tool_call(tools, "demo", {**valid, "name": "x"})
    with pytest.raises(ValueError, match="array"):
        validate_tool_call(tools, "demo", {**valid, "items": "bad"})
    with pytest.raises(ValueError, match="at least 1"):
        validate_tool_call(tools, "demo", {**valid, "items": []})
    with pytest.raises(ValueError, match="at most 2"):
        validate_tool_call(tools, "demo", {**valid, "items": [1, 2, 3]})
    with pytest.raises(ValueError, match="integer"):
        validate_tool_call(tools, "demo", {**valid, "count": True})
    with pytest.raises(ValueError, match=">= 1"):
        validate_tool_call(tools, "demo", {**valid, "items": [0]})
    with pytest.raises(ValueError, match="<= 3"):
        validate_tool_call(tools, "demo", {**valid, "items": [4]})
    with pytest.raises(ValueError, match="number"):
        validate_tool_call(tools, "demo", {**valid, "ratio": True})
    with pytest.raises(ValueError, match="boolean"):
        validate_tool_call(tools, "demo", {**valid, "enabled": 1})

    invalid_schema = [{"name": "bad", "inputSchema": "not-a-dict"}]
    with pytest.raises(ValueError, match="invalid input schema"):
        validate_tool_call(invalid_schema, "bad", {})


def test_atomic_json_file_and_mutex_recovery(tmp_path: Path) -> None:
    path = tmp_path / "state" / "data.json"
    state = AtomicJsonFile(path)
    assert state.read({"missing": True}) == {"missing": True}
    state.write({"count": 1})
    assert state.read() == {"count": 1}
    assert state.update(lambda value: {"count": value["count"] + 1}, default={}) == {"count": 2}
    assert state.read() == {"count": 2}

    path.write_text("{broken", encoding="utf-8")
    assert state.read("fallback") == "fallback"

    lock_path = tmp_path / "stale.lock"
    lock_path.mkdir()
    old = time.time() - 100
    os.utime(lock_path, (old, old))
    mutex = FileMutex(lock_path, timeout_seconds=0.2, stale_seconds=1)
    mutex.acquire()
    assert mutex._held is True
    mutex.release()
    assert not lock_path.exists()
    mutex.release()

    live = FileMutex(tmp_path / "live.lock", timeout_seconds=0.06, stale_seconds=60)
    live.acquire()
    contender = FileMutex(live.path, timeout_seconds=0.01, stale_seconds=60)
    with pytest.raises(TimeoutError):
        contender.acquire()
    live.release()


def test_feedback_store_summary_and_adjustments(tmp_path: Path) -> None:
    store = AgentFeedbackStore(tmp_path / "feedback.db")
    assert store.summary(Capability.CONTEXT) is None
    assert store.routing_adjustment(Capability.CONTEXT) == 0.0

    for latency in (10.0, 20.0, 30.0):
        store.record("auth query", Capability.CONTEXT, True, latency)
    summary = store.summary(Capability.CONTEXT, limit=2)
    assert summary is not None
    assert summary.samples == 2
    assert summary.success_rate == 1.0
    assert summary.average_latency_ms >= 0
    assert store.routing_adjustment(Capability.CONTEXT) > 0

    for _ in range(3):
        store.record("bad", Capability.VALIDATION, False, -50)
    bad = store.summary(Capability.VALIDATION)
    assert bad is not None and bad.average_latency_ms == 0.0
    assert store.routing_adjustment(Capability.VALIDATION) < 0


def test_retrieval_quality_metrics_and_hit_shapes() -> None:
    assert RetrievalQualityReport(()).summary() == {
        "cases": 0.0,
        "avg_recall": 0.0,
        "avg_precision": 0.0,
        "mrr": 0.0,
    }
    cases = [
        RetrievalQualityCase("one", "q", ("a", "c"), limit=3),
        RetrievalQualityCase("empty", "none", (), limit=0),
    ]
    benchmark = RetrievalQualityBenchmark(cases)

    def search(query: str, limit: int):
        assert limit >= 1
        return ["x", {"id": "a"}, SimpleNamespace(id="c")] if query == "q" else []

    report = benchmark.run(search)
    assert report.results[0].recall == 1.0
    assert report.results[0].precision == pytest.approx(2 / 3)
    assert report.results[0].reciprocal_rank == 0.5
    assert report.results[1].recall == 1.0
    assert report.results[1].precision == 0.0
    summary = report.summary()
    assert summary["cases"] == 2.0
    assert summary["mrr"] == 0.25

    assert benchmark._hit_id(SimpleNamespace(document=SimpleNamespace(id="doc"))) == "doc"
    with pytest.raises(TypeError, match="cannot extract"):
        benchmark._hit_id(object())


def _graph(name: str) -> ProjectGraph:
    file_node = GraphNode(id=f"file:{name}", kind="file", name=f"{name}.py", path=f"{name}.py")
    symbol = GraphNode(
        id=f"symbol:{name}", kind="function", name=name, path=f"{name}.py", line=1
    )
    return ProjectGraph(
        nodes=[file_node, symbol],
        edges=[GraphEdge(source=file_node.id, target=symbol.id, kind="contains")],
    )


def test_distributed_graph_store_revisions_and_pruning(tmp_path: Path) -> None:
    store = DistributedGraphStore(tmp_path / "graphs.db")
    assert store.latest_revision("repo") is None
    assert store.load("repo").nodes == []
    with pytest.raises(ValueError, match="required"):
        store.replace("", "r1", ProjectGraph())

    first = _graph("alpha")
    second = _graph("beta")
    store.replace("repo", "r1", first)
    time.sleep(0.001)
    store.replace("repo", "r2", second)
    assert store.repositories() == ("repo",)
    assert store.latest_revision("repo") == "r2"
    assert store.load("repo").nodes[1].name == "beta"
    assert store.load("repo", "r1") == first
    assert store.prune("repo", keep=1) == 1
    assert store.load("repo", "r1").nodes == []
    assert store.prune("repo", keep=0) == 0


def test_ast_context_slicer_symbol_fallback_and_query(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text(
        "class Service:\n"
        "    def run(self, value):\n"
        "        return helper(value)\n\n"
        "def helper(value):\n"
        "    return value + 1\n",
        encoding="utf-8",
    )
    slicer = AstContextSlicer(tmp_path, context_lines=1)
    exact = slicer.slice_symbol(source, "helper", max_tokens=200)
    assert "def helper" in exact
    method = slicer.slice_symbol(source, "run", line=2, max_tokens=200)
    assert "def run" in method
    fallback = slicer.slice_symbol(source, "missing", line=5, max_tokens=200)
    assert "helper" in fallback
    assert slicer.slice_symbol(tmp_path / "missing.py", "x") == ""

    chunks = slicer.slice("run helper", source, max_tokens=300, limit=2)
    assert chunks
    assert all(chunk.metadata["ast_slice"] is True for chunk in chunks)
    assert all(chunk.metadata["path"] == "service.py" for chunk in chunks)
    assert slicer.slice("zzzznotfound", source) == []


def test_repository_semantic_index_documents_incremental_and_search(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text("def helper(value):\n    return value + 1\n", encoding="utf-8")
    file_node = GraphNode(id="file", kind="file", name="service.py", path="service.py")
    helper = GraphNode(id="helper", kind="function", name="helper", path="service.py", line=1)
    module = GraphNode(id="module", kind="module", name="service", path="service.py")
    graph = ProjectGraph(
        nodes=[file_node, helper, module],
        edges=[GraphEdge(source="file", target="helper", kind="contains")],
    )
    index = RepositorySemanticIndex(tmp_path, max_snippet_chars=200)
    assert index.refresh(graph) == 2
    assert index.index.document_ids == {"file", "helper"}
    helper_doc = index.index.document("helper")
    assert helper_doc is not None and "helper" in helper_doc.text
    assert "contains" in index._structural_context("file", graph)
    assert "used-by" in index._structural_context("helper", graph)
    assert index._document(module, graph) is None
    assert index._snippet(tmp_path / "missing.py", None) == ""
    assert index._snippet(source, 1)
    assert index.search("helper", limit=5)

    reduced = ProjectGraph(nodes=[file_node], edges=[])
    assert index.refresh(reduced) == 1
    assert index.index.document_ids == {"file"}
    assert index.refresh(reduced) == 1
