"""Product-level identity and capability taxonomy for the CodeCortex platform."""

from __future__ import annotations

from dataclasses import dataclass


PLATFORM_NAME = "CodeCortex"
CONSOLE_NAME = "CodeCortex Console"
PLATFORM_API_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class PlatformCapabilities:
    """Stable product capability groups exposed across CLI, MCP and web transports."""

    intelligence: tuple[str, ...] = (
        "repository",
        "symbols",
        "graph",
        "retrieval",
        "context",
        "impact",
        "architecture",
        "git",
        "pull_requests",
    )
    operations: tuple[str, ...] = (
        "tracing",
        "telemetry",
        "benchmarks",
        "backends",
        "jobs",
        "workers",
    )
    collaboration: tuple[str, ...] = (
        "workspaces",
        "memory",
        "organizations",
        "policies",
        "audit",
    )

    def all(self) -> tuple[str, ...]:
        return (*self.intelligence, *self.operations, *self.collaboration)


CAPABILITIES = PlatformCapabilities()
