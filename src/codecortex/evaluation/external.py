"""Reproducible external evaluation suites for coding-agent workflows."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class EvaluationExpectation:
    required_strings: tuple[str, ...] = ()
    forbidden_strings: tuple[str, ...] = ()
    required_paths: tuple[str, ...] = ()
    max_tokens: int | None = None
    max_tool_calls: int | None = None


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    id: str
    prompt: str
    expectation: EvaluationExpectation = EvaluationExpectation()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvaluationOutput:
    answer: str
    files_touched: tuple[str, ...] = ()
    tokens: int = 0
    tool_calls: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Grade:
    passed: bool
    score: float
    checks: tuple[str, ...]
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    case_id: str
    target: str
    duration_ms: float
    output: EvaluationOutput
    grade: Grade
    error: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    run_id: str
    suite_name: str
    suite_version: int
    target: str
    created_at: str
    results: tuple[EvaluationResult, ...]

    def summary(self) -> dict[str, float]:
        count = max(1, len(self.results))
        successful = [item for item in self.results if item.error is None]
        return {
            "cases": float(len(self.results)),
            "success_rate": sum(item.grade.passed for item in self.results) / count,
            "avg_score": sum(item.grade.score for item in self.results) / count,
            "execution_success_rate": len(successful) / count,
            "avg_duration_ms": sum(item.duration_ms for item in self.results) / count,
            "avg_tokens": sum(item.output.tokens for item in self.results) / count,
            "avg_tool_calls": sum(item.output.tool_calls for item in self.results) / count,
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {**asdict(self), "summary": self.summary()}
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)


class EvaluationTarget(Protocol):
    name: str

    async def run(self, case: EvaluationCase) -> EvaluationOutput: ...


class DeterministicGrader:
    def grade(self, case: EvaluationCase, output: EvaluationOutput) -> Grade:
        checks: list[str] = []
        failures: list[str] = []
        expectation = case.expectation
        lowered = output.answer.lower()
        for value in expectation.required_strings:
            label = f"required-string:{value}"
            checks.append(label)
            if value.lower() not in lowered:
                failures.append(label)
        for value in expectation.forbidden_strings:
            label = f"forbidden-string:{value}"
            checks.append(label)
            if value.lower() in lowered:
                failures.append(label)
        paths = {path.replace("\\", "/") for path in output.files_touched}
        for path in expectation.required_paths:
            label = f"required-path:{path}"
            checks.append(label)
            normalized = path.replace("\\", "/")
            if normalized not in paths:
                failures.append(label)
        if expectation.max_tokens is not None:
            label = f"max-tokens:{expectation.max_tokens}"
            checks.append(label)
            if output.tokens > expectation.max_tokens:
                failures.append(label)
        if expectation.max_tool_calls is not None:
            label = f"max-tool-calls:{expectation.max_tool_calls}"
            checks.append(label)
            if output.tool_calls > expectation.max_tool_calls:
                failures.append(label)
        total = max(1, len(checks))
        score = (len(checks) - len(failures)) / total if checks else 1.0
        return Grade(not failures, score, tuple(checks), tuple(failures))


class SubprocessEvaluationTarget:
    """External target adapter using explicit argv and JSON over stdin/stdout.

    No shell is used. The child must return a JSON object compatible with
    EvaluationOutput. This keeps the harness agent-agnostic and scriptable.
    """

    def __init__(
        self,
        name: str,
        argv: tuple[str, ...],
        *,
        cwd: Path | None = None,
        timeout_seconds: float = 300.0,
        env: dict[str, str] | None = None,
    ) -> None:
        if not argv:
            raise ValueError("argv cannot be empty")
        self.name = name
        self.argv = argv
        self.cwd = cwd
        self.timeout_seconds = timeout_seconds
        self.env = env or {}

    async def run(self, case: EvaluationCase) -> EvaluationOutput:
        child_env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            **self.env,
        }
        process = await asyncio.create_subprocess_exec(
            *self.argv,
            cwd=str(self.cwd) if self.cwd else None,
            env=child_env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        request = json.dumps(asdict(case), ensure_ascii=False).encode("utf-8")
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(request),
                timeout=self.timeout_seconds,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError(
                f"evaluation target timed out after {self.timeout_seconds}s"
            ) from None
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace")[-2_000:]
            raise RuntimeError(f"evaluation target exited {process.returncode}: {message}")
        try:
            payload = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("evaluation target returned invalid JSON") from exc
        return EvaluationOutput(
            answer=str(payload.get("answer", "")),
            files_touched=tuple(str(item) for item in payload.get("files_touched", [])),
            tokens=int(payload.get("tokens", 0)),
            tool_calls=int(payload.get("tool_calls", 0)),
            metadata=dict(payload.get("metadata", {})),
        )


class ExternalEvaluationSuite:
    VERSION = 1

    def __init__(
        self,
        name: str,
        cases: list[EvaluationCase],
        grader: DeterministicGrader | None = None,
    ) -> None:
        self.name = name
        self.cases = cases
        self.grader = grader or DeterministicGrader()

    @classmethod
    def load(cls, path: Path) -> ExternalEvaluationSuite:
        payload = json.loads(path.read_text(encoding="utf-8"))
        version = int(payload.get("version", 0))
        if version != cls.VERSION:
            raise ValueError(f"unsupported evaluation suite version: {version}")
        cases = []
        for item in payload.get("cases", []):
            expectation = item.get("expectation", {})
            cases.append(
                EvaluationCase(
                    id=str(item["id"]),
                    prompt=str(item["prompt"]),
                    expectation=EvaluationExpectation(
                        required_strings=tuple(
                            str(value) for value in expectation.get("required_strings", [])
                        ),
                        forbidden_strings=tuple(
                            str(value) for value in expectation.get("forbidden_strings", [])
                        ),
                        required_paths=tuple(
                            str(value) for value in expectation.get("required_paths", [])
                        ),
                        max_tokens=int(expectation["max_tokens"])
                        if expectation.get("max_tokens") is not None
                        else None,
                        max_tool_calls=int(expectation["max_tool_calls"])
                        if expectation.get("max_tool_calls") is not None
                        else None,
                    ),
                    metadata={
                        str(key): str(value) for key, value in item.get("metadata", {}).items()
                    },
                )
            )
        return cls(str(payload.get("name", path.stem)), cases)

    async def run(self, target: EvaluationTarget) -> EvaluationReport:
        results: list[EvaluationResult] = []
        for case in self.cases:
            started = time.perf_counter()
            try:
                output = await target.run(case)
                grade = self.grader.grade(case, output)
                error = None
            except Exception as exc:
                output = EvaluationOutput(answer="")
                grade = Grade(False, 0.0, (), ("execution-error",))
                error = f"{type(exc).__name__}: {exc}"[:1_000]
            results.append(
                EvaluationResult(
                    case_id=case.id,
                    target=target.name,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    output=output,
                    grade=grade,
                    error=error,
                )
            )
        return EvaluationReport(
            run_id=uuid.uuid4().hex,
            suite_name=self.name,
            suite_version=self.VERSION,
            target=target.name,
            created_at=datetime.now(UTC).isoformat(),
            results=tuple(results),
        )
