"""Telemetry collection with optional local persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import time
from typing import Any


@dataclass(slots=True)
class TelemetryEvent:
    name: str
    timestamp: float = field(default_factory=time)
    attributes: dict[str, Any] = field(default_factory=dict)


class TelemetryCollector:
    def __init__(self, enabled: bool = True, log_path: Path | None = None) -> None:
        self.enabled = enabled
        self.log_path = log_path
        self._events: list[TelemetryEvent] = []
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, name: str, **attributes: Any) -> None:
        if not self.enabled:
            return
        event = TelemetryEvent(name=name, attributes=attributes)
        self._events.append(event)
        if self.log_path is not None:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(event), ensure_ascii=False, default=str) + "\n")

    def events(self) -> list[TelemetryEvent]:
        return list(self._events)

    def snapshot(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self._events:
            counts[event.name] = counts.get(event.name, 0) + 1
        return counts
