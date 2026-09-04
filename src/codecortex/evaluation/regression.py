"""Persistent benchmark history and deterministic regression gates."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BenchmarkSnapshot:
    id: str
    created_at: str
    commit: str | None
    metrics: dict[str, dict[str, float]]
    metadata: dict[str, str]


@dataclass(frozen=True, slots=True)
class MetricPolicy:
    metric: str
    direction: str
    max_relative_regression: float | None = None
    max_absolute_regression: float | None = None

    def __post_init__(self) -> None:
        if self.direction not in {"higher", "lower"}:
            raise ValueError("direction must be 'higher' or 'lower'")


@dataclass(frozen=True, slots=True)
class RegressionViolation:
    strategy: str
    metric: str
    baseline: float
    current: float
    relative_change: float | None
    absolute_change: float
    reason: str


@dataclass(frozen=True, slots=True)
class GateReport:
    passed: bool
    violations: tuple[RegressionViolation, ...]
    compared_metrics: int


class BenchmarkHistory:
    VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(
        self,
        metrics: dict[str, dict[str, float]],
        commit: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> BenchmarkSnapshot:
        created = datetime.now(UTC).isoformat()
        snapshot = BenchmarkSnapshot(
            id=f"bench-{created.replace(':', '').replace('+', '-')}",
            created_at=created,
            commit=commit,
            metrics=metrics,
            metadata=metadata or {},
        )
        snapshots = self.load()
        snapshots.append(snapshot)
        self._save(snapshots)
        return snapshot

    def load(self) -> list[BenchmarkSnapshot]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if payload.get("version") != self.VERSION:
            return []
        result: list[BenchmarkSnapshot] = []
        for item in payload.get("snapshots", []):
            try:
                result.append(
                    BenchmarkSnapshot(
                        id=str(item["id"]),
                        created_at=str(item["created_at"]),
                        commit=str(item["commit"]) if item.get("commit") else None,
                        metrics={
                            str(strategy): {
                                str(metric): float(value) for metric, value in values.items()
                            }
                            for strategy, values in item["metrics"].items()
                        },
                        metadata={
                            str(key): str(value) for key, value in item.get("metadata", {}).items()
                        },
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return result

    def latest(self) -> BenchmarkSnapshot | None:
        snapshots = self.load()
        return snapshots[-1] if snapshots else None

    def _save(self, snapshots: list[BenchmarkSnapshot]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.VERSION,
            "snapshots": [asdict(snapshot) for snapshot in snapshots],
        }
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)


class RegressionGate:
    DEFAULT_POLICIES = (
        MetricPolicy("success_rate", "higher", max_absolute_regression=0.02),
        MetricPolicy("avg_path_recall", "higher", max_absolute_regression=0.03),
        MetricPolicy("avg_symbol_recall", "higher", max_absolute_regression=0.03),
        MetricPolicy("avg_duration_ms", "lower", max_relative_regression=0.20),
        MetricPolicy("avg_context_tokens", "lower", max_relative_regression=0.10),
        MetricPolicy("avg_files_read", "lower", max_relative_regression=0.15),
        MetricPolicy("avg_tool_calls", "lower", max_relative_regression=0.15),
    )

    def __init__(self, policies: tuple[MetricPolicy, ...] | None = None) -> None:
        self.policies = policies or self.DEFAULT_POLICIES

    def evaluate(
        self,
        current: BenchmarkSnapshot,
        baseline: BenchmarkSnapshot,
    ) -> GateReport:
        violations: list[RegressionViolation] = []
        compared = 0
        for strategy, current_metrics in current.metrics.items():
            baseline_metrics = baseline.metrics.get(strategy)
            if baseline_metrics is None:
                continue
            for policy in self.policies:
                if policy.metric not in current_metrics or policy.metric not in baseline_metrics:
                    continue
                compared += 1
                now = current_metrics[policy.metric]
                before = baseline_metrics[policy.metric]
                absolute = now - before
                relative = None if before == 0 else absolute / abs(before)
                regression = before - now if policy.direction == "higher" else now - before
                if regression <= 0:
                    continue
                reasons: list[str] = []
                if (
                    policy.max_absolute_regression is not None
                    and regression > policy.max_absolute_regression
                ):
                    reasons.append(
                        f"absolute regression {regression:.4f} > {policy.max_absolute_regression:.4f}"
                    )
                relative_regression = None if before == 0 else regression / abs(before)
                if (
                    policy.max_relative_regression is not None
                    and relative_regression is not None
                    and relative_regression > policy.max_relative_regression
                ):
                    reasons.append(
                        f"relative regression {relative_regression:.2%} > {policy.max_relative_regression:.2%}"
                    )
                if reasons:
                    violations.append(
                        RegressionViolation(
                            strategy=strategy,
                            metric=policy.metric,
                            baseline=before,
                            current=now,
                            relative_change=relative,
                            absolute_change=absolute,
                            reason="; ".join(reasons),
                        )
                    )
        return GateReport(
            passed=not violations,
            violations=tuple(violations),
            compared_metrics=compared,
        )
