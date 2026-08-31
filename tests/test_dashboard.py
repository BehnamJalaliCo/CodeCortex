from codecortex.dashboard import _event_stats, _overview, _recent_traces
from codecortex.runtime import build_runtime


def test_event_stats_aggregates_routes_tokens_and_latency():
    events = [
        {"name": "route.created", "attributes": {"kind": "debug"}},
        {"name": "context.fitted", "attributes": {"saved": 120}},
        {"name": "engine.executed", "attributes": {"capability": "symbols", "duration_ms": 40}},
        {"name": "engine.executed", "attributes": {"capability": "symbols", "duration_ms": 20}},
    ]
    stats = _event_stats(events)
    assert stats["routes"]["debug"] == 1
    assert stats["context_tokens_saved"] == 120
    assert stats["engine_avg_latency_ms"]["symbols"] == 30.0


async def test_overview_exposes_graph_runtime_and_observability(tmp_path):
    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    runtime = build_runtime(tmp_path)
    runtime.telemetry.emit("route.created", kind="explain")
    payload = await _overview(runtime)
    assert payload["graph"]["nodes"] >= 1
    assert payload["index"]["tracked"] >= 1
    assert payload["runtime"]["routes"]["explain"] == 1
    assert "architecture" in payload
    assert "benchmarks" in payload


def test_recent_traces_tolerates_missing_trace_file(tmp_path):
    runtime = build_runtime(tmp_path)
    assert _recent_traces(runtime) == []
