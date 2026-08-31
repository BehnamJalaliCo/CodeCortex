"""Public guarded editing service used by CLI and MCP surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codecortex.backends.symbols import SymbolBackendAdapter
from codecortex.core.models import Capability
from codecortex.runtime import CortexRuntime


@dataclass(slots=True)
class EditService:
    runtime: CortexRuntime

    @property
    def root(self) -> Path:
        return self.runtime.config.project_root

    def backend(self) -> SymbolBackendAdapter:
        engine = self.runtime.registry.get(Capability.SYMBOLS)
        if not isinstance(engine, SymbolBackendAdapter):
            raise RuntimeError(
                "semantic editing requires the mature symbol backend; "
                "run `cortex backend install symbols`"
            )
        return engine

    def rename(self, path: str, name_path: str, new_name: str) -> dict[str, Any]:
        return self.backend().rename_symbol(name_path, path, new_name)

    def replace(self, path: str, name_path: str, body: str) -> dict[str, Any]:
        return self.backend().replace_symbol_body(name_path, path, body)

    def insert_before(self, path: str, name_path: str, body: str) -> dict[str, Any]:
        return self.backend().insert_before_symbol(name_path, path, body)

    def insert_after(self, path: str, name_path: str, body: str) -> dict[str, Any]:
        return self.backend().insert_after_symbol(name_path, path, body)
