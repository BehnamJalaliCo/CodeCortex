"""Configuration loading and validation for CodeCortex."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


def _as_int(value: object, default: int) -> int:
    """Coerce a JSON value to an int, falling back to a documented default."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        return int(value)
    except ValueError:
        return default



class PrecisionIndexConfig(BaseModel):
    """Optional compiler/indexer-grade symbol index used for exact navigation."""

    enabled: bool = True
    path: str | None = None
    auto_generate: bool = False
    generator_command: tuple[str, ...] = ()
    generator_timeout_seconds: float = Field(default=900.0, gt=0)
    max_index_bytes: int = Field(default=256 * 1024 * 1024, gt=0)
    #: Largest source file read back for column conversion. Files above this
    #: are not converted rather than being loaded into memory.
    max_source_bytes: int = Field(default=8 * 1024 * 1024, gt=0)
    #: How long a computed freshness verdict may be reused before the indexed
    #: documents are checked again. Zero, the default, means every check scans
    #: the whole index, so an edit is never missed. A positive value trades
    #: that guarantee for fewer stat calls on a very large index: an edit made
    #: within the window is not seen until it expires. Raise it deliberately.
    freshness_ttl_seconds: float = Field(default=0.0, ge=0)


class DependencyDocsConfig(BaseModel):
    """Optional external documentation provider for resolved dependency versions."""

    enabled: bool = False
    provider: str = "remote"
    base_url: str = ""
    api_key_env: str = "CODECORTEX_DEPENDENCY_DOCS_API_KEY"
    connect_timeout_seconds: float = Field(default=5.0, gt=0)
    read_timeout_seconds: float = Field(default=20.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=5)
    max_response_bytes: int = Field(default=1_048_576, gt=0)
    cache_ttl_seconds: int = Field(default=86_400, gt=0)
    serve_stale_when_offline: bool = True


class StructuralConfig(BaseModel):
    """Optional syntax-aware search and guarded rewrite engine."""

    enabled: bool = True
    command: str | None = None
    command_args: tuple[str, ...] = ()
    timeout_seconds: float = Field(default=120.0, gt=0)
    max_output_bytes: int = Field(default=32 * 1024 * 1024, gt=0)
    max_results: int = Field(default=500, gt=0)
    max_rewrite_files: int = Field(default=50, gt=0)
    max_rewrite_matches: int = Field(default=500, gt=0)
    max_rewrite_bytes: int = Field(default=1_048_576, gt=0)
    preview_ttl_seconds: int = Field(default=1_800, gt=0)
    allow_apply: bool = True


class CortexConfig(BaseModel):
    project_root: Path = Field(default_factory=lambda: Path.cwd())
    state_dir_name: str = ".codecortex"
    default_context_budget: int = Field(default=32_000, gt=0)
    hard_context_limit: int = Field(default=128_000, gt=0)
    telemetry_enabled: bool = True
    precision_index: PrecisionIndexConfig = Field(default_factory=PrecisionIndexConfig)
    dependency_docs: DependencyDocsConfig = Field(default_factory=DependencyDocsConfig)
    structural: StructuralConfig = Field(default_factory=StructuralConfig)

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
    def cache_dir(self) -> Path:
        return self.state_dir / "cache"

    @property
    def runtime_dir(self) -> Path:
        return self.state_dir / "runtime"

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
            "default_context_budget": _as_int(
                payload.get("context_budget", payload.get("default_context_budget")), 32_000
            ),
            "hard_context_limit": _as_int(payload.get("hard_context_limit"), 128_000),
            "telemetry_enabled": bool(
                payload.get("telemetry", payload.get("telemetry_enabled", True))
            ),
        }
        for key, model in (
            ("precision_index", PrecisionIndexConfig),
            ("dependency_docs", DependencyDocsConfig),
            ("structural", StructuralConfig),
        ):
            section = payload.get(key)
            try:
                values[key] = model.model_validate(section) if isinstance(section, dict) else model()
            except ValueError:
                # A malformed optional section must never break local operation.
                values[key] = model()
        if os.getenv("CODECORTEX_CONTEXT_BUDGET"):
            values["default_context_budget"] = int(os.environ["CODECORTEX_CONTEXT_BUDGET"])
        if os.getenv("CODECORTEX_HARD_CONTEXT_LIMIT"):
            values["hard_context_limit"] = int(os.environ["CODECORTEX_HARD_CONTEXT_LIMIT"])
        if os.getenv("CODECORTEX_TELEMETRY"):
            values["telemetry_enabled"] = os.environ[
                "CODECORTEX_TELEMETRY"
            ].strip().lower() not in {"0", "false", "no", "off"}
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
