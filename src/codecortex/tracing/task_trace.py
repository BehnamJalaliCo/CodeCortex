"""Crash-tolerant task traces for agent workflows and tool execution."""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SENSITIVE = re.compile(
    r"^(?:secret|password|passwd|api[_-]?key|authorization|cookie|token)$"
    r"|(?:^|[_-])(?:access|refresh|auth)[_-]?token(?:$|[_-])",
    re.I,
)


@dataclass(frozen=True, slots=True)
class SpanRecord:
    trace_id: str
    span_id: str
    parent_id: str | None
    name: str
    status: str
    started_at: str
    ended_at: str
    duration_ms: float
    attributes: dict[str, Any]
    error: str | None = None


@dataclass(frozen=True, slots=True)
class TraceSummary:
    trace_id: str
    spans: int
    errors: int
    duration_ms: float
    tool_calls: int
    context_tokens: int
    names: tuple[str, ...]


class TaskTraceRecorder:
    VERSION = 1

    def __init__(self, path: Path, max_attribute_chars: int = 2_000) -> None:
        self.path = path
        self.max_attribute_chars = max_attribute_chars
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def new_trace_id(self) -> str:
        return uuid.uuid4().hex

    @contextmanager
    def span(
        self,
        name: str,
        *,
        trace_id: str | None = None,
        parent_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        resolved_trace = trace_id or self.new_trace_id()
        span_id = uuid.uuid4().hex
        started_wall = datetime.now(UTC).isoformat()
        started = time.perf_counter()
        error: str | None = None
        status = "ok"
        try:
            yield span_id
        except Exception as exc:
            status = "error"
            error = f"{type(exc).__name__}: {exc}"[:500]
            raise
        finally:
            self._append(
                SpanRecord(
                    trace_id=resolved_trace,
                    span_id=span_id,
                    parent_id=parent_id,
                    name=name,
                    status=status,
                    started_at=started_wall,
                    ended_at=datetime.now(UTC).isoformat(),
                    duration_ms=(time.perf_counter() - started) * 1000,
                    attributes=self._sanitize(attributes or {}),
                    error=error,
                )
            )

    @asynccontextmanager
    async def async_span(
        self,
        name: str,
        *,
        trace_id: str | None = None,
        parent_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        resolved_trace = trace_id or self.new_trace_id()
        span_id = uuid.uuid4().hex
        started_wall = datetime.now(UTC).isoformat()
        started = time.perf_counter()
        error: str | None = None
        status = "ok"
        try:
            yield span_id
        except Exception as exc:
            status = "error"
            error = f"{type(exc).__name__}: {exc}"[:500]
            raise
        finally:
            self._append(
                SpanRecord(
                    trace_id=resolved_trace,
                    span_id=span_id,
                    parent_id=parent_id,
                    name=name,
                    status=status,
                    started_at=started_wall,
                    ended_at=datetime.now(UTC).isoformat(),
                    duration_ms=(time.perf_counter() - started) * 1000,
                    attributes=self._sanitize(attributes or {}),
                    error=error,
                )
            )

    def record(
        self,
        name: str,
        *,
        trace_id: str,
        attributes: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> str:
        now = datetime.now(UTC).isoformat()
        span_id = uuid.uuid4().hex
        self._append(
            SpanRecord(
                trace_id=trace_id,
                span_id=span_id,
                parent_id=parent_id,
                name=name,
                status="ok",
                started_at=now,
                ended_at=now,
                duration_ms=0.0,
                attributes=self._sanitize(attributes or {}),
            )
        )
        return span_id

    def read(self, trace_id: str | None = None, limit: int = 10_000) -> list[SpanRecord]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        records: list[SpanRecord] = []
        for line in lines[-max(1, limit) :]:
            try:
                payload = json.loads(line)
                if int(payload.get("version", -1)) != self.VERSION:
                    continue
                data = payload["span"]
                record = SpanRecord(
                    trace_id=str(data["trace_id"]),
                    span_id=str(data["span_id"]),
                    parent_id=str(data["parent_id"]) if data.get("parent_id") else None,
                    name=str(data["name"]),
                    status=str(data["status"]),
                    started_at=str(data["started_at"]),
                    ended_at=str(data["ended_at"]),
                    duration_ms=float(data["duration_ms"]),
                    attributes=dict(data.get("attributes", {})),
                    error=str(data["error"]) if data.get("error") else None,
                )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
            if trace_id is None or record.trace_id == trace_id:
                records.append(record)
        return records

    def summarize(self, trace_id: str) -> TraceSummary:
        records = self.read(trace_id)
        return TraceSummary(
            trace_id=trace_id,
            spans=len(records),
            errors=sum(record.status == "error" for record in records),
            duration_ms=sum(record.duration_ms for record in records),
            tool_calls=sum(record.name.startswith("tool.") for record in records),
            context_tokens=sum(
                self._integer_metric(record.attributes.get("context_tokens")) for record in records
            ),
            names=tuple(record.name for record in records),
        )

    def _append(self, record: SpanRecord) -> None:
        payload = {"version": self.VERSION, "span": asdict(record)}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            handle.flush()

    def _sanitize(self, attributes: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in attributes.items():
            if _SENSITIVE.search(str(key)):
                sanitized[str(key)] = "[REDACTED]"
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                text = value if not isinstance(value, str) else value[: self.max_attribute_chars]
                sanitized[str(key)] = text
            else:
                serialized = json.dumps(value, ensure_ascii=False, default=str)
                sanitized[str(key)] = serialized[: self.max_attribute_chars]
        return sanitized

    @staticmethod
    def _integer_metric(value: Any) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value))
            except ValueError:
                return 0
        return 0
