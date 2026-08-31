"""Architecture fingerprinting and drift detection."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from codecortex.architecture.inference import ArchitectureInferenceEngine
from codecortex.indexing.graph import ProjectGraph


@dataclass(frozen=True, slots=True)
class ArchitectureFingerprint:
    version: int
    pattern: str | None
    confidence: float
    dependency_counts: dict[str, int]
    zone_file_counts: dict[str, int]
    unresolved_ratio: float

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)

    @classmethod
    def load(cls, path: Path) -> ArchitectureFingerprint | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                version=int(payload["version"]),
                pattern=str(payload["pattern"]) if payload.get("pattern") else None,
                confidence=float(payload["confidence"]),
                dependency_counts={str(k): int(v) for k, v in payload["dependency_counts"].items()},
                zone_file_counts={str(k): int(v) for k, v in payload["zone_file_counts"].items()},
                unresolved_ratio=float(payload["unresolved_ratio"]),
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None


@dataclass(frozen=True, slots=True)
class DriftFinding:
    kind: str
    severity: str
    score: float
    message: str
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArchitectureDriftReport:
    drifted: bool
    score: float
    findings: tuple[DriftFinding, ...]


class ArchitectureDriftDetector:
    VERSION = 1

    def fingerprint(self, graph: ProjectGraph) -> ArchitectureFingerprint:
        report = ArchitectureInferenceEngine().analyze(graph)
        node_map = {node.id: node for node in graph.nodes}
        dependencies: Counter[str] = Counter()
        zones: Counter[str] = Counter()
        unresolved = 0
        relevant_edges = 0
        for node in graph.nodes:
            if node.kind == "file" and node.path:
                zones[self._zone(node.path)] += 1
        for edge in graph.edges:
            if edge.kind not in {"calls", "imports", "inherits", "implements"}:
                continue
            relevant_edges += 1
            source = node_map.get(edge.source)
            target = node_map.get(edge.target)
            if target is None or target.kind in {"reference", "module"}:
                unresolved += 1
            source_zone = self._zone(source.path) if source and source.path else "external"
            target_zone = self._zone(target.path) if target and target.path else "external"
            dependencies[f"{source_zone}->{target_zone}:{edge.kind}"] += 1
        primary = report.primary
        return ArchitectureFingerprint(
            version=self.VERSION,
            pattern=primary.name if primary else None,
            confidence=primary.confidence if primary else 0.0,
            dependency_counts=dict(sorted(dependencies.items())),
            zone_file_counts=dict(sorted(zones.items())),
            unresolved_ratio=unresolved / max(1, relevant_edges),
        )

    def compare(
        self,
        baseline: ArchitectureFingerprint,
        current: ArchitectureFingerprint,
        dependency_growth_limit: float = 0.75,
    ) -> ArchitectureDriftReport:
        findings: list[DriftFinding] = []
        if baseline.pattern and current.pattern and baseline.pattern != current.pattern:
            findings.append(
                DriftFinding(
                    "primary-pattern-change",
                    "high",
                    0.90,
                    f"Primary architecture changed from {baseline.pattern} to {current.pattern}.",
                    (f"baseline={baseline.confidence:.2f}", f"current={current.confidence:.2f}"),
                )
            )
        elif baseline.confidence - current.confidence >= 0.20:
            findings.append(
                DriftFinding(
                    "pattern-confidence-drop",
                    "medium",
                    0.55,
                    "Architecture pattern confidence dropped materially.",
                    (f"{baseline.confidence:.2f}->{current.confidence:.2f}",),
                )
            )

        for signature, count in current.dependency_counts.items():
            before = baseline.dependency_counts.get(signature, 0)
            if before == 0 and count > 0:
                severity = "high" if any(kind in signature for kind in (":calls", ":inherits")) else "medium"
                findings.append(
                    DriftFinding(
                        "new-dependency-direction",
                        severity,
                        0.70 if severity == "high" else 0.45,
                        f"New dependency direction detected: {signature}.",
                        (f"count={count}",),
                    )
                )
                continue
            growth = (count - before) / max(1, before)
            if count - before >= 2 and growth > dependency_growth_limit:
                findings.append(
                    DriftFinding(
                        "dependency-growth",
                        "medium",
                        min(0.70, 0.35 + growth * 0.20),
                        f"Dependency volume increased sharply: {signature}.",
                        (f"{before}->{count}", f"growth={growth:.0%}"),
                    )
                )

        unresolved_delta = current.unresolved_ratio - baseline.unresolved_ratio
        if unresolved_delta >= 0.12:
            findings.append(
                DriftFinding(
                    "resolution-quality-drop",
                    "medium",
                    min(0.65, 0.40 + unresolved_delta),
                    "Unresolved dependency ratio increased.",
                    (
                        f"{baseline.unresolved_ratio:.2%}->{current.unresolved_ratio:.2%}",
                    ),
                )
            )

        score = 1.0
        for finding in findings:
            score *= 1.0 - min(0.95, finding.score)
        aggregate = round(1.0 - score, 4)
        findings.sort(key=lambda item: (-item.score, item.kind))
        return ArchitectureDriftReport(
            drifted=bool(findings),
            score=aggregate,
            findings=tuple(findings),
        )

    @staticmethod
    def _zone(path: str) -> str:
        parts = PurePosixPath(path).parts
        ignored = {"src", "lib", "app", "source"}
        for part in parts[:-1]:
            normalized = part.lower().replace("-", "_")
            if normalized not in ignored:
                return normalized
        return "root"
