"""Non-synthetic scale measurement for very large repositories."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

_EXCLUDED = {".git", ".codecortex", ".venv", "venv", "node_modules", "dist", "build", "target"}


@dataclass(frozen=True, slots=True)
class ScaleSample:
    target_files: int
    observed_files: int
    reached: bool
    elapsed_ms: float


@dataclass(frozen=True, slots=True)
class ScaleBenchmarkReport:
    root: str
    samples: tuple[ScaleSample, ...]

    @property
    def observed_files(self) -> int:
        return max((item.observed_files for item in self.samples), default=0)


class RepositoryScaleBenchmark:
    """Measure actual repository traversal at 100k/1M targets without synthetic rows."""

    def __init__(self, targets: tuple[int, ...] = (100_000, 1_000_000)) -> None:
        normalized = tuple(sorted({int(item) for item in targets if int(item) > 0}))
        if not normalized:
            raise ValueError("at least one positive scale target is required")
        self.targets = normalized

    def run(self, root: Path) -> ScaleBenchmarkReport:
        resolved = root.resolve()
        started = time.perf_counter()
        observed = 0
        reached: dict[int, ScaleSample] = {}
        maximum = self.targets[-1]
        for path in resolved.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(resolved)
            if any(part in _EXCLUDED for part in relative.parts):
                continue
            observed += 1
            for target in self.targets:
                if target not in reached and observed >= target:
                    reached[target] = ScaleSample(
                        target_files=target,
                        observed_files=observed,
                        reached=True,
                        elapsed_ms=(time.perf_counter() - started) * 1000,
                    )
            if observed >= maximum:
                break
        total_ms = (time.perf_counter() - started) * 1000
        samples = tuple(
            reached.get(
                target,
                ScaleSample(
                    target_files=target,
                    observed_files=observed,
                    reached=False,
                    elapsed_ms=total_ms,
                ),
            )
            for target in self.targets
        )
        return ScaleBenchmarkReport(str(resolved), samples)
