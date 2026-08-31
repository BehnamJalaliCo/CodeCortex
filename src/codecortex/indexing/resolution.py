"""Cross-file symbol resolution with explicit confidence and ambiguity."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from codecortex.indexing.graph import GraphNode


@dataclass(frozen=True, slots=True)
class ResolutionCandidate:
    node_id: str
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    target_id: str | None
    confidence: float
    ambiguity: float
    candidates: tuple[ResolutionCandidate, ...]


class CrossFileResolver:
    """Rank same-name symbols while preserving uncertainty for downstream agents."""

    def resolve(
        self,
        name: str,
        source_path: str,
        candidates: list[GraphNode],
        relation_kind: str,
    ) -> ResolutionResult:
        ranked: list[ResolutionCandidate] = []
        source = PurePosixPath(source_path)
        for node in candidates:
            if node.path is None:
                continue
            target = PurePosixPath(node.path)
            score = 0.35
            reasons = ["exact_symbol_name"]
            if target == source:
                score += 0.35
                reasons.append("same_file")
            elif target.parent == source.parent:
                score += 0.20
                reasons.append("same_directory")
            else:
                shared = len(set(source.parts[:-1]) & set(target.parts[:-1]))
                if shared:
                    score += min(0.12, shared * 0.03)
                    reasons.append("shared_package_path")
            if relation_kind == "calls" and node.kind in {
                "function",
                "async_function",
                "method",
            }:
                score += 0.08
                reasons.append("callable_kind")
            if relation_kind in {"inherits", "implements"} and node.kind in {
                "class",
                "interface",
            }:
                score += 0.08
                reasons.append("type_kind")
            ranked.append(
                ResolutionCandidate(
                    node_id=node.id,
                    score=min(1.0, score),
                    reasons=tuple(reasons),
                )
            )
        ranked.sort(key=lambda item: (-item.score, item.node_id))
        if not ranked:
            return ResolutionResult(None, 0.0, 1.0, ())
        best = ranked[0]
        second = ranked[1].score if len(ranked) > 1 else 0.0
        margin = max(0.0, best.score - second)
        ambiguity = 0.0 if len(ranked) == 1 else max(0.0, min(1.0, 1.0 - margin))
        confidence = max(0.0, min(1.0, best.score * (1.0 - 0.45 * ambiguity)))
        return ResolutionResult(
            target_id=best.node_id,
            confidence=confidence,
            ambiguity=ambiguity,
            candidates=tuple(ranked[:5]),
        )
