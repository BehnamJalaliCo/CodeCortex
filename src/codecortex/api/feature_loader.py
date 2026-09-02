"""Optional platform feature route loader.

Feature modules are independent so each roadmap capability can ship as a small,
reviewable unit without making the core API assembly monolithic.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Callable


@dataclass(slots=True)
class ApiRouteContext:
    prefix: str
    database: Any
    runtimes: Any
    principal: Callable[..., str]
    events: Any
    jobs: Any
    state_root: Path


_FEATURE_MODULES = (
    "codecortex.api.routes.git",
    "codecortex.api.routes.pr",
    "codecortex.api.routes.quality",
    "codecortex.api.routes.memory_center",
    "codecortex.api.routes.backends",
    "codecortex.api.routes.cluster",
    "codecortex.api.routes.organization",
    "codecortex.api.routes.audit",
    "codecortex.api.routes.code_actions",
    "codecortex.api.routes.integrations",
    "codecortex.api.routes.notifications",
    "codecortex.api.routes.observability",
    "codecortex.api.routes.performance",
)


def mount_optional_features(app: Any, context: ApiRouteContext) -> None:
    for module_name in _FEATURE_MODULES:
        try:
            module = import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise
        mount = getattr(module, "mount", None)
        if callable(mount):
            mount(app, context)
