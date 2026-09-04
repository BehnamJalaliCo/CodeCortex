"""Subprocess adapter for the external structural-matching engine.

Security properties
-------------------
* the engine is invoked with an explicit argument vector, never a shell string;
* the executable is resolved to an absolute path before it is run;
* the working directory is the validated project root;
* runtime is bounded by a timeout and captured output is bounded by a byte cap.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from codecortex.config import StructuralConfig
from codecortex.structural.models import StructuralEngineUnavailable, StructuralError

#: Executable names auto-detected on PATH when none is configured.
#:
#: Only the unambiguous name is probed. The engine also ships a short alias that
#: collides with an unrelated system utility on Linux, so that alias is never
#: auto-detected: a project that installed it under a different name must set
#: ``structural.command`` explicitly.
CANDIDATE_EXECUTABLES: tuple[str, ...] = ("ast-grep",)

#: Exit codes that mean "ran correctly". A structural search that matched
#: nothing exits non-zero, which is not a failure.
SUCCESS_EXIT_CODES = frozenset({0, 1})

#: Cap on captured stderr kept for diagnostics.
MAX_ERROR_CHARS = 4_000


@dataclass(frozen=True, slots=True)
class EngineStatus:
    """Capability report for the structural engine."""

    available: bool
    executable: str | None = None
    version: str = ""
    detail: str = ""

    @property
    def label(self) -> str:
        return "available" if self.available else "unavailable"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.label,
            "available": self.available,
            "executable": self.executable,
            "version": self.version,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class EngineRun:
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool


class StructuralEngine:
    """Locate and drive the structural engine binary."""

    def __init__(
        self,
        root: Path,
        config: StructuralConfig | None = None,
        *,
        argv_prefix: tuple[str, ...] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.config = config or StructuralConfig()
        self._argv_prefix = argv_prefix

    # -- discovery ----------------------------------------------------------

    def argv_prefix(self) -> tuple[str, ...]:
        """Return the validated command prefix used to invoke the engine.

        Raises:
            StructuralEngineUnavailable: when the engine is disabled or missing.
        """
        if self._argv_prefix is not None:
            return self._argv_prefix
        if not self.config.enabled:
            raise StructuralEngineUnavailable(
                "structural intelligence is disabled in configuration"
            )
        configured = self.config.command
        if configured:
            candidate = Path(configured)
            if candidate.is_absolute() or len(candidate.parts) > 1:
                resolved = candidate.expanduser().resolve()
                if not resolved.is_file():
                    raise StructuralEngineUnavailable(
                        f"structural engine not found: {configured}"
                    )
                return (str(resolved), *self.config.command_args)
            located = shutil.which(configured)
            if located is None:
                raise StructuralEngineUnavailable(
                    f"structural engine not found on PATH: {configured}"
                )
            return (located, *self.config.command_args)
        for name in CANDIDATE_EXECUTABLES:
            located = shutil.which(name)
            if located is not None:
                return (located, *self.config.command_args)
        raise StructuralEngineUnavailable(
            "structural engine is not installed; install it or set structural.command"
        )

    def status(self) -> EngineStatus:
        """Probe the engine without mutating anything."""
        try:
            prefix = self.argv_prefix()
        except StructuralEngineUnavailable as exc:
            return EngineStatus(available=False, detail=str(exc))
        try:
            run = self._run((*prefix, "--version"))
        except StructuralError as exc:
            return EngineStatus(available=False, executable=prefix[0], detail=str(exc))
        version = (run.stdout or run.stderr).strip().splitlines()
        return EngineStatus(
            available=True,
            executable=prefix[0],
            version=version[0] if version else "",
        )

    def available(self) -> bool:
        return self.status().available

    # -- execution ----------------------------------------------------------

    def _run(self, argv: tuple[str, ...]) -> EngineRun:
        try:
            completed = subprocess.run(  # noqa: S603 - argv only, resolved executable, no shell
                list(argv),
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise StructuralError(
                f"structural engine timed out after {self.config.timeout_seconds:g}s"
            ) from exc
        except OSError as exc:
            raise StructuralEngineUnavailable(f"structural engine failed to start: {exc}") from exc
        stdout = completed.stdout or ""
        truncated = len(stdout.encode("utf-8", errors="ignore")) > self.config.max_output_bytes
        if truncated:
            stdout = stdout.encode("utf-8", errors="ignore")[
                : self.config.max_output_bytes
            ].decode("utf-8", errors="ignore")
        return EngineRun(
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=(completed.stderr or "")[:MAX_ERROR_CHARS],
            truncated=truncated,
        )

    def search(
        self,
        *,
        pattern: str,
        language: str,
        rewrite: str | None = None,
        include: tuple[str, ...] = (),
        exclude: tuple[str, ...] = (),
        paths: tuple[str, ...] = (),
    ) -> Iterator[dict[str, object]]:
        """Stream raw engine match records for a pattern.

        Raises:
            StructuralError: when the engine reports a real failure.
        """
        if not pattern.strip():
            raise StructuralError("structural pattern must not be empty")
        if not language.strip():
            raise StructuralError("structural search requires a language")
        argv = [
            *self.argv_prefix(),
            "run",
            "--pattern",
            pattern,
            "--lang",
            language,
            "--json=stream",
        ]
        if rewrite is not None:
            argv.extend(["--rewrite", rewrite])
        for glob in include:
            argv.extend(["--globs", glob])
        for glob in exclude:
            argv.extend(["--globs", glob if glob.startswith("!") else f"!{glob}"])
        argv.extend(paths or (".",))

        run = self._run(tuple(argv))
        if run.exit_code not in SUCCESS_EXIT_CODES:
            raise StructuralError(
                f"structural engine failed (exit {run.exit_code}): "
                f"{run.stderr.strip() or 'no diagnostic output'}"
            )
        yielded = 0
        for line in run.stdout.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                if run.truncated:
                    break
                raise StructuralError("structural engine emitted malformed output") from None
            if isinstance(record, dict):
                yielded += 1
                yield record
                if yielded >= self.config.max_results:
                    return
