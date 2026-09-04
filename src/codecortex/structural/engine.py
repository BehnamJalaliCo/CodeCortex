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
import re
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from codecortex.config import StructuralConfig
from codecortex.structural.models import StructuralEngineUnavailable, StructuralError

#: No vendor-specific executable is auto-detected. Projects that enable the
#: optional subprocess adapter must configure `structural.command` explicitly.
CANDIDATE_EXECUTABLES: tuple[str, ...] = ()

#: Exit codes that mean "ran correctly". A structural search that matched
#: nothing exits non-zero, which is not a failure.
SUCCESS_EXIT_CODES = frozenset({0, 1})

#: Cap on captured stderr kept for diagnostics.
MAX_ERROR_CHARS = 4_000

#: The engine's own wording when a pattern failed to parse cleanly. It reports
#: this on stderr and still exits successfully with zero matches, so the marker
#: is the only signal that a pattern was malformed rather than unmatched.
PATTERN_ERROR_MARKER = "Pattern contains an ERROR node"

#: Reference record-shape version used by the generic subprocess adapter.
#: A configured engine may use a different version; status reports that as
#: unverified rather than silently assuming compatibility.
TESTED_ENGINE_VERSION = "0.45.3"

_VERSION_TOKEN = re.compile(r"(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?)")


def parse_engine_version(text: str) -> str:
    """Extract a version from the engine's ``--version`` output."""
    found = _VERSION_TOKEN.search(text)
    return found.group(1) if found else ""


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

    @property
    def engine_version(self) -> str:
        """The engine's own version number, extracted from its banner."""
        return parse_engine_version(self.version)

    @property
    def verified_version(self) -> bool:
        """Whether the installed engine is the release CodeCortex tests against."""
        return self.engine_version == TESTED_ENGINE_VERSION

    @property
    def version_warning(self) -> str:
        """A warning when the installed engine is not the tested release.

        Not an error: another build will usually work. But CodeCortex parses
        this engine's structured output, so an untested version is exactly
        where a silent shape change would show up, and saying nothing would
        present an unverified combination as a verified one.
        """
        if not self.available or self.verified_version:
            return ""
        found = self.engine_version or "an unrecognised version"
        return (
            f"structural engine {found} is installed; CodeCortex verifies its "
            f"output against {TESTED_ENGINE_VERSION}"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.label,
            "available": self.available,
            "executable": self.executable,
            "version": self.version,
            "engine_version": self.engine_version,
            "tested_version": TESTED_ENGINE_VERSION,
            "verified_version": self.verified_version,
            "version_warning": self.version_warning,
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
        # A pattern the engine could not parse cleanly exits 0 with a warning
        # and matches nothing. Dropping that warning makes a broken pattern
        # indistinguishable from a pattern that legitimately found nothing -
        # and its matches, if any, are not safe to drive a rewrite from.
        if PATTERN_ERROR_MARKER in run.stderr:
            raise StructuralError(
                "structural pattern is not valid for this language: "
                f"{run.stderr.strip().splitlines()[0]}"
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
