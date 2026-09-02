"""Execution-priority and roadmap governance contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PriorityStage:
    id: str
    name: str
    items: tuple[str, ...]


class PriorityManifest:
    EXPECTED = tuple(f"P{index}" for index in range(6))

    def __init__(self, stages: tuple[PriorityStage, ...]) -> None:
        self.stages = stages
        ids = tuple(item.id for item in stages)
        if ids != self.EXPECTED:
            raise ValueError(f"priority stages must be {self.EXPECTED}")
        owners: dict[str, str] = {}
        for stage in stages:
            for item in stage.items:
                if item in owners:
                    raise ValueError(
                        f"roadmap item {item!r} appears in both {owners[item]} and {stage.id}"
                    )
                owners[item] = stage.id
        self._owners = owners

    @classmethod
    def load(cls, path: Path) -> PriorityManifest:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported priority manifest version")
        return cls(
            tuple(
                PriorityStage(
                    str(row["id"]),
                    str(row["name"]),
                    tuple(str(item) for item in row.get("items", [])),
                )
                for row in payload.get("priorities", [])
            )
        )

    def priority_for(self, item: str) -> str | None:
        return self._owners.get(item)

    def may_start(self, target_stage: str, completed_stages: set[str]) -> bool:
        if target_stage not in self.EXPECTED:
            raise ValueError(f"unknown priority stage: {target_stage}")
        index = self.EXPECTED.index(target_stage)
        return set(self.EXPECTED[:index]).issubset(completed_stages)
