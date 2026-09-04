"""Dependency-free API observability primitives."""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class PlatformMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests = 0
        self.errors = 0
        self.in_flight = 0
        self.total_duration_ms = 0.0
        self.statuses: Counter[int] = Counter()
        self.paths: Counter[str] = Counter()

    def begin(self) -> None:
        with self._lock:
            self.requests += 1
            self.in_flight += 1

    def finish(self, path: str, status: int, duration_ms: float) -> None:
        with self._lock:
            self.in_flight = max(0, self.in_flight - 1)
            self.total_duration_ms += duration_ms
            self.statuses[status] += 1
            self.paths[path] += 1
            if status >= 500:
                self.errors += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "requests": self.requests,
                "errors": self.errors,
                "in_flight": self.in_flight,
                "avg_duration_ms": self.total_duration_ms / self.requests if self.requests else 0.0,
                "statuses": dict(self.statuses),
                "top_paths": self.paths.most_common(20),
            }

    def prometheus(self) -> str:
        data = self.snapshot()
        lines = [
            "# TYPE codecortex_api_requests_total counter",
            f"codecortex_api_requests_total {data['requests']}",
            "# TYPE codecortex_api_errors_total counter",
            f"codecortex_api_errors_total {data['errors']}",
            "# TYPE codecortex_api_in_flight gauge",
            f"codecortex_api_in_flight {data['in_flight']}",
            "# TYPE codecortex_api_duration_ms gauge",
            f"codecortex_api_duration_ms {data['avg_duration_ms']:.6f}",
        ]
        for status, count in data["statuses"].items():
            lines.append(f'codecortex_api_responses_total{{status="{status}"}} {count}')
        return "\n".join(lines) + "\n"


class StructuredRequestLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(
        self,
        *,
        request_id: str,
        trace_id: str | None,
        method: str,
        path: str,
        status: int,
        duration_ms: float,
    ) -> None:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": "error" if status >= 500 else "info",
            "request_id": request_id,
            "trace_id": trace_id,
            "event": "api.request",
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": round(duration_ms, 3),
        }
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def request_id() -> str:
    return uuid.uuid4().hex


def clock_ms() -> float:
    return time.perf_counter() * 1000
