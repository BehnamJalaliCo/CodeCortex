import json
import subprocess
from pathlib import Path

from codecortex.evaluation.production import (
    BenchmarkCaseSpec,
    ProductionBenchmarkReport,
    ProductionBenchmarkRunner,
    RepositoryCheckout,
    RepositorySpec,
    _evidence_recall,
)


def test_evidence_recall_is_deterministic() -> None:
    assert _evidence_recall(("src/auth.py", "AuthService"), "src/auth.py AuthService") == 1.0
    assert _evidence_recall(("src/auth.py", "Missing"), "src/auth.py AuthService") == 0.5


def test_report_keeps_missing_metrics_null(tmp_path: Path) -> None:
    report = ProductionBenchmarkReport()
    target = tmp_path / "report.json"
    report.save(target)
    payload = json.loads(target.read_text())
    assert payload["measurement_policy"]["missing_metrics"] == "null; never synthesized"


def test_revision_pinned_checkout(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(source), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(source), "config", "user.email", "test@example.com"], check=True
    )
    (source / "main.py").write_text("class Example:\n    pass\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(source), "commit", "-m", "base"], check=True, capture_output=True
    )
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    spec = RepositorySpec(
        name="fixture",
        url=source.as_uri(),
        revision=revision,
        cases=(
            BenchmarkCaseSpec(
                id="example",
                query="Example",
                expected_paths=("main.py",),
                expected_symbols=("Example",),
            ),
        ),
    )
    root = RepositoryCheckout(tmp_path / "cache").ensure(spec)
    assert (
        subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        == revision
    )


def test_vanilla_benchmark_observes_file_reads(tmp_path: Path) -> None:
    (tmp_path / "auth.py").write_text("class AuthService:\n    pass\n", encoding="utf-8")
    spec = RepositorySpec(
        name="fixture",
        url="file:///unused",
        revision="0" * 40,
        cases=(
            BenchmarkCaseSpec(
                id="auth",
                query="AuthService",
                expected_paths=("auth.py",),
                expected_symbols=("AuthService",),
            ),
        ),
    )
    runner = ProductionBenchmarkRunner([spec], workspace=tmp_path / "work")
    observation = runner._lexical(tmp_path, spec.cases[0])
    assert observation.files_read == 1
    assert "AuthService" in observation.text
