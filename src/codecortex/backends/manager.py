"""Isolated lifecycle management for optional backend engines."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import venv
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from codecortex.backends.spec import BackendSpec


@dataclass(frozen=True, slots=True)
class ProcessResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: float


class BackendProcessError(RuntimeError):
    def __init__(self, result: ProcessResult) -> None:
        self.result = result
        message = result.stderr.strip() or result.stdout.strip() or "backend process failed"
        super().__init__(f"{result.argv[0]} exited with {result.returncode}: {message[:500]}")


def _default_cache_root() -> Path:
    configured = os.getenv("CODECORTEX_BACKEND_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "codecortex" / "backends"
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "CodeCortex" / "backends"
    return Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")) / "codecortex" / "backends"


class BackendManager:
    """Provision and execute pinned engines in conflict-free environments."""

    def __init__(self, cache_root: Path | None = None, timeout_seconds: float = 300.0) -> None:
        self.cache_root = (cache_root or _default_cache_root()).expanduser().resolve()
        self.timeout_seconds = timeout_seconds

    def environment_dir(self, spec: BackendSpec) -> Path:
        return self.cache_root / spec.key / spec.revision[:12]

    def metadata_path(self, spec: BackendSpec) -> Path:
        return self.environment_dir(spec) / ".codecortex-backend.json"

    def python_path(self, spec: BackendSpec) -> Path:
        env = self.environment_dir(spec)
        return env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def command_path(self, spec: BackendSpec) -> Path:
        env = self.environment_dir(spec)
        suffix = ".exe" if os.name == "nt" else ""
        return env / ("Scripts" if os.name == "nt" else "bin") / f"{spec.command}{suffix}"

    def is_installed(self, spec: BackendSpec) -> bool:
        metadata = self._load_metadata(spec)
        return bool(
            metadata
            and metadata.get("revision") == spec.revision
            and self.command_path(spec).exists()
        )

    def ensure(self, spec: BackendSpec) -> Path:
        if self.is_installed(spec):
            return self.command_path(spec)
        env_dir = self.environment_dir(spec)
        env_dir.parent.mkdir(parents=True, exist_ok=True)
        lock = env_dir.with_suffix(".lock")
        self._acquire_lock(lock)
        try:
            if self.is_installed(spec):
                return self.command_path(spec)
            if env_dir.exists():
                shutil.rmtree(env_dir)
            self._create_environment(env_dir, spec)
            self._install(spec)
            payload = asdict(spec)
            payload["installed_at"] = time.time()
            self.metadata_path(spec).write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            command = self.command_path(spec)
            if not command.exists():
                raise RuntimeError(f"backend installed without expected command: {command}")
            return command
        except Exception:
            if env_dir.exists() and not self.is_installed(spec):
                shutil.rmtree(env_dir, ignore_errors=True)
            raise
        finally:
            self._release_lock(lock)

    def run(
        self,
        spec: BackendSpec,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
        check: bool = True,
        provision: bool = True,
    ) -> ProcessResult:
        command = self.ensure(spec) if provision else self.command_path(spec)
        if not command.exists():
            raise FileNotFoundError(command)
        argv = (str(command), *(str(item) for item in args))
        started = time.perf_counter()
        process = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            env={**os.environ, **dict(env or {})},
            text=True,
            capture_output=True,
            timeout=timeout_seconds or self.timeout_seconds,
            check=False,
        )
        result = ProcessResult(
            argv=argv,
            returncode=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
        if check and result.returncode != 0:
            raise BackendProcessError(result)
        return result

    def probe(self, spec: BackendSpec, provision: bool = False) -> bool:
        try:
            if not provision and not self.is_installed(spec):
                return False
            result = self.run(spec, ("--help",), timeout_seconds=30, provision=provision, check=False)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            return False
        return result.returncode == 0

    def remove(self, spec: BackendSpec) -> None:
        shutil.rmtree(self.environment_dir(spec), ignore_errors=True)

    def _create_environment(self, env_dir: Path, spec: BackendSpec) -> None:
        uv = shutil.which("uv")
        if uv:
            result = subprocess.run(
                [uv, "venv", "--python", spec.python, str(env_dir)],
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            if result.returncode == 0:
                return
        venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)

    def _install(self, spec: BackendSpec) -> None:
        python = self.python_path(spec)
        uv = shutil.which("uv")
        if uv:
            argv = [uv, "pip", "install", "--python", str(python), spec.source_requirement]
        else:
            argv = [str(python), "-m", "pip", "install", spec.source_requirement]
        process = subprocess.run(
            argv,
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(process.stderr.strip() or process.stdout.strip())

    def _load_metadata(self, spec: BackendSpec) -> dict[str, object] | None:
        try:
            value = json.loads(self.metadata_path(spec).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _acquire_lock(self, lock: Path) -> None:
        deadline = time.monotonic() + min(self.timeout_seconds, 120.0)
        while True:
            try:
                lock.mkdir(parents=False)
                return
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out waiting for backend lock: {lock}") from None
                time.sleep(0.1)

    @staticmethod
    def _release_lock(lock: Path) -> None:
        try:
            lock.rmdir()
        except OSError:
            pass
