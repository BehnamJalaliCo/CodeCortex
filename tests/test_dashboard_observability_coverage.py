from __future__ import annotations

import json
from pathlib import Path

import pytest

from codecortex.architecture import ArchitectureDriftDetector
from codecortex.dashboard import (
    _architecture_drift,
    _benchmark_history,
    _event_stats,
    _html,
    _overview,
    _read_events,
    _recent_traces,
)
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.runtime import build_runtime


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "dashboard-project"
    root.mkdir()
    (root / "app.py").write_text(
        "class Service:\n    def run(self):\n        return 1\n",
        encoding="utf-8",
    )
    return root


def test_event_reading_and_stats(tmp_path: Path) -> None:
    root = _project(tmp_path)
    runtime = build_runtime(root)
    events_path = runtime.config.state_dir / "runtime" / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text(
        "not-json\n"
        + "\n".join(
            json.dumps(item)
            for item in [
                {"name": "route.created", "attributes": {"kind": "symbol"}},
                {"name": "route.created", "attributes": {"kind": "symbol"}},
                {"name": "context.fitted", "attributes": {"saved": 120}},
                {
                    "name": "engine.executed",
                    "attributes": {"capability": "symbols", "duration_ms": 10},
                },
                {
                    "name": "engine.executed",
                    "attributes": {"capability": "symbols", "duration_ms": 30},
                },
                {"name": "plain"},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    events = _read_events(runtime)
    assert len(events) == 6
    stats = _event_stats(events)
    assert stats["routes"]["symbol"] == 2
    assert stats["context_tokens_saved"] == 120
    assert stats["engine_avg_latency_ms"]["symbols"] == 20.0

    events_path.unlink()
    assert _read_events(runtime) == []


def test_dashboard_helpers_and_overview(tmp_path: Path) -> None:
    root = _project(tmp_path)
    runtime = build_runtime(root)
    graph, _stats = IncrementalGraphIndex(root).refresh()

    missing = _architecture_drift(runtime, graph)
    assert missing["status"] == "no-baseline"
    baseline = runtime.config.state_dir / "architecture" / "baseline.json"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    ArchitectureDriftDetector().fingerprint(graph).save(baseline)
    compared = _architecture_drift(runtime, graph)
    assert compared["status"] == "compared"

    assert _recent_traces(runtime) == []
    assert _benchmark_history(runtime) == []
    page = _html("<repo&name>")
    assert "&lt;repo&amp;name&gt;" in page
    assert "CodeCortex Observatory" in page


@pytest.mark.asyncio
async def test_overview_returns_observability_payload(tmp_path: Path) -> None:
    root = _project(tmp_path)
    runtime = build_runtime(root)
    payload = await _overview(runtime)
    assert payload["project"] == str(root.resolve())
    assert payload["index"]["tracked"] >= 1
    assert payload["graph"]["nodes"] >= 1
    assert "health" in payload and "runtime" in payload
