"""Evidence-based architecture pattern inference with calibrated confidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from codecortex.indexing.graph import ProjectGraph


@dataclass(frozen=True, slots=True)
class ArchitectureHypothesis:
    name: str
    confidence: float
    evidence: tuple[str, ...]
    missing_signals: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArchitectureReport:
    primary: ArchitectureHypothesis | None
    alternatives: tuple[ArchitectureHypothesis, ...]
    analyzed_files: int
    analyzed_symbols: int


@dataclass(frozen=True, slots=True)
class _Pattern:
    name: str
    groups: tuple[tuple[str, tuple[str, ...], float], ...]


class ArchitectureInferenceEngine:
    """Infer architecture from path vocabulary, symbols, and graph relations.

    Confidence is evidence-derived rather than a binary label. A pattern only reaches
    high confidence when independent signal groups are present across the repository.
    """

    _PATTERNS = (
        _Pattern(
            "hexagonal",
            (
                ("domain", ("domain", "entities", "aggregate"), 0.24),
                ("ports", ("ports", "port", "interfaces"), 0.24),
                ("adapters", ("adapters", "adapter"), 0.22),
                ("application", ("application", "usecases", "use_cases"), 0.18),
                ("infrastructure", ("infrastructure", "infra"), 0.12),
            ),
        ),
        _Pattern(
            "clean-architecture",
            (
                ("domain", ("domain", "entities"), 0.25),
                ("use-cases", ("usecases", "use_cases", "application"), 0.25),
                ("interfaces", ("interfaces", "presenters", "controllers"), 0.20),
                ("infrastructure", ("infrastructure", "frameworks", "drivers"), 0.20),
                ("dependency-boundaries", ("repository", "gateway"), 0.10),
            ),
        ),
        _Pattern(
            "layered",
            (
                ("presentation", ("controllers", "controller", "api", "routes"), 0.22),
                ("service", ("services", "service"), 0.24),
                ("persistence", ("repositories", "repository", "dao"), 0.24),
                ("model", ("models", "model", "entities"), 0.16),
                ("configuration", ("config", "configuration"), 0.14),
            ),
        ),
        _Pattern(
            "mvc",
            (
                ("models", ("models", "model"), 0.34),
                ("views", ("views", "templates", "view"), 0.33),
                ("controllers", ("controllers", "controller"), 0.33),
            ),
        ),
        _Pattern(
            "service-repository",
            (
                ("services", ("services", "service"), 0.38),
                ("repositories", ("repositories", "repository"), 0.38),
                ("models", ("models", "entities", "model"), 0.14),
                ("contracts", ("protocol", "interface", "contracts"), 0.10),
            ),
        ),
        _Pattern(
            "monorepo",
            (
                ("apps", ("apps", "applications"), 0.30),
                ("packages", ("packages", "libs", "libraries"), 0.30),
                ("workspace", ("workspace", "workspaces"), 0.15),
                ("shared", ("shared", "common"), 0.15),
                ("tooling", ("tools", "tooling"), 0.10),
            ),
        ),
        _Pattern(
            "plugin-oriented",
            (
                ("plugins", ("plugins", "plugin", "extensions"), 0.42),
                ("adapters", ("adapters", "providers"), 0.22),
                ("registry", ("registry", "registries"), 0.18),
                ("hooks", ("hooks", "hook"), 0.18),
            ),
        ),
    )

    def analyze(self, graph: ProjectGraph, threshold: float = 0.20) -> ArchitectureReport:
        corpus = self._corpus(graph)
        hypotheses = [self._score(pattern, corpus) for pattern in self._PATTERNS]
        hypotheses = [item for item in hypotheses if item.confidence >= threshold]
        hypotheses.sort(key=lambda item: (-item.confidence, item.name))
        return ArchitectureReport(
            primary=hypotheses[0] if hypotheses else None,
            alternatives=tuple(hypotheses[1:4]),
            analyzed_files=sum(1 for node in graph.nodes if node.kind == "file"),
            analyzed_symbols=sum(
                1 for node in graph.nodes if node.kind not in {"file", "module", "reference"}
            ),
        )

    @staticmethod
    def _corpus(graph: ProjectGraph) -> set[str]:
        terms: set[str] = set()
        for node in graph.nodes:
            if node.path:
                path = PurePosixPath(node.path)
                for part in path.parts:
                    stem = PurePosixPath(part).stem.lower().replace("-", "_")
                    terms.add(stem)
                    terms.update(piece for piece in stem.split("_") if piece)
            name = node.name.lower().replace("-", "_")
            terms.add(name)
            terms.update(piece for piece in name.split("_") if piece)
        return terms

    @staticmethod
    def _score(pattern: _Pattern, corpus: set[str]) -> ArchitectureHypothesis:
        confidence = 0.0
        evidence: list[str] = []
        missing: list[str] = []
        matched_groups = 0
        for label, aliases, weight in pattern.groups:
            matches = sorted(alias for alias in aliases if alias in corpus)
            if matches:
                confidence += weight
                matched_groups += 1
                evidence.append(f"{label}: {', '.join(matches[:3])}")
            else:
                missing.append(label)
        # Independent groups matter more than repeated vocabulary from one layer.
        diversity = matched_groups / max(1, len(pattern.groups))
        confidence *= 0.70 + 0.30 * diversity
        return ArchitectureHypothesis(
            name=pattern.name,
            confidence=round(min(1.0, confidence), 4),
            evidence=tuple(evidence),
            missing_signals=tuple(missing),
        )
