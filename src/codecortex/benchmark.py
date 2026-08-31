"""Small benchmark harness for repeatable CodeCortex measurements."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from time import perf_counter

from codecortex.gateway import CodeCortexGateway


@dataclass(slots=True)
class BenchmarkSample:
    query: str
    duration_ms: float
    context_tokens: int
    engines_executed: int


@dataclass(slots=True)
class BenchmarkReport:
    samples: list[BenchmarkSample]

    @property
    def average_duration_ms(self) -> float:
        return mean(sample.duration_ms for sample in self.samples) if self.samples else 0.0

    @property
    def average_context_tokens(self) -> float:
        return mean(sample.context_tokens for sample in self.samples) if self.samples else 0.0


class BenchmarkRunner:
    def __init__(self, gateway: CodeCortexGateway) -> None:
        self.gateway = gateway

    async def run(self, queries: list[str]) -> BenchmarkReport:
        samples: list[BenchmarkSample] = []
        for query in queries:
            started = perf_counter()
            result = await self.gateway.query(query)
            duration_ms = (perf_counter() - started) * 1000
            samples.append(
                BenchmarkSample(
                    query=query,
                    duration_ms=duration_ms,
                    context_tokens=result.context_tokens,
                    engines_executed=len(result.results),
                )
            )
        return BenchmarkReport(samples=samples)
