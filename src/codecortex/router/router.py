"""Deterministic adaptive router with outcome feedback."""

from __future__ import annotations

from codecortex.core.models import AgentRequest, Capability, RequestKind, RoutePlan, RouteScore
from codecortex.feedback import AgentFeedbackStore


class AdaptiveRouter:
    _kind_terms: dict[RequestKind, tuple[str, ...]] = {
        RequestKind.LOCATE: ("find", "where", "locate", "symbol", "definition", "reference"),
        RequestKind.DEBUG: ("bug", "debug", "error", "fail", "crash", "race", "trace"),
        RequestKind.REFACTOR: ("refactor", "rename", "extract", "move", "restructure"),
        RequestKind.CHANGE: ("change", "edit", "implement", "add", "remove", "fix"),
        RequestKind.REVIEW: ("review", "risk", "regression", "security", "inspect"),
        RequestKind.EXPLAIN: ("explain", "why", "how", "architecture", "understand"),
    }

    def __init__(
        self,
        default_budget: int = 32_000,
        feedback: AgentFeedbackStore | None = None,
    ) -> None:
        self.default_budget = default_budget
        self.feedback = feedback

    def route(self, request: AgentRequest) -> RoutePlan:
        text = request.query.lower()
        kind = request.kind if request.kind != RequestKind.UNKNOWN else self._classify(text)
        scores = {
            Capability.REPOSITORY: 0.35,
            Capability.SYMBOLS: 0.30,
            Capability.CONTEXT: 0.45,
            Capability.MEMORY: 0.20,
            Capability.VALIDATION: 0.10,
        }
        if kind in {RequestKind.EXPLAIN, RequestKind.DEBUG, RequestKind.REVIEW}:
            scores[Capability.REPOSITORY] += 0.45
        if kind in {
            RequestKind.LOCATE,
            RequestKind.DEBUG,
            RequestKind.REFACTOR,
            RequestKind.CHANGE,
        }:
            scores[Capability.SYMBOLS] += 0.50
        if kind in {
            RequestKind.DEBUG,
            RequestKind.REFACTOR,
            RequestKind.CHANGE,
            RequestKind.REVIEW,
        }:
            scores[Capability.VALIDATION] += 0.55
        if any(term in text for term in ("history", "previous", "decision", "remember", "again")):
            scores[Capability.MEMORY] += 0.65
        if any(term in text for term in ("large", "logs", "context", "tokens", "many files")):
            scores[Capability.CONTEXT] += 0.35

        repository_files = request.metadata.get("repository_files")
        if isinstance(repository_files, int) and repository_files >= 100_000:
            scores[Capability.CONTEXT] += 0.20
            scores[Capability.REPOSITORY] += 0.10
        if request.metadata.get("latency_sensitive"):
            scores[Capability.CONTEXT] -= 0.10
            scores[Capability.MEMORY] -= 0.05
        preferred = request.metadata.get("preferred_capabilities", [])
        if isinstance(preferred, list):
            for value in preferred:
                try:
                    scores[Capability(str(value))] += 0.20
                except ValueError:
                    continue
        if self.feedback is not None:
            for capability in scores:
                scores[capability] += self.feedback.routing_adjustment(capability)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        route_scores = [
            RouteScore(
                capability=capability,
                score=max(0.0, min(score, 1.0)),
                reason=self._reason(capability, kind),
            )
            for capability, score in ranked
        ]
        selected = [item.capability for item in route_scores if item.score >= 0.50]
        if not selected:
            selected = [Capability.REPOSITORY]
        return RoutePlan(
            request_kind=kind,
            scores=route_scores,
            selected=selected,
            context_budget=self.default_budget,
        )

    def _classify(self, text: str) -> RequestKind:
        matches: list[tuple[int, RequestKind]] = []
        for kind, terms in self._kind_terms.items():
            count = sum(1 for term in terms if term in text)
            if count:
                matches.append((count, kind))
        if not matches:
            return RequestKind.EXPLAIN
        matches.sort(key=lambda item: item[0], reverse=True)
        return matches[0][1]

    @staticmethod
    def _reason(capability: Capability, kind: RequestKind) -> str:
        return f"{capability.value} is relevant to a {kind.value} request"
