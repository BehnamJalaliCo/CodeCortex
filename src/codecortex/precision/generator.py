"""Optional, explicitly configured generation of a precision index.

CodeCortex Core never depends on a language-specific indexer. A project that
already has one installed can configure the exact argument vector to run; the
command is executed with no shell, a bounded timeout, and bounded output.
Nothing is ever downloaded on the user's behalf.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from codecortex.config import PrecisionIndexConfig

#: Cap on captured generator output so a runaway indexer cannot exhaust memory.
MAX_CAPTURED_OUTPUT = 64 * 1024


class PrecisionGeneratorError(RuntimeError):
    """Raised when a configured index generator cannot be run."""


@dataclass(frozen=True, slots=True)
class GenerationResult:
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True, slots=True)
class PrecisionIndexGenerator:
    """Run a project-configured indexer command inside the project root."""

    root: Path
    config: PrecisionIndexConfig

    @property
    def configured(self) -> bool:
        return bool(self.config.generator_command)

    def resolve_executable(self) -> str:
        """Resolve the configured executable to an absolute path.

        Raises:
            PrecisionGeneratorError: when nothing is configured or the
                executable cannot be found on PATH.
        """
        if not self.config.generator_command:
            raise PrecisionGeneratorError("no precision index generator is configured")
        name = self.config.generator_command[0]
        candidate = Path(name)
        if candidate.is_absolute() or len(candidate.parts) > 1:
            resolved = candidate.expanduser().resolve()
            if not resolved.is_file():
                raise PrecisionGeneratorError(f"generator executable not found: {name}")
            return str(resolved)
        located = shutil.which(name)
        if located is None:
            raise PrecisionGeneratorError(f"generator executable not found on PATH: {name}")
        return located

    def generate(self) -> GenerationResult:
        """Run the configured generator, returning its bounded result."""
        executable = self.resolve_executable()
        argv = (executable, *self.config.generator_command[1:])
        try:
            completed = subprocess.run(  # noqa: S603 - argv only, never a shell string
                argv,
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=self.config.generator_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise PrecisionGeneratorError(
                f"precision index generation timed out after "
                f"{self.config.generator_timeout_seconds:g}s"
            ) from exc
        except OSError as exc:
            raise PrecisionGeneratorError(f"precision index generation failed: {exc}") from exc
        return GenerationResult(
            command=argv,
            exit_code=completed.returncode,
            stdout=(completed.stdout or "")[:MAX_CAPTURED_OUTPUT],
            stderr=(completed.stderr or "")[:MAX_CAPTURED_OUTPUT],
        )
