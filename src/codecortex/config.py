"""Configuration for CodeCortex."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class CortexConfig(BaseModel):
    project_root: Path = Field(default_factory=lambda: Path.cwd())
    state_dir_name: str = ".codecortex"
    default_context_budget: int = Field(default=32_000, gt=0)
    hard_context_limit: int = Field(default=128_000, gt=0)
    telemetry_enabled: bool = True

    @property
    def state_dir(self) -> Path:
        return self.project_root / self.state_dir_name

    @property
    def memory_dir(self) -> Path:
        return self.state_dir / "memory"

    def ensure_directories(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
