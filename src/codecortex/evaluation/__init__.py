"""Benchmark and external evaluation infrastructure."""

from codecortex.evaluation.baseline import PlatformBaseline, PlatformBaselineStore
from codecortex.evaluation.evidence_benchmark import (
    CaseReport,
    ComparisonMetric,
    EvidenceBenchmark,
    EvidenceBenchmarkReport,
)
from codecortex.evaluation.external import (
    DeterministicGrader,
    EvaluationCase,
    EvaluationExpectation,
    EvaluationOutput,
    EvaluationReport,
    ExternalEvaluationSuite,
    SubprocessEvaluationTarget,
)
from codecortex.evaluation.production import (
    AgentProtocolResult,
    BenchmarkCaseSpec,
    InstrumentedAgentRunner,
    ObservedMetrics,
    ProductionBenchmarkReport,
    ProductionBenchmarkRunner,
    RepositorySpec,
    ScenarioResult,
    SetupMeasurement,
    load_repository_specs,
)
from codecortex.evaluation.regression import (
    BenchmarkHistory,
    BenchmarkSnapshot,
    GateReport,
    MetricPolicy,
    RegressionGate,
)

__all__ = [
    "AgentProtocolResult",
    "BenchmarkCaseSpec",
    "BenchmarkHistory",
    "BenchmarkSnapshot",
    "CaseReport",
    "ComparisonMetric",
    "DeterministicGrader",
    "EvaluationCase",
    "EvaluationExpectation",
    "EvaluationOutput",
    "EvaluationReport",
    "EvidenceBenchmark",
    "EvidenceBenchmarkReport",
    "ExternalEvaluationSuite",
    "GateReport",
    "InstrumentedAgentRunner",
    "MetricPolicy",
    "ObservedMetrics",
    "PlatformBaseline",
    "PlatformBaselineStore",
    "ProductionBenchmarkReport",
    "ProductionBenchmarkRunner",
    "RegressionGate",
    "RepositorySpec",
    "ScenarioResult",
    "SetupMeasurement",
    "SubprocessEvaluationTarget",
    "load_repository_specs",
]
