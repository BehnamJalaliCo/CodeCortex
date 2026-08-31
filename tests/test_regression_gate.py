from codecortex.evaluation import BenchmarkHistory, BenchmarkSnapshot, RegressionGate


def test_benchmark_history_persists_and_regression_gate_fails(tmp_path) -> None:
    history = BenchmarkHistory(tmp_path / "history.json")
    baseline = history.append(
        {"codecortex": {"success_rate": 1.0, "avg_duration_ms": 100.0}},
        commit="base",
    )
    current = history.append(
        {"codecortex": {"success_rate": 0.90, "avg_duration_ms": 140.0}},
        commit="head",
    )
    assert len(history.load()) == 2
    report = RegressionGate().evaluate(current, baseline)
    assert report.passed is False
    assert {item.metric for item in report.violations} == {"success_rate", "avg_duration_ms"}


def test_gate_allows_improvements() -> None:
    baseline = BenchmarkSnapshot("a", "now", None, {"s": {"success_rate": 0.8}}, {})
    current = BenchmarkSnapshot("b", "now", None, {"s": {"success_rate": 0.9}}, {})
    assert RegressionGate().evaluate(current, baseline).passed is True
