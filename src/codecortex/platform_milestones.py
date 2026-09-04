"""Machine-readable release milestone contract."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReleaseMilestone:
    id: str
    name: str
    requires: tuple[str, ...]


class MilestoneManifest:
    def __init__(self, milestones: tuple[ReleaseMilestone, ...]) -> None:
        self.milestones = milestones
        ids = [item.id for item in milestones]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("milestone ids must be unique and ordered")

    @classmethod
    def load(cls, path: Path) -> MilestoneManifest:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported milestone manifest version")
        milestones = tuple(
            ReleaseMilestone(
                str(item["id"]),
                str(item["name"]),
                tuple(str(value) for value in item.get("requires", [])),
            )
            for item in payload.get("milestones", [])
        )
        return cls(milestones)

    def completion(self, capabilities: Iterable[str]) -> dict[str, bool]:
        available = set(capabilities)
        return {item.id: set(item.requires).issubset(available) for item in self.milestones}
