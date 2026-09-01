"""Deterministic retrieval-quality benchmarks with observable ranking metrics."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RetrievalQualityCase:
    id: str
    query: str
    expected_ids: tuple[str, ...]
    limit: int = 20


@dataclass(frozen=True, slots=True)
class RetrievalQualityResult:
    case_id: str
    recall: float
    precision: float
    reciprocal_rank: float
    hits: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalQualityReport:
    results: tuple[RetrievalQualityResult, ...]

    def summary(self) -> dict[str, float]:
        count = len(self.results)
        if not count:
            return {"cases": 0.0, "avg_recall": 0.0, "avg_precision": 0.0, "mrr": 0.0}
        return {
            "cases": float(count),
            "avg_recall": sum(item.recall for item in self.results) / count,
            "avg_precision": sum(item.precision for item in self.results) / count,
            "mrr": sum(item.reciprocal_rank for item in self.results) / count,
        }


class RetrievalQualityBenchmark:
    def __init__(self, cases: Iterable[RetrievalQualityCase]) -> None:
        self.cases = tuple(cases)

    def run(
        self,
        search: Callable[[str, int], Iterable[Any]],
    ) -> RetrievalQualityReport:
        results: list[RetrievalQualityResult] = []
        for case in self.cases:
            raw_hits = list(search(case.query, max(1, case.limit)))
            hit_ids = tuple(self._hit_id(item) for item in raw_hits[: max(1, case.limit)])
            expected = set(case.expected_ids)
            recovered = [item for item in hit_ids if item in expected]
            recall = len(set(recovered)) / len(expected) if expected else 1.0
            precision = len(recovered) / len(hit_ids) if hit_ids else 0.0
            rank = next((index for index, item in enumerate(hit_ids, 1) if item in expected), None)
            results.append(
                RetrievalQualityResult(
                    case_id=case.id,
                    recall=recall,
                    precision=precision,
                    reciprocal_rank=0.0 if rank is None else 1.0 / rank,
                    hits=hit_ids,
                )
            )
        return RetrievalQualityReport(tuple(results))

    @staticmethod
    def _hit_id(item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, dict) and "id" in item:
            return str(item["id"])
        document = getattr(item, "document", None)
        if document is not None and getattr(document, "id", None) is not None:
            return str(document.id)
        if getattr(item, "id", None) is not None:
            return str(item.id)
        raise TypeError(f"cannot extract retrieval hit id from {type(item).__name__}")
