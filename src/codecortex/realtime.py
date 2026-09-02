"""Small in-process event bus used by SSE and local platform services."""

from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class PlatformEvent:
    event_id: str
    type: str
    payload: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PlatformEventBus:
    def __init__(self, *, subscriber_queue_size: int = 1000) -> None:
        self.subscriber_queue_size = max(10, subscriber_queue_size)
        self._subscribers: set[queue.Queue[PlatformEvent]] = set()
        self._lock = threading.RLock()

    def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> PlatformEvent:
        event = PlatformEvent(
            event_id=uuid.uuid4().hex,
            type=event_type,
            payload=dict(payload or {}),
            created_at=datetime.now(UTC).isoformat(),
        )
        with self._lock:
            subscribers = tuple(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(event)
            except queue.Full:
                try:
                    subscriber.get_nowait()
                except queue.Empty:
                    pass
                try:
                    subscriber.put_nowait(event)
                except queue.Full:
                    pass
        return event

    def subscribe(self) -> queue.Queue[PlatformEvent]:
        subscriber: queue.Queue[PlatformEvent] = queue.Queue(self.subscriber_queue_size)
        with self._lock:
            self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[PlatformEvent]) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)
