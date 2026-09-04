from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from codecortex.entrypoint import app
from codecortex.evaluation import EvidenceBenchmark
from tests.fixtures.precision_index import (
    DEFINITION,
    Document,
    IndexBuilder,
    Occurrence,
    SymbolInfo,
    symbol,
)

runner = CliRunner()

AUTH_SESSION = symbol("app", "auth/service/`Session`#")
BILLING_SESSION = symbol("app", "billing/service/`Session`#")


def _index() -> bytes:
    """Index the generated duplicate-symbol fixture at its real positions."""
    return (
        IndexBuilder()
        .add(
            Document(
                relative_path="src/auth/service.py",
                occurrences=(Occurrence(AUTH_SESSION, 0, 6, 13, roles=DEFINITION),),
                symbols=(SymbolInfo(AUTH_SESSION, display_name="Session"),),
            )
        )
        .add(
            Document(
                relative_path="src/billing/service.py",
                occurrences=(Occurrence(BILLING_SESSION, 0, 6, 13, roles=DEFINITION),),
                symbols=(SymbolInfo(BILLING_SESSION, display_name="Session"),),
            )
        )
        .add(
            Document(
                relative_path="src/app.py",
                occurrences=(Occurrence(AUTH_SESSION, 4, 11, 18),),
            )
        )
        .encode()
    )


def _case(report, case_id: str):
    return next(item for item in report.cases if item.case_id == case_id)


def _metric(case, strategy: str):
    return next(item for item in case.metrics if item.strategy == strategy)


def test_benchmark_measures_duplicate_symbol_resolution(tmp_path: Path) -> None:
    report = EvidenceBenchmark(workdir=tmp_path / "wd", precision_index=_index()).run()
    case = _case(report, "duplicate-symbols")

    heuristic = _metric(case, "graph_heuristic")
    precision = _metric(case, "precision_index")

    # The heuristic strategy cannot tell the two same-named classes apart.
    assert heuristic.correct_targets >= 1
    assert heuristic.false_targets >= 1
    assert precision.correct_targets == 1
    assert precision.false_targets == 0
    assert precision.precision == 1.0
    assert precision.precision > heuristic.precision
    assert precision.context_tokens <= heuristic.context_tokens


def test_benchmark_measures_resolved_dependency_versions(tmp_path: Path) -> None:
    report = EvidenceBenchmark(workdir=tmp_path / "wd").run()
    case = _case(report, "dependency-version")
    assert _metric(case, "source_only").correct_targets == 0
    assert _metric(case, "dependency_intelligence").correct_targets == 1
    assert any("credentials" in note for note in case.notes)


def test_benchmark_measures_migration_precision(tmp_path: Path) -> None:
    engine = shutil.which("ast-grep")
    report = EvidenceBenchmark(workdir=tmp_path / "wd", structural_command=engine).run()
    case = _case(report, "mechanical-migration")

    lexical = _metric(case, "lexical_scan")
    # The lexical scan also matches prose that merely mentions the call.
    assert lexical.false_targets >= 1

    if engine is None:
        assert any("not measured" in note for note in case.notes)
        assert any("mechanical-migration" in item for item in report.skipped)
        return
    structural = _metric(case, "structural_search")
    assert structural.correct_targets == 2
    assert structural.false_targets == 0
    assert structural.precision > lexical.precision


def test_benchmark_reports_skipped_strategies_instead_of_estimating(tmp_path: Path) -> None:
    report = EvidenceBenchmark(workdir=tmp_path / "wd", structural_command=None).run()
    duplicate = _case(report, "duplicate-symbols")
    assert [item.strategy for item in duplicate.metrics] == ["graph_heuristic"]
    assert any("no precision index" in item for item in report.skipped)
    assert any("not measured" in note for note in duplicate.notes)


def test_benchmark_cli_writes_a_report(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    index_file = tmp_path / "index.scip"
    index_file.write_bytes(_index())
    result = runner.invoke(
        app,
        [
            "evidence-benchmark",
            "--path",
            str(root),
            "--precision-index",
            str(index_file),
            "--output",
            "benchmarks/evidence.json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads((root / "benchmarks" / "evidence.json").read_text(encoding="utf-8"))
    assert {item["case_id"] for item in payload["cases"]} == {
        "duplicate-symbols",
        "dependency-version",
        "mechanical-migration",
    }
    for case in payload["cases"]:
        for metric in case["metrics"]:
            assert metric["duration_ms"] >= 0.0
            assert 0.0 <= metric["precision"] <= 1.0
