"""Canonical product capability manifest for the CodeCortex Platform."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ProductCapability:
    key: str
    group: str
    surface: str
    mutating: bool = False


CAPABILITIES: tuple[ProductCapability, ...] = (
    ProductCapability("repository-intelligence", "intelligence", "repository"),
    ProductCapability("symbol-intelligence", "intelligence", "symbols"),
    ProductCapability("semantic-retrieval", "intelligence", "search"),
    ProductCapability("knowledge-graph", "intelligence", "graph"),
    ProductCapability("context-optimization", "intelligence", "context"),
    ProductCapability("impact-analysis", "engineering", "impact"),
    ProductCapability("architecture-intelligence", "engineering", "architecture"),
    ProductCapability("git-intelligence", "engineering", "git"),
    ProductCapability("pr-intelligence", "engineering", "pr"),
    ProductCapability("quality-regression", "engineering", "quality"),
    ProductCapability("routing", "runtime", "routing"),
    ProductCapability("tracing", "runtime", "traces"),
    ProductCapability("observability", "runtime", "observability"),
    ProductCapability("team-memory", "knowledge", "memory", True),
    ProductCapability("backend-management", "administration", "backends", True),
    ProductCapability("integrations", "administration", "integrations", True),
    ProductCapability("organization-rbac", "administration", "organization", True),
    ProductCapability("audit", "administration", "audit"),
    ProductCapability("notifications", "administration", "notifications", True),
    ProductCapability("distributed-cluster", "scale", "cluster", True),
    ProductCapability("performance-scale", "scale", "performance", True),
    ProductCapability("safe-code-actions", "development", "code-actions", True),
)


def product_manifest() -> dict[str, object]:
    groups = sorted({item.group for item in CAPABILITIES})
    return {
        "product": "CodeCortex Platform",
        "console": "CodeCortex Console",
        "control_plane": "CodeCortex Control Plane",
        "hierarchy": ["organization", "workspace", "repository", "revision"],
        "groups": groups,
        "capabilities": [asdict(item) for item in CAPABILITIES],
    }
