"""In-process telemetry collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any


@dataclass(slots=True)
class TelemetryEvent:
    name: str
    timestamp: float = field(default_factory=time)
    attributes: dict[str, Any] = field(default_factory=dict)


class TelemetryCollector:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._events: list[TelemetryEvent] = []

    def emit(self, name: str, **attributes: Any) -> None:
        if self.enabled:
            self._events.append(TelemetryEvent(name=name, attributes=attributes))

    def events(self) -> list[TelemetryEvent]:
        return list(self._events)

    def snapshot(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self._events:
            counts[event.name] = counts.get(event.name, 0) + 1
        return counts
