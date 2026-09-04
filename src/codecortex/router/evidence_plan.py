"""Decide which optional evidence layers a request should consult.

Routing is deliberately conservative: precision navigation and structural search
are local and cheap, so they are proposed whenever the wording calls for them,
while the remote documentation layer is proposed only for questions that are
actually about a third-party library. A question such as "where is AuthService
defined?" never triggers a network call.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from codecortex.core.models import AgentRequest, RequestKind


class EvidenceLayer(StrEnum):
    PRECISION = "precision"
    DEPENDENCY_DOCS = "dependency_docs"
    STRUCTURAL = "structural"


_PRECISION_TERMS = (
    "definition",
    "defined",
    "declaration",
    "references",
    "reference",
    "who calls",
    "callers",
    "call sites",
    "usages",
    "implements",
    "implementation",
    "implementations",
    "subclass",
    "override",
)

_DEPENDENCY_TERMS = (
    "library",
    "package",
    "dependency",
    "dependencies",
    "upgrade",
    "migrate",
    "migration",
    "deprecated",
    "deprecation",
    "framework",
    "sdk",
    "api version",
    "installed version",
    "compatible",
    "compatibility",
    "breaking change",
    "release notes",
    "changelog",
    "supported api",
    "current api",
)

_STRUCTURAL_TERMS = (
    "all usages",
    "all calls",
    "every call",
    "pattern",
    "shaped like",
    "codemod",
    "rewrite",
    "replace all",
    "find all",
    "across the codebase",
    "mechanical",
    "bulk",
)


@dataclass(frozen=True, slots=True)
class EvidencePlan:
    """Which optional layers to consult, and why."""

    layers: tuple[EvidenceLayer, ...] = ()
    reasons: tuple[str, ...] = ()

    def wants(self, layer: EvidenceLayer) -> bool:
        return layer in self.layers

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "layers": [item.value for item in self.layers],
            "reasons": list(self.reasons),
        }


def plan_evidence(request: AgentRequest, kind: RequestKind) -> EvidencePlan:
    """Classify a request into the optional evidence layers worth consulting."""
    text = request.query.lower()
    layers: list[EvidenceLayer] = []
    reasons: list[str] = []

    def add(layer: EvidenceLayer, reason: str) -> None:
        if layer not in layers:
            layers.append(layer)
            reasons.append(reason)

    if request.metadata.get("path") and request.metadata.get("line"):
        add(EvidenceLayer.PRECISION, "the request names an exact file position")
    if any(term in text for term in _PRECISION_TERMS):
        add(EvidenceLayer.PRECISION, "the request asks about symbol relationships")
    if kind in {RequestKind.LOCATE, RequestKind.REFACTOR}:
        add(EvidenceLayer.PRECISION, f"a {kind.value} request benefits from exact navigation")

    if any(term in text for term in _DEPENDENCY_TERMS):
        add(EvidenceLayer.DEPENDENCY_DOCS, "the request concerns a third-party dependency")
    if request.metadata.get("library"):
        add(EvidenceLayer.DEPENDENCY_DOCS, "the request names a library explicitly")

    if any(term in text for term in _STRUCTURAL_TERMS):
        add(EvidenceLayer.STRUCTURAL, "the request describes a repeated code shape")
    if request.metadata.get("structural_pattern"):
        add(EvidenceLayer.STRUCTURAL, "the request carries a structural pattern")
    if kind is RequestKind.REFACTOR and any(
        term in text for term in ("all", "every", "everywhere")
    ):
        add(EvidenceLayer.STRUCTURAL, "a broad refactor benefits from structural matching")

    return EvidencePlan(layers=tuple(layers), reasons=tuple(reasons))
