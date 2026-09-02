"""Public HTTP API stability contract."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ApiVersion:
    version: str
    status: str
    breaking_changes_allowed: bool
    replacement: str | None = None


SUPPORTED_API_VERSIONS: tuple[ApiVersion, ...] = (
    ApiVersion("v1", "stable", False),
)


def current_api_version() -> str:
    stable = [item.version for item in SUPPORTED_API_VERSIONS if item.status == "stable"]
    if not stable:
        raise RuntimeError("CodeCortex has no stable API version")
    return stable[-1]


def version_manifest() -> dict[str, object]:
    return {
        "current": current_api_version(),
        "versions": [asdict(item) for item in SUPPORTED_API_VERSIONS],
        "compatibility_rule": "Breaking changes require a new API version.",
    }
