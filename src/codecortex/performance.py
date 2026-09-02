"""Performance budgets for platform operations."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True, slots=True)
class PerformanceBudgets:
    api_p95_ms: float = 500.0
    search_ms: float = 1000.0
    graph_ms: float = 1500.0
    context_ms: float = 3000.0
    incremental_index_ms: float = 5000.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
