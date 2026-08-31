from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from codecortex.evaluation.production import (
    AgentProtocolResult,
    BenchmarkCaseSpec,
    InstrumentedAgentRunner,
    ObservedMetrics,
    ProductionBenchmarkReport,
    ProductionBenchmarkRunner,
    RepositorySpec,
    RetrievalObservation,
    ScenarioResult,
    SetupMeasurement,
    _average,
    _evidence_recall,
    _extract_paths,
    _optional_float,
    _optional_int,
    _safe_name,
    load_repository_specs,
    temporary_benchmark_workspace,
)

REV = "1" * 40


def _case() -> BenchmarkCaseSpec:
    return BenchmarkCaseSpec(
        id="service",
        query="Service helper",
        expected_paths=("src/service.py",),
        expected_symbols=("Service",),
    )


def _spec() -> RepositorySpec:
    return RepositorySpec("demo", "https://example.invalid/demo.git", REV, (_case(),))


def test_specs_helpers_report_and_save(tmp_path: Path) -> None:
    case_payload = {
        "id": "x",
        "query": "query",
        "expected_paths": ["src/x.py"],
        "expected_symbols": ["X"],
    }
    case = BenchmarkCaseSpec.from_dict(case_payload)
    repo = RepositorySpec.from_dict(
        {"name": "repo", "url": "u", "revision": REV, "cases": [case_payload]}
    )
    assert case.id == "x" and repo.cases[0].id == "x"
    assert _evidence_recall((), "") == 1.0
    assert _evidence_recall(("X", "Y"), "x only") == 0.5
    assert "src/x.py" in _extract_paths("see [src/x.py] now")
    assert _average([1, None, 3]) == 2.0
    assert _average([]) is None
    assert _optional_int(2.0) == 2 and _optional_int(True) is None
    assert _optional_float(2) == 2.0 and _optional_float(False) is None
    assert _safe_name("a b/c") == "a-b-c"
    assert _safe_name("///") == "repository"

    metrics = ObservedMetrics(10, 20, 5, 2, 1, 3, cost_usd=0.25)
    ok = ScenarioResult("repo", REV, "x", "vanilla", "ok", True, 1.0, 1.0, metrics)
    skipped = ScenarioResult(
        "repo", REV, "y", "vanilla", "skipped", None, None, None, None
    )
    report = ProductionBenchmarkReport(
        repositories=[{"name": "repo", "url": "u", "revision": REV}],
        setup=[SetupMeasurement("repo", "graph", 2.0, "ok", "healthy")],
        results=[ok, skipped],
    )
    summary = report.summary()["vanilla"]
    assert summary["cases"] == 2 and summary["success_rate"] == 1.0
    output = tmp_path / "report.json"
    report.save(output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1

    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "name": "repo",
                        "url": "u",
                        "revision": REV,
                        "cases": [{"id": "x", "query": "q"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert load_repository_specs(spec_path)[0].name == "repo"
    loaded = ProductionBenchmarkRunner.load(spec_path, workspace=tmp_path / "loaded")
    assert loaded.specs[0].name == "repo"
    with temporary_benchmark_workspace() as workspace:
        assert Path(workspace).exists()


def test_lexical_measure_and_operations(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "service.py").write_text(
        "class Service:\n    pass\n\ndef helper():\n    return Service()\n",
        encoding="utf-8",
    )
    (root / "binary.bin").write_bytes(b"\xff")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "ignored.py").write_text("Service", encoding="utf-8")

    runner = ProductionBenchmarkRunner((), workspace=tmp_path / "work")
    case = _case()
    observation = runner._lexical(root, case)
    assert observation.files_read == 1
    assert "src/service.py" in observation.text

    measured = runner._measure(_spec(), case, "vanilla", lambda: observation)
    assert measured.status == "ok" and measured.success is True
    failed = runner._measure(
        _spec(), case, "vanilla", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert failed.status == "error" and "boom" in (failed.error or "")

    graph = SimpleNamespace(query=lambda query: f"src/service.py {query}")
    symbols = SimpleNamespace(
        call=lambda _name, _args: {
            "content": [{"type": "text", "text": "Service"}]
        }
    )
    context = SimpleNamespace(
        compress=lambda text: {"content": [{"type": "text", "text": text[:50]}]}
    )
    baseline = RetrievalObservation("src/service.py Service", 1, 1)
    assert (
        runner._operation("graph", case, root, graph, symbols, context, baseline)().tool_calls
        == 1
    )
    assert (
        runner._operation("symbols", case, root, graph, symbols, context, baseline)().tool_calls
        == 1
    )
    assert (
        runner._operation("context", case, root, graph, symbols, context, baseline)().tool_calls
        == 2
    )
    assert (
        runner._operation("full", case, root, graph, symbols, context, baseline)().tool_calls
        == 3
    )
    with pytest.raises(ValueError):
        runner._operation(
            "invalid", case, root, graph, symbols, context, baseline  # type: ignore[arg-type]
        )


def test_prepare_availability(tmp_path: Path) -> None:
    class Manager:
        def __init__(self) -> None:
            self.installed = {"graph": True, "symbols": True, "context": False}

        def is_installed(self, spec) -> bool:
            return self.installed[spec.key]

        def probe(self, spec, provision=False) -> bool:
            del provision
            return bool(self.installed.get(spec.key))

    class Adapter:
        required_tools = ("tool",)

        def __init__(self, key: str) -> None:
            self.spec = SimpleNamespace(key=key)
            self.built = False

        def build(self) -> None:
            self.built = True

        def tools(self):
            return ("tool",)

        def require_tools(self, tools, required) -> None:
            assert tools and required

    manager = Manager()
    runner = ProductionBenchmarkRunner(
        (), workspace=tmp_path, backend_manager=manager  # type: ignore[arg-type]
    )
    graph, symbols, context = Adapter("graph"), Adapter("symbols"), Adapter("context")
    report = ProductionBenchmarkReport()
    availability = runner._prepare(
        _spec(),
        tmp_path,
        ("full",),
        graph,  # type: ignore[arg-type]
        symbols,  # type: ignore[arg-type]
        context,  # type: ignore[arg-type]
        report,
    )
    assert availability["graph"] and availability["symbols"]
    assert not availability["context"] and not availability["full"]
    assert graph.built and len(report.setup) == 3


def test_instrumented_agent_runner_success_and_errors(tmp_path: Path) -> None:
    good_script = tmp_path / "agent.py"
    good_script.write_text(
        "import json, sys\n"
        "json.load(sys.stdin)\n"
        "print(json.dumps({'answer': 'ok', 'files_read': 2, 'tool_calls': 3, 'cost_usd': 0.1}))\n",
        encoding="utf-8",
    )
    runner = InstrumentedAgentRunner(f"{sys.executable} {good_script}")
    result = runner.run(scenario="vanilla", repository=tmp_path, case=_case())
    assert isinstance(result, AgentProtocolResult)
    assert result.answer == "ok" and result.files_read == 2 and result.cost_usd == 0.1

    with pytest.raises(ValueError):
        InstrumentedAgentRunner("")

    bad_script = tmp_path / "bad.py"
    bad_script.write_text("print('not-json')\n", encoding="utf-8")
    bad = InstrumentedAgentRunner(f"{sys.executable} {bad_script}")
    with pytest.raises(json.JSONDecodeError):
        bad.run(scenario="vanilla", repository=tmp_path, case=_case())

    failing_script = tmp_path / "fail.py"
    failing_script.write_text(
        "import sys\nsys.stderr.write('agent failed')\nraise SystemExit(2)\n",
        encoding="utf-8",
    )
    failing = InstrumentedAgentRunner(f"{sys.executable} {failing_script}")
    with pytest.raises(RuntimeError, match="agent failed"):
        failing.run(scenario="vanilla", repository=tmp_path, case=_case())
