"""Pull-request change intelligence from Git diffs and the repository graph."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from codecortex.indexing.graph import GraphNode, ProjectGraph
from codecortex.indexing.impact import ImpactAnalyzer

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


@dataclass(frozen=True, slots=True)
class LineRange:
    start: int
    end: int

    def contains(self, line: int | None) -> bool:
        return line is not None and self.start <= line <= self.end


@dataclass(frozen=True, slots=True)
class PRFileChange:
    path: str
    status: str
    additions: int
    deletions: int
    changed_ranges: tuple[LineRange, ...]


@dataclass(frozen=True, slots=True)
class ChangedSymbol:
    node: GraphNode
    direct_change: bool
    impact_risk: float
    affected_nodes: int
    affected_tests: int


@dataclass(frozen=True, slots=True)
class PRReport:
    base_ref: str
    head_ref: str
    files: tuple[PRFileChange, ...]
    symbols: tuple[ChangedSymbol, ...]
    affected_tests: tuple[str, ...]
    risk_score: float
    risk_level: str


class PRIntelligence:
    def __init__(self, root: Path, graph: ProjectGraph, timeout_seconds: float = 15.0) -> None:
        self.root = root.resolve()
        self.graph = graph
        self.timeout_seconds = timeout_seconds

    def _git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root), *args],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return result.stdout if result.returncode == 0 else ""

    def analyze(self, base_ref: str, head_ref: str = "HEAD") -> PRReport:
        files = self._file_changes(base_ref, head_ref)
        changed_by_path = {change.path: change for change in files}
        symbols: list[ChangedSymbol] = []
        tests: set[str] = set()
        analyzer = ImpactAnalyzer(self.graph)

        for node in self.graph.nodes:
            if not node.path or node.path not in changed_by_path:
                continue
            if node.kind in {"file", "module", "reference"}:
                continue
            change = changed_by_path[node.path]
            direct = not change.changed_ranges or any(
                item.contains(node.line) for item in change.changed_ranges
            )
            if not direct:
                continue
            try:
                impact = analyzer.analyze(node.name)
                affected_nodes = len(impact.direct) + len(impact.indirect)
                affected_tests = len(impact.affected_tests)
                tests.update(
                    item.node.path or item.node.name for item in impact.affected_tests
                )
                risk = impact.risk_score
            except ValueError:
                affected_nodes = 0
                affected_tests = 0
                risk = 0.0
            symbols.append(
                ChangedSymbol(
                    node=node,
                    direct_change=True,
                    impact_risk=risk,
                    affected_nodes=affected_nodes,
                    affected_tests=affected_tests,
                )
            )

        churn = sum(item.additions + item.deletions for item in files)
        max_impact = max((item.impact_risk for item in symbols), default=0.0)
        breadth = min(1.0, len(files) / 20)
        churn_score = min(1.0, churn / 600)
        risk_score = min(1.0, max_impact * 0.55 + breadth * 0.25 + churn_score * 0.20)
        if risk_score >= 0.70:
            level = "high"
        elif risk_score >= 0.40:
            level = "medium"
        else:
            level = "low"
        symbols.sort(key=lambda item: (-item.impact_risk, item.node.path or "", item.node.line or 0))
        return PRReport(
            base_ref=base_ref,
            head_ref=head_ref,
            files=tuple(files),
            symbols=tuple(symbols),
            affected_tests=tuple(sorted(tests)),
            risk_score=round(risk_score, 4),
            risk_level=level,
        )

    def _file_changes(self, base_ref: str, head_ref: str) -> list[PRFileChange]:
        range_ref = f"{base_ref}...{head_ref}"
        numstat = self._git("diff", "--numstat", range_ref)
        statuses = self._git("diff", "--name-status", range_ref)
        patch = self._git("diff", "--unified=0", "--no-color", range_ref)

        stats: dict[str, tuple[int, int]] = {}
        for line in numstat.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                additions = int(parts[0]) if parts[0].isdigit() else 0
                deletions = int(parts[1]) if parts[1].isdigit() else 0
                stats[parts[-1]] = (additions, deletions)
        status_map: dict[str, str] = {}
        for line in statuses.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                status_map[parts[-1]] = parts[0]
        ranges: dict[str, list[LineRange]] = {}
        current_path: str | None = None
        for line in patch.splitlines():
            if line.startswith("+++ b/"):
                current_path = line[6:]
                ranges.setdefault(current_path, [])
                continue
            match = _HUNK.match(line)
            if current_path and match:
                start = int(match.group("start"))
                count = int(match.group("count") or "1")
                if count > 0:
                    ranges[current_path].append(LineRange(start, start + count - 1))

        paths = sorted(set(stats) | set(status_map) | set(ranges))
        return [
            PRFileChange(
                path=path,
                status=status_map.get(path, "M"),
                additions=stats.get(path, (0, 0))[0],
                deletions=stats.get(path, (0, 0))[1],
                changed_ranges=tuple(ranges.get(path, [])),
            )
            for path in paths
        ]
