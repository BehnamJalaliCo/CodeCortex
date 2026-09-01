"""Configuration loading and validation for CodeCortex."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class CortexConfig(BaseModel):
    project_root: Path = Field(default_factory=lambda: Path.cwd())
    state_dir_name: str = ".codecortex"
    default_context_budget: int = Field(default=32_000, gt=0)
    hard_context_limit: int = Field(default=128_000, gt=0)
    telemetry_enabled: bool = True

    @model_validator(mode="after")
    def _validate_context_limits(self) -> CortexConfig:
        if self.default_context_budget > self.hard_context_limit:
            raise ValueError("default_context_budget cannot exceed hard_context_limit")
        return self

    @property
    def state_dir(self) -> Path:
        return self.project_root / self.state_dir_name

    @property
    def memory_dir(self) -> Path:
        return self.state_dir / "memory"

    @property
    def config_path(self) -> Path:
        return self.state_dir / "config.json"

    @classmethod
    def load(cls, project_root: Path | None = None) -> CortexConfig:
        root = (project_root or Path.cwd()).expanduser().resolve()
        payload: dict[str, object] = {}
        path = root / ".codecortex" / "config.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                payload = raw
        except (OSError, json.JSONDecodeError):
            payload = {}

        values: dict[str, object] = {
            "project_root": root,
            "state_dir_name": str(payload.get("state_dir_name", ".codecortex")),
            "default_context_budget": int(payload.get("context_budget", payload.get("default_context_budget", 32_000))),
            "hard_context_limit": int(payload.get("hard_context_limit", 128_000)),
            "telemetry_enabled": bool(payload.get("telemetry", payload.get("telemetry_enabled", True))),
        }
        if os.getenv("CODECORTEX_CONTEXT_BUDGET"):
            values["default_context_budget"] = int(os.environ["CODECORTEX_CONTEXT_BUDGET"])
        if os.getenv("CODECORTEX_HARD_CONTEXT_LIMIT"):
            values["hard_context_limit"] = int(os.environ["CODECORTEX_HARD_CONTEXT_LIMIT"])
        if os.getenv("CODECORTEX_TELEMETRY"):
            values["telemetry_enabled"] = os.environ["CODECORTEX_TELEMETRY"].strip().lower() not in {"0", "false", "no", "off"}
        return cls.model_validate(values)

    def validate_budget(self, budget: int) -> int:
        if budget < 1:
            raise ValueError("context budget must be positive")
        if budget > self.hard_context_limit:
            raise ValueError(
                f"context budget {budget} exceeds hard limit {self.hard_context_limit}"
            )
        return budget

    def ensure_directories(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
