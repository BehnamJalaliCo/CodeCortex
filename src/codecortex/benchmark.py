"""Reproducible repository intelligence benchmark harness."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Protocol

from codecortex.indexing.indexer import ProjectIndexer

_TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java",
    ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".php", ".rb",
    ".md", ".toml", ".yaml", ".yml", ".json",
}
_EXCLUDED = {".git", ".codecortex", ".venv", "venv", "node_modules", "dist", "build"}


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    id: str
    query: str
    expected_paths: tuple[str, ...] = ()
    expected_symbols: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "BenchmarkCase":
        return cls(
            id=str(value["id"]),
            query=str(value["query"]),
            expected_paths=tuple(str(item) for item in value.get("expected_paths", [])),
            expected_symbols=tuple(str(item) for item in value.get("expected_symbols", [])),
        )


@dataclass(frozen=True, slots=True)
class StrategyResult:
    strategy: str
    case_id: str
    duration_ms: float
    context_tokens: int
    files_read: int
    tool_calls: int
    path_recall: float
    symbol_recall: float
    success: bool


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    results: tuple[StrategyResult, ...]

    def summary(self) -> dict[str, dict[str, float]]:
        grouped: dict[str, list[StrategyResult]] = {}
        for result in self.results:
            grouped.setdefault(result.strategy, []).append(result)
        summary: dict[str, dict[str, float]] = {}
        for name, rows in grouped.items():
            count = max(1, len(rows))
            summary[name] = {
                "cases": float(len(rows)),
                "success_rate": sum(row.success for row in rows) / count,
                "avg_duration_ms": sum(row.duration_ms for row in rows) / count,
                "avg_context_tokens": sum(row.context_tokens for row in rows) / count,
                "avg_files_read": sum(row.files_read for row in rows) / count,
                "avg_tool_calls": sum(row.tool_calls for row in rows) / count,
                "avg_path_recall": sum(row.path_recall for row in rows) / count,
                "avg_symbol_recall": sum(row.symbol_recall for row in rows) / count,
            }
        return summary

    def save(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "summary": self.summary(),
            "results": [asdict(result) for result in self.results],
        }
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


class BenchmarkStrategy(Protocol):
    name: str

    def run(self, case: BenchmarkCase) -> StrategyResult: ...


def _recall(expected: tuple[str, ...], actual: set[str]) -> float:
    if not expected:
        return 1.0
    normalized = {item.lower() for item in actual}
    hits = sum(
        1
        for item in expected
        if item.lower() in normalized
        or any(item.lower() in candidate for candidate in normalized)
    )
    return hits / len(expected)


def _success(case: BenchmarkCase, path_recall: float, symbol_recall: float) -> bool:
    paths_ok = not case.expected_paths or path_recall > 0
    symbols_ok = not case.expected_symbols or symbol_recall > 0
    return paths_ok and symbols_ok


class FullTextBaseline:
    """Simple full-repository lexical baseline used for measured comparisons."""

    name = "full_text_baseline"

    def __init__(self, root: Path, max_files: int = 10_000, result_limit: int = 50) -> None:
        self.root = root.resolve()
        self.max_files = max_files
        self.result_limit = result_limit

    def run(self, case: BenchmarkCase) -> StrategyResult:
        started = perf_counter()
        terms = {term.lower() for term in case.query.split() if len(term) > 2}
        scored: list[tuple[int, str, str]] = []
        files_read = 0
        for path in self.root.rglob("*"):
            if files_read >= self.max_files:
                break
            if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
                continue
            relative = path.relative_to(self.root)
            if any(part in _EXCLUDED for part in relative.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            files_read += 1
            lowered = text.lower()
            path_text = relative.as_posix().lower()
            score = sum(lowered.count(term) + (3 if term in path_text else 0) for term in terms)
            if score:
                scored.append((score, relative.as_posix(), text[:4000]))
        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = scored[: self.result_limit]
        paths = {path for _, path, _ in selected}
        symbols: set[str] = set()
        context = "\n".join(f"[{path}]\n{text}" for _, path, text in selected)
        path_recall = _recall(case.expected_paths, paths)
        symbol_recall = _recall(case.expected_symbols, symbols)
        return StrategyResult(
            strategy=self.name,
            case_id=case.id,
            duration_ms=(perf_counter() - started) * 1000,
            context_tokens=max(0, len(context) // 4),
            files_read=files_read,
            tool_calls=1,
            path_recall=path_recall,
            symbol_recall=symbol_recall,
            success=_success(case, path_recall, symbol_recall),
        )


class CodeCortexGraphStrategy:
    name = "codecortex_graph"

    def __init__(self, root: Path, result_limit: int = 50) -> None:
        self.root = root.resolve()
        self.result_limit = result_limit
        self.graph = ProjectIndexer(self.root).build()

    def run(self, case: BenchmarkCase) -> StrategyResult:
        started = perf_counter()
        matches = self.graph.search(case.query, self.result_limit)
        paths = {node.path for node in matches if node.path}
        symbols = {node.name for node in matches if node.kind not in {"file", "module", "reference"}}
        lines = [
            f"{node.kind} {node.name} {node.path or ''}:{node.line or ''}"
            for node in matches
        ]
        context = "\n".join(lines)
        path_recall = _recall(case.expected_paths, {path for path in paths if path})
        symbol_recall = _recall(case.expected_symbols, symbols)
        return StrategyResult(
            strategy=self.name,
            case_id=case.id,
            duration_ms=(perf_counter() - started) * 1000,
            context_tokens=max(0, len(context) // 4),
            files_read=len({path for path in paths if path}),
            tool_calls=1,
            path_recall=path_recall,
            symbol_recall=symbol_recall,
            success=_success(case, path_recall, symbol_recall),
        )


class BenchmarkSuite:
    def __init__(self, cases: list[BenchmarkCase], strategies: list[BenchmarkStrategy]) -> None:
        self.cases = cases
        self.strategies = strategies

    @classmethod
    def load(cls, path: Path, strategies: list[BenchmarkStrategy]) -> "BenchmarkSuite":
        payload = json.loads(path.read_text(encoding="utf-8"))
        cases = [BenchmarkCase.from_dict(item) for item in payload["cases"]]
        return cls(cases, strategies)

    def run(self) -> BenchmarkReport:
        results = tuple(
            strategy.run(case)
            for case in self.cases
            for strategy in self.strategies
        )
        return BenchmarkReport(results)
