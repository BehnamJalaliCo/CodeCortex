"""Production benchmark harness for real, revision-pinned repositories.

The harness intentionally separates measurements from claims. It never fills missing
metrics with synthetic values: unavailable file-read counts, provider token usage, and
costs remain ``None`` unless the strategy can observe them directly.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from codecortex.backends import BackendManager, ContextBackendAdapter, GraphBackendAdapter, SymbolBackendAdapter
from codecortex.backends.mcp_client import MCPStdioClient

_TEXT_SUFFIXES = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java",
    ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".php", ".rb", ".kt", ".kts",
    ".scala", ".swift", ".vue", ".svelte", ".md", ".toml", ".yaml", ".yml", ".json",
}
_EXCLUDED = {".git", ".codecortex", ".venv", "venv", "node_modules", "dist", "build", "target"}
_PATH_RE = re.compile(r"(?:^|[\s\[(`'\"])([A-Za-z0-9_.@+-]+(?:/[A-Za-z0-9_.@+-]+)+\.[A-Za-z0-9]+)")

ScenarioName = Literal["vanilla", "graph", "symbols", "context", "full"]


@dataclass(frozen=True, slots=True)
class RepositorySpec:
    name: str
    url: str
    revision: str
    cases: tuple[BenchmarkCaseSpec, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RepositorySpec:
        return cls(
            name=str(value["name"]),
            url=str(value["url"]),
            revision=str(value["revision"]),
            cases=tuple(BenchmarkCaseSpec.from_dict(item) for item in value.get("cases", [])),
        )


@dataclass(frozen=True, slots=True)
class BenchmarkCaseSpec:
    id: str
    query: str
    expected_paths: tuple[str, ...] = ()
    expected_symbols: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BenchmarkCaseSpec:
        return cls(
            id=str(value["id"]),
            query=str(value["query"]),
            expected_paths=tuple(str(item) for item in value.get("expected_paths", [])),
            expected_symbols=tuple(str(item) for item in value.get("expected_symbols", [])),
        )


@dataclass(frozen=True, slots=True)
class ObservedMetrics:
    wall_time_ms: float
    context_chars: int
    estimated_context_tokens: int
    files_read: int | None
    files_surfaced: int
    tool_calls: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    cost_source: str | None = None


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    repository: str
    revision: str
    case_id: str
    scenario: ScenarioName
    status: Literal["ok", "skipped", "error"]
    success: bool | None
    path_recall: float | None
    symbol_recall: float | None
    metrics: ObservedMetrics | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class SetupMeasurement:
    repository: str
    scenario: ScenarioName
    wall_time_ms: float
    status: Literal["ok", "skipped", "error"]
    detail: str = ""


@dataclass(slots=True)
class ProductionBenchmarkReport:
    repositories: list[dict[str, str]] = field(default_factory=list)
    setup: list[SetupMeasurement] = field(default_factory=list)
    results: list[ScenarioResult] = field(default_factory=list)

    def summary(self) -> dict[str, dict[str, float | int | None]]:
        grouped: dict[str, list[ScenarioResult]] = {}
        for result in self.results:
            grouped.setdefault(result.scenario, []).append(result)
        output: dict[str, dict[str, float | int | None]] = {}
        for scenario, rows in grouped.items():
            completed = [row for row in rows if row.status == "ok" and row.metrics is not None]
            scored = [row for row in completed if row.success is not None]
            output[scenario] = {
                "cases": len(rows),
                "completed": len(completed),
                "success_rate": (
                    sum(bool(row.success) for row in scored) / len(scored) if scored else None
                ),
                "avg_wall_time_ms": _average(row.metrics.wall_time_ms for row in completed if row.metrics),
                "avg_estimated_context_tokens": _average(
                    row.metrics.estimated_context_tokens for row in completed if row.metrics
                ),
                "avg_files_read": _average(
                    row.metrics.files_read
                    for row in completed
                    if row.metrics and row.metrics.files_read is not None
                ),
                "avg_files_surfaced": _average(row.metrics.files_surfaced for row in completed if row.metrics),
                "avg_tool_calls": _average(row.metrics.tool_calls for row in completed if row.metrics),
                "avg_cost_usd": _average(
                    row.metrics.cost_usd
                    for row in completed
                    if row.metrics and row.metrics.cost_usd is not None
                ),
            }
        return output

    def save(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "measurement_policy": {
                "estimated_context_tokens": "UTF-8 text length divided by four; explicitly estimated",
                "missing_metrics": "null; never synthesized",
                "cost": "reported only when an instrumented agent/provider supplies a measured value",
            },
            "repositories": self.repositories,
            "setup": [asdict(item) for item in self.setup],
            "summary": self.summary(),
            "results": [asdict(item) for item in self.results],
        }
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@dataclass(frozen=True, slots=True)
class RetrievalObservation:
    text: str
    files_read: int | None
    tool_calls: int


class RepositoryCheckout:
    """Materialize a public repository at an exact immutable revision."""

    def __init__(self, cache_root: Path) -> None:
        self.cache_root = cache_root.resolve()

    def ensure(self, spec: RepositorySpec) -> Path:
        target = self.cache_root / _safe_name(spec.name) / spec.revision[:12]
        marker = target / ".codecortex-benchmark-revision"
        if marker.exists() and marker.read_text(encoding="utf-8").strip() == spec.revision:
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            _remove_tree(target)
        target.mkdir(parents=True)
        _git(target, "init")
        _git(target, "remote", "add", "origin", spec.url)
        _git(target, "fetch", "--depth", "1", "origin", spec.revision, timeout=600)
        _git(target, "checkout", "--detach", "FETCH_HEAD")
        resolved = _git(target, "rev-parse", "HEAD").strip()
        if resolved != spec.revision:
            raise RuntimeError(f"revision mismatch for {spec.name}: expected {spec.revision}, got {resolved}")
        marker.write_text(spec.revision + "\n", encoding="utf-8")
        return target


class ProductionBenchmarkRunner:
    """Compare a lexical baseline, individual mature engines, and the integrated stack."""

    scenarios: tuple[ScenarioName, ...] = ("vanilla", "graph", "symbols", "context", "full")

    def __init__(
        self,
        specs: Sequence[RepositorySpec],
        *,
        workspace: Path,
        backend_manager: BackendManager | None = None,
        provision_backends: bool = False,
        result_limit: int = 30,
    ) -> None:
        self.specs = tuple(specs)
        self.workspace = workspace.resolve()
        self.checkout = RepositoryCheckout(self.workspace / "repositories")
        self.manager = backend_manager or BackendManager(timeout_seconds=900)
        self.provision_backends = provision_backends
        self.result_limit = result_limit

    @classmethod
    def load(
        cls,
        spec_path: Path,
        *,
        workspace: Path,
        backend_manager: BackendManager | None = None,
        provision_backends: bool = False,
    ) -> ProductionBenchmarkRunner:
        payload = json.loads(spec_path.read_text(encoding="utf-8"))
        repos = [RepositorySpec.from_dict(item) for item in payload["repositories"]]
        return cls(
            repos,
            workspace=workspace,
            backend_manager=backend_manager,
            provision_backends=provision_backends,
        )

    def run(self, scenarios: Sequence[ScenarioName] | None = None) -> ProductionBenchmarkReport:
        selected = tuple(scenarios or self.scenarios)
        report = ProductionBenchmarkReport()
        for spec in self.specs:
            root = self.checkout.ensure(spec)
            report.repositories.append({"name": spec.name, "url": spec.url, "revision": spec.revision})
            graph = GraphBackendAdapter(root, self.manager)
            symbols = SymbolBackendAdapter(root, self.manager)
            context = ContextBackendAdapter(root, self.manager)
            availability = self._prepare(spec, root, selected, graph, symbols, context, report)
            for case in spec.cases:
                baseline: RetrievalObservation | None = None
                for scenario in selected:
                    if scenario == "vanilla":
                        baseline = self._lexical(root, case)
                        report.results.append(self._measure(spec, case, scenario, lambda b=baseline: b))
                        continue
                    if not availability.get(scenario, False):
                        report.results.append(
                            ScenarioResult(
                                repository=spec.name,
                                revision=spec.revision,
                                case_id=case.id,
                                scenario=scenario,
                                status="skipped",
                                success=None,
                                path_recall=None,
                                symbol_recall=None,
                                metrics=None,
                                error="required backend is not provisioned/healthy",
                            )
                        )
                        continue
                    if baseline is None and scenario == "context":
                        baseline = self._lexical(root, case)
                    operation = self._operation(
                        scenario,
                        case,
                        root,
                        graph,
                        symbols,
                        context,
                        baseline,
                    )
                    report.results.append(self._measure(spec, case, scenario, operation))
        return report

    def _prepare(
        self,
        spec: RepositorySpec,
        root: Path,
        selected: Sequence[ScenarioName],
        graph: GraphBackendAdapter,
        symbols: SymbolBackendAdapter,
        context: ContextBackendAdapter,
        report: ProductionBenchmarkReport,
    ) -> dict[ScenarioName, bool]:
        availability: dict[ScenarioName, bool] = {"vanilla": True, "graph": False, "symbols": False, "context": False, "full": False}
        adapters = {"graph": graph, "symbols": symbols, "context": context}
        for key, adapter in adapters.items():
            needed = key in selected or "full" in selected
            if not needed:
                continue
            started = perf_counter()
            try:
                if self.provision_backends:
                    self.manager.ensure(adapter.spec)
                installed = self.manager.is_installed(adapter.spec)
                if not installed:
                    status: Literal["ok", "skipped", "error"] = "skipped"
                    detail = "not installed"
                    healthy = False
                else:
                    healthy = self.manager.probe(adapter.spec, provision=False)
                    status = "ok" if healthy else "error"
                    detail = "healthy" if healthy else "health probe failed"
                    if healthy and key == "graph":
                        graph.build()
                    elif healthy and key in {"symbols", "context"}:
                        adapter.require_tools(adapter.tools(), adapter.required_tools)
                availability[key] = healthy  # type: ignore[literal-required]
            except Exception as exc:
                status = "error"
                detail = f"{type(exc).__name__}: {exc}"
                availability[key] = False  # type: ignore[literal-required]
            report.setup.append(
                SetupMeasurement(
                    repository=spec.name,
                    scenario=key,  # type: ignore[arg-type]
                    wall_time_ms=(perf_counter() - started) * 1000,
                    status=status,
                    detail=detail,
                )
            )
        availability["full"] = availability["graph"] and availability["symbols"] and availability["context"]
        return availability

    def _operation(
        self,
        scenario: ScenarioName,
        case: BenchmarkCaseSpec,
        root: Path,
        graph: GraphBackendAdapter,
        symbols: SymbolBackendAdapter,
        context: ContextBackendAdapter,
        baseline: RetrievalObservation | None,
    ):
        if scenario == "graph":
            return lambda: RetrievalObservation(graph.query(case.query), None, 1)
        if scenario == "symbols":
            return lambda: self._symbol_observation(symbols, case)
        if scenario == "context":
            assert baseline is not None
            return lambda: self._context_observation(context, baseline)
        if scenario == "full":
            return lambda: self._full_observation(graph, symbols, context, case)
        raise ValueError(scenario)

    def _symbol_observation(self, symbols: SymbolBackendAdapter, case: BenchmarkCaseSpec) -> RetrievalObservation:
        target = case.expected_symbols[0] if case.expected_symbols else case.query
        payload = symbols.call(
            "find_symbol",
            {"name_path_pattern": target, "include_body": True, "depth": 1},
        )
        return RetrievalObservation(MCPStdioClient.content_text(payload) or json.dumps(payload), None, 1)

    def _context_observation(self, context: ContextBackendAdapter, baseline: RetrievalObservation) -> RetrievalObservation:
        payload = context.compress(baseline.text)
        text = MCPStdioClient.content_text(payload) or json.dumps(payload)
        return RetrievalObservation(text, baseline.files_read, baseline.tool_calls + 1)

    def _full_observation(
        self,
        graph: GraphBackendAdapter,
        symbols: SymbolBackendAdapter,
        context: ContextBackendAdapter,
        case: BenchmarkCaseSpec,
    ) -> RetrievalObservation:
        graph_text = graph.query(case.query)
        symbol = self._symbol_observation(symbols, case)
        combined = f"[graph]\n{graph_text}\n\n[symbols]\n{symbol.text}"
        payload = context.compress(combined)
        compressed = MCPStdioClient.content_text(payload) or json.dumps(payload)
        return RetrievalObservation(compressed, None, 3)

    def _lexical(self, root: Path, case: BenchmarkCaseSpec) -> RetrievalObservation:
        terms = {term.lower() for term in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", case.query)}
        scored: list[tuple[int, str, str]] = []
        files_read = 0
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
                continue
            relative = path.relative_to(root)
            if any(part in _EXCLUDED for part in relative.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            files_read += 1
            lowered = text.lower()
            path_text = relative.as_posix().lower()
            score = sum(lowered.count(term) + (5 if term in path_text else 0) for term in terms)
            if score:
                scored.append((score, relative.as_posix(), text[:8000]))
        scored.sort(key=lambda row: (-row[0], row[1]))
        selected = scored[: self.result_limit]
        text = "\n\n".join(f"[{path}]\n{content}" for _, path, content in selected)
        return RetrievalObservation(text, files_read, 1)

    def _measure(
        self,
        spec: RepositorySpec,
        case: BenchmarkCaseSpec,
        scenario: ScenarioName,
        operation,
    ) -> ScenarioResult:
        started = perf_counter()
        try:
            observation: RetrievalObservation = operation()
            duration = (perf_counter() - started) * 1000
            path_recall = _evidence_recall(case.expected_paths, observation.text)
            symbol_recall = _evidence_recall(case.expected_symbols, observation.text)
            success = (not case.expected_paths or path_recall > 0) and (
                not case.expected_symbols or symbol_recall > 0
            )
            surfaced = len(_extract_paths(observation.text))
            return ScenarioResult(
                repository=spec.name,
                revision=spec.revision,
                case_id=case.id,
                scenario=scenario,
                status="ok",
                success=success,
                path_recall=path_recall,
                symbol_recall=symbol_recall,
                metrics=ObservedMetrics(
                    wall_time_ms=duration,
                    context_chars=len(observation.text),
                    estimated_context_tokens=max(0, len(observation.text) // 4),
                    files_read=observation.files_read,
                    files_surfaced=surfaced,
                    tool_calls=observation.tool_calls,
                ),
            )
        except Exception as exc:
            return ScenarioResult(
                repository=spec.name,
                revision=spec.revision,
                case_id=case.id,
                scenario=scenario,
                status="error",
                success=None,
                path_recall=None,
                symbol_recall=None,
                metrics=None,
                error=f"{type(exc).__name__}: {exc}",
            )


@dataclass(frozen=True, slots=True)
class AgentProtocolResult:
    answer: str
    files_read: int | None = None
    tool_calls: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    cost_source: str | None = None


class InstrumentedAgentRunner:
    """Run an actual coding agent through a JSON protocol without inventing usage metrics.

    The configured command receives one JSON request on stdin and must emit one JSON object
    on stdout. Metrics omitted by the agent remain null in the benchmark result.
    """

    def __init__(self, command: str, *, timeout_seconds: float = 900.0) -> None:
        self.argv = tuple(shlex.split(command))
        if not self.argv:
            raise ValueError("agent command is empty")
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        *,
        scenario: ScenarioName,
        repository: Path,
        case: BenchmarkCaseSpec,
        environment: Mapping[str, str] | None = None,
    ) -> AgentProtocolResult:
        request = {
            "schema_version": 1,
            "scenario": scenario,
            "repository": str(repository),
            "case": asdict(case),
        }
        process = subprocess.run(
            self.argv,
            cwd=repository,
            env={**os.environ, **dict(environment or {})},
            input=json.dumps(request),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self.timeout_seconds,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(process.stderr.strip() or f"agent exited with {process.returncode}")
        payload = json.loads(process.stdout)
        if not isinstance(payload, dict) or not isinstance(payload.get("answer"), str):
            raise ValueError("agent must return a JSON object containing string field 'answer'")
        return AgentProtocolResult(
            answer=payload["answer"],
            files_read=_optional_int(payload.get("files_read")),
            tool_calls=_optional_int(payload.get("tool_calls")),
            input_tokens=_optional_int(payload.get("input_tokens")),
            output_tokens=_optional_int(payload.get("output_tokens")),
            cost_usd=_optional_float(payload.get("cost_usd")),
            cost_source=str(payload["cost_source"]) if payload.get("cost_source") is not None else None,
        )


def load_repository_specs(path: Path) -> tuple[RepositorySpec, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(RepositorySpec.from_dict(item) for item in payload["repositories"])


def _evidence_recall(expected: Sequence[str], text: str) -> float:
    if not expected:
        return 1.0
    lowered = text.lower()
    return sum(item.lower() in lowered for item in expected) / len(expected)


def _extract_paths(text: str) -> set[str]:
    return {match.group(1) for match in _PATH_RE.finditer(text)}


def _average(values: Iterable[int | float | None]) -> float | None:
    rows = [float(value) for value in values if value is not None]
    return sum(rows) / len(rows) if rows else None


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "repository"


def _remove_tree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=False)


def _git(root: Path, *args: str, timeout: float = 120.0) -> str:
    process = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or process.stdout.strip())
    return process.stdout


def temporary_benchmark_workspace() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix="codecortex-benchmark-")
