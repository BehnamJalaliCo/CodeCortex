from codecortex.benchmark import (
    BenchmarkCase,
    BenchmarkSuite,
    CodeCortexGraphStrategy,
    FullTextBaseline,
)


def test_benchmark_records_measured_metrics(tmp_path):
    source = tmp_path / "auth.py"
    source.write_text("class TokenManager:\n    pass\n", encoding="utf-8")
    case = BenchmarkCase(
        id="auth",
        query="TokenManager authentication",
        expected_paths=("auth.py",),
        expected_symbols=("TokenManager",),
    )
    report = BenchmarkSuite(
        [case],
        [FullTextBaseline(tmp_path), CodeCortexGraphStrategy(tmp_path)],
    ).run()
    assert len(report.results) == 2
    graph = next(item for item in report.results if item.strategy == "codecortex_graph")
    assert graph.success is True
    assert graph.context_tokens >= 0
    assert report.summary()["codecortex_graph"]["success_rate"] == 1.0
