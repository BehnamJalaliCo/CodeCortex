"""Configuration-driven optional backend specifications."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BackendSpec:
    key: str
    capabilities: tuple[str, ...]
    package: str = ""
    source_url: str = ""
    revision: str = ""
    command: str = ""
    license_id: str = ""
    extras: tuple[str, ...] = ()
    python: str = "3.13"
    vendor_path: str | None = None

    @property
    def configured(self) -> bool:
        return bool(
            self.package
            and self.source_url
            and len(self.revision) == 40
            and self.command
        )

    @property
    def source_requirement(self) -> str:
        if not self.configured:
            raise RuntimeError(f"backend {self.key!r} is not configured")
        if not self.extras:
            return f"git+{self.source_url}@{self.revision}"
        extras = ",".join(self.extras)
        return f"{self.package}[{extras}] @ git+{self.source_url}@{self.revision}"


def _external_spec(
    key: str,
    capabilities: tuple[str, ...],
    *,
    default_extras: tuple[str, ...] = (),
) -> BackendSpec:
    prefix = f"CODECORTEX_{key.upper()}_BACKEND"
    extras_value = os.getenv(f"{prefix}_EXTRAS", "").strip()
    extras = (
        tuple(part.strip() for part in extras_value.split(",") if part.strip())
        if extras_value
        else default_extras
    )
    vendor_path = os.getenv(f"{prefix}_LOCAL_PATH", "").strip() or None
    return BackendSpec(
        key=key,
        capabilities=capabilities,
        package=os.getenv(f"{prefix}_PACKAGE", "").strip(),
        source_url=os.getenv(f"{prefix}_SOURCE_URL", "").strip(),
        revision=os.getenv(f"{prefix}_REVISION", "").strip(),
        command=os.getenv(f"{prefix}_COMMAND", "").strip(),
        license_id=os.getenv(f"{prefix}_LICENSE", "").strip(),
        extras=extras,
        python=os.getenv(f"{prefix}_PYTHON", "3.13").strip() or "3.13",
        vendor_path=vendor_path,
    )


BACKENDS: dict[str, BackendSpec] = {
    "graph": _external_spec(
        "graph",
        ("ast", "graph", "query", "path", "explain", "incremental"),
    ),
    "symbols": _external_spec(
        "symbols",
        ("lsp", "symbols", "references", "diagnostics", "editing", "refactor"),
    ),
    "context": _external_spec(
        "context",
        ("compression", "routing", "reversible", "memory", "proxy", "mcp"),
        default_extras=("mcp", "code", "memory", "relevance"),
    ),
}
