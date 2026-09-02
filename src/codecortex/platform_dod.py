"""Definition-of-Done validation for platform features."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FeatureCompletion:
    feature: str
    checks: dict[str, bool]


class DefinitionOfDone:
    def __init__(self, required: tuple[str, ...]) -> None:
        if not required or len(required) != len(set(required)):
            raise ValueError("Definition of Done checks must be non-empty and unique")
        self.required = required

    @classmethod
    def load(cls, path: Path) -> "DefinitionOfDone":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported Definition of Done version")
        return cls(tuple(str(item) for item in payload.get("required", [])))

    def validate(self, completion: FeatureCompletion) -> tuple[str, ...]:
        return tuple(item for item in self.required if completion.checks.get(item) is not True)

    def done(self, completion: FeatureCompletion) -> bool:
        return not self.validate(completion)
