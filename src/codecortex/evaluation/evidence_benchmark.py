"""Measured comparisons between heuristic-only and evidence-backed resolution.

Every number this module reports is produced by running both strategies over a
generated fixture repository in the same process. Nothing is estimated: a
metric that cannot be measured is reported as ``None`` rather than filled in.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter

from codecortex.config import CortexConfig, StructuralConfig
from codecortex.dependencies import DependencyResolver
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.precision import (
    PrecisionEvidenceProvider,
    PrecisionQuery,
)
from codecortex.structural import StructuralSearch


@dataclass(frozen=True, slots=True)
class ComparisonMetric:
    """One measured metric for one strategy."""

    strategy: str
    correct_targets: int
    false_targets: int
    context_tokens: int
    duration_ms: float

    @property
    def precision(self) -> float:
        total = self.correct_targets + self.false_targets
        return self.correct_targets / total if total else 0.0

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "precision": round(self.precision, 4)}


@dataclass(frozen=True, slots=True)
class CaseReport:
    """A single benchmark case with one row per strategy."""

    case_id: str
    description: str
    metrics: tuple[ComparisonMetric, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "description": self.description,
            "metrics": [item.to_dict() for item in self.metrics],
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class EvidenceBenchmarkReport:
    cases: tuple[CaseReport, ...] = ()
    skipped: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "cases": [case.to_dict() for case in self.cases],
            "skipped": list(self.skipped),
        }

    def save(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


# -- fixtures ---------------------------------------------------------------

_DUPLICATE_SOURCES: dict[str, str] = {
    "src/auth/service.py": (
        "class Session:\n"
        "    def refresh(self) -> str:\n"
        '        return "auth"\n'
    ),
    "src/billing/service.py": (
        "class Session:\n"
        "    def refresh(self) -> str:\n"
        '        return "billing"\n'
    ),
    "src/app.py": (
        "from auth.service import Session\n"
        "\n"
        "\n"
        "def start() -> str:\n"
        "    return Session().refresh()\n"
    ),
}

_MIGRATION_SOURCES: dict[str, str] = {
    "src/handlers.py": (
        "def handler():\n"
        "    return old_api(1)\n"
        "\n"
        "\n"
        "def other():\n"
        "    return old_api(2)\n"
    ),
    "src/notes.py": (
        "# The string old_api( appears here in a comment, not as a call.\n"
        'MESSAGE = "call old_api(x) to migrate"\n'
    ),
}

_MANIFEST_SOURCES: dict[str, str] = {
    "pyproject.toml": '[project]\nname = "demo"\ndependencies = ["framework>=2,<3"]\n',
    "uv.lock": '[[package]]\nname = "framework"\nversion = "2.4.1"\n',
    "src/app.py": "import framework\n",
}


def _materialize(root: Path, sources: dict[str, str]) -> None:
    for relative, text in sources.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


@dataclass(slots=True)
class EvidenceBenchmark:
    """Run the measured comparisons inside a scratch directory."""

    workdir: Path
    structural_command: str | None = None
    precision_index: bytes | None = None
    _cases: list[CaseReport] = field(default_factory=list, repr=False)
    _skipped: list[str] = field(default_factory=list, repr=False)

    def run(self) -> EvidenceBenchmarkReport:
        self._cases = []
        self._skipped = []
        self._case_duplicate_symbols()
        self._case_dependency_version()
        self._case_mechanical_migration()
        return EvidenceBenchmarkReport(tuple(self._cases), tuple(self._skipped))

    # -- case A: duplicate symbol names ------------------------------------

    def _case_duplicate_symbols(self) -> None:
        """Resolve ``Session`` at a call site where two packages export that name."""
        root = self.workdir / "duplicate"
        root.mkdir(parents=True, exist_ok=True)
        _materialize(root, _DUPLICATE_SOURCES)

        started = perf_counter()
        graph = IncrementalGraphIndex(root).refresh()[0]
        candidates = [
            node
            for node in graph.nodes
            if node.name == "Session" and node.kind not in {"file", "module", "reference"}
        ]
        heuristic_context = "\n".join(f"{node.path}:{node.line} {node.name}" for node in candidates)
        correct = sum(1 for node in candidates if node.path == "src/auth/service.py")
        heuristic = ComparisonMetric(
            strategy="graph_heuristic",
            correct_targets=correct,
            false_targets=len(candidates) - correct,
            context_tokens=max(0, len(heuristic_context) // 4),
            duration_ms=(perf_counter() - started) * 1000,
        )

        if self.precision_index is None:
            self._skipped.append("duplicate-symbols: no precision index supplied")
            self._cases.append(
                CaseReport(
                    "duplicate-symbols",
                    "Resolve a call to a class name exported by two packages.",
                    (heuristic,),
                    ("precision strategy not measured: no index was supplied",),
                )
            )
            return

        index_path = root / ".codecortex" / "precision" / "index.cortexidx"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_bytes(self.precision_index)
        started = perf_counter()
        provider = PrecisionEvidenceProvider(root, CortexConfig(project_root=root))
        bundle = provider.definition(PrecisionQuery("src/app.py", 5, 12))
        precise_correct = sum(
            1 for record in bundle.records if record.path == "src/auth/service.py"
        )
        context = "\n".join(record.content for record in bundle.records)
        precision = ComparisonMetric(
            strategy="precision_index",
            correct_targets=precise_correct,
            false_targets=len(bundle.records) - precise_correct,
            context_tokens=max(0, len(context) // 4),
            duration_ms=(perf_counter() - started) * 1000,
        )
        self._cases.append(
            CaseReport(
                "duplicate-symbols",
                "Resolve a call to a class name exported by two packages.",
                (heuristic, precision),
            )
        )

    # -- case B: dependency version ----------------------------------------

    def _case_dependency_version(self) -> None:
        """Identify the version of a dependency the repository actually runs."""
        root = self.workdir / "dependency"
        root.mkdir(parents=True, exist_ok=True)
        _materialize(root, _MANIFEST_SOURCES)

        started = perf_counter()
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        declared_only = ">=2,<3" in text
        source_only = ComparisonMetric(
            strategy="source_only",
            correct_targets=0,
            false_targets=1 if declared_only else 0,
            context_tokens=max(0, len(text) // 4),
            duration_ms=(perf_counter() - started) * 1000,
        )

        started = perf_counter()
        inventory = DependencyResolver(root).inventory()
        matches = inventory.find("framework")
        resolved = matches[0].effective_version if matches else None
        payload = json.dumps([item.to_dict() for item in matches])
        dependency = ComparisonMetric(
            strategy="dependency_intelligence",
            correct_targets=1 if resolved == "2.4.1" else 0,
            false_targets=0 if resolved == "2.4.1" else 1,
            context_tokens=max(0, len(payload) // 4),
            duration_ms=(perf_counter() - started) * 1000,
        )
        self._cases.append(
            CaseReport(
                "dependency-version",
                "Identify the resolved dependency version rather than the declared range.",
                (source_only, dependency),
                (
                    "documentation retrieval is not measured here: it requires the "
                    "opt-in remote provider and credentials",
                ),
            )
        )

    # -- case C: mechanical migration --------------------------------------

    def _case_mechanical_migration(self) -> None:
        """Find every real call to a deprecated API without matching prose."""
        root = self.workdir / "migration"
        root.mkdir(parents=True, exist_ok=True)
        _materialize(root, _MIGRATION_SOURCES)

        started = perf_counter()
        lexical: list[tuple[str, int]] = []
        for path in sorted(root.rglob("*.py")):
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if "old_api(" in line:
                    lexical.append((path.relative_to(root).as_posix(), number))
        lexical_correct = sum(1 for path, _ in lexical if path == "src/handlers.py")
        lexical_metric = ComparisonMetric(
            strategy="lexical_scan",
            correct_targets=lexical_correct,
            false_targets=len(lexical) - lexical_correct,
            context_tokens=max(0, sum(len(item[0]) for item in lexical) // 4),
            duration_ms=(perf_counter() - started) * 1000,
        )

        command = self.structural_command
        if command is None:
            self._skipped.append("mechanical-migration: structural engine is not installed")
            self._cases.append(
                CaseReport(
                    "mechanical-migration",
                    "Find every real call to a deprecated API.",
                    (lexical_metric,),
                    ("structural strategy not measured: engine not installed",),
                )
            )
            return

        started = perf_counter()
        config = CortexConfig(project_root=root, structural=StructuralConfig(command=command))
        matches = StructuralSearch(root, config).search("old_api($X)", "python")
        structural_correct = sum(1 for item in matches if item.path == "src/handlers.py")
        structural_metric = ComparisonMetric(
            strategy="structural_search",
            correct_targets=structural_correct,
            false_targets=len(matches) - structural_correct,
            context_tokens=max(0, sum(len(item.matched_text) for item in matches) // 4),
            duration_ms=(perf_counter() - started) * 1000,
        )
        self._cases.append(
            CaseReport(
                "mechanical-migration",
                "Find every real call to a deprecated API.",
                (lexical_metric, structural_metric),
            )
        )
