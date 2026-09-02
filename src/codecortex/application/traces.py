"""Trace-list and trace-detail application service."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codecortex.runtime import CortexRuntime


class TraceExplorerService:
    def __init__(self, runtime: CortexRuntime) -> None:
        self.runtime = runtime

    def recent(self, limit: int = 50) -> dict[str, Any]:
        records = self.runtime.tracer.read(limit=10000)
        latest: dict[str, str] = {}
        for row in records:
            latest[row.trace_id] = max(latest.get(row.trace_id, ""), row.started_at)
        trace_ids = [
            item[0]
            for item in sorted(latest.items(), key=lambda x: x[1], reverse=True)[
                : min(500, max(1, limit))
            ]
        ]
        return {
            "traces": [
                {**asdict(self.runtime.tracer.summarize(trace_id)), "last_seen": latest[trace_id]}
                for trace_id in trace_ids
            ]
        }

    def detail(self, trace_id: str) -> dict[str, Any]:
        spans = self.runtime.tracer.read(trace_id)
        if not spans:
            raise KeyError(trace_id)
        return {
            "summary": asdict(self.runtime.tracer.summarize(trace_id)),
            "spans": [asdict(span) for span in spans],
        }
