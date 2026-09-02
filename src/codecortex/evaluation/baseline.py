"""Evidence-backed platform baseline snapshots used before large refactors."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PlatformBaseline:
    recorded_at: str
    revision: str | None
    metrics: dict[str, float | int | None]
    metadata: dict[str, str]


class PlatformBaselineStore:
    """Persist explicit baseline measurements without synthesizing missing values."""

    VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path

    def record(
        self,
        metrics: Mapping[str, float | int | None],
        *,
        revision: str | None = None,
        metadata: Mapping[str, str] | None = None,
        recorded_at: str | None = None,
    ) -> PlatformBaseline:
        normalized: dict[str, float | int | None] = {}
        for key, value in metrics.items():
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise TypeError(f"baseline metric {key!r} must be numeric or null")
            normalized[str(key)] = value
        baseline = PlatformBaseline(
            recorded_at=recorded_at or datetime.now(UTC).isoformat(),
            revision=revision,
            metrics=normalized,
            metadata={str(key): str(value) for key, value in (metadata or {}).items()},
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": self.VERSION, "baseline": asdict(baseline)}
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.path)
        return baseline

    def load(self) -> PlatformBaseline | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if payload.get("version") != self.VERSION or not isinstance(payload.get("baseline"), dict):
            return None
        raw = payload["baseline"]
        metrics = raw.get("metrics", {})
        metadata = raw.get("metadata", {})
        if not isinstance(metrics, dict) or not isinstance(metadata, dict):
            return None
        return PlatformBaseline(
            recorded_at=str(raw["recorded_at"]),
            revision=None if raw.get("revision") is None else str(raw["revision"]),
            metrics={str(key): value for key, value in metrics.items()},  # type: ignore[misc]
            metadata={str(key): str(value) for key, value in metadata.items()},
        )
