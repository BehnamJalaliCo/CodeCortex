"""Isolated lifecycle management for CodeCortex backend engines."""

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


def _discover_source_root() -> Path | None:
    configured = os.getenv("CODECORTEX_SOURCE_ROOT")
    if configured:
        candidate = Path(configured).expanduser().resolve()
        return candidate if candidate.is_dir() else None
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return None


class BackendManager:
    """Provision pinned engines, preferring the source carried by the checkout."""

    def __init__(
        self,
        cache_root: Path | None = None,
        timeout_seconds: float = 300.0,
        health_ttl_seconds: float = 30.0,
        source_root: Path | None = None,
    ) -> None:
        self.cache_root = (cache_root or _default_cache_root()).expanduser().resolve()
        self.timeout_seconds = timeout_seconds
        self.health_ttl_seconds = health_ttl_seconds
        self.source_root = source_root.expanduser().resolve() if source_root else _discover_source_root()
        self._probe_cache: dict[tuple[str, str], tuple[float, bool]] = {}

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

    def local_source_path(self, spec: BackendSpec) -> Path | None:
        if self.source_root is None or not spec.vendor_path:
            return None
        candidate = (self.source_root / spec.vendor_path).resolve()
        try:
            candidate.relative_to(self.source_root)
        except ValueError:
            raise RuntimeError(f"backend vendor path escapes source root: {spec.vendor_path}") from None
        if not candidate.is_dir() or not (candidate / "pyproject.toml").is_file():
            return None
        revision = self._git_revision(candidate)
        if revision is not None and revision != spec.revision:
            raise RuntimeError(
                f"vendored backend revision mismatch for {spec.key}: expected {spec.revision}, found {revision}"
            )
        return candidate

    def install_requirement(self, spec: BackendSpec) -> str:
        local = self.local_source_path(spec)
        if local is None:
            return spec.source_requirement
        if spec.extras:
            return f"{spec.package}[{','.join(spec.extras)}] @ {local.as_uri()}"
        return str(local)

    def installation_metadata(self, spec: BackendSpec) -> dict[str, object] | None:
        return self._load_metadata(spec)

    def is_installed(self, spec: BackendSpec) -> bool:
        metadata = self._load_metadata(spec)
        if not metadata or metadata.get("revision") != spec.revision or not self.command_path(spec).exists():
            return False
        local = self.local_source_path(spec)
        return local is None or metadata.get("source_kind") == "vendored"

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
            local = self.local_source_path(spec)
            self._install(spec)
            payload = asdict(spec)
            payload["installed_at"] = time.time()
            payload["source_kind"] = "vendored" if local is not None else "remote"
            payload["source_path"] = str(local) if local is not None else None
            self.metadata_path(spec).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            command = self.command_path(spec)
            if not command.exists():
                raise RuntimeError(f"backend installed without expected command: {command}")
            self._probe_cache.pop((spec.key, spec.revision), None)
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
        result = ProcessResult(argv, process.returncode, process.stdout, process.stderr, (time.perf_counter() - started) * 1000)
        if check and result.returncode != 0:
            raise BackendProcessError(result)
        return result

    def probe(self, spec: BackendSpec, provision: bool = False, *, force: bool = False) -> bool:
        key = (spec.key, spec.revision)
        now = time.monotonic()
        cached = self._probe_cache.get(key)
        if not force and cached is not None and now - cached[0] <= self.health_ttl_seconds:
            return cached[1]
        try:
            if not provision and not self.is_installed(spec):
                healthy = False
            else:
                result = self.run(spec, ("--help",), timeout_seconds=30, provision=provision, check=False)
                healthy = result.returncode == 0
        except (OSError, RuntimeError, subprocess.SubprocessError):
            healthy = False
        self._probe_cache[key] = (now, healthy)
        return healthy

    def remove(self, spec: BackendSpec) -> None:
        shutil.rmtree(self.environment_dir(spec), ignore_errors=True)
        self._probe_cache.pop((spec.key, spec.revision), None)

    def _create_environment(self, env_dir: Path, spec: BackendSpec) -> None:
        uv = shutil.which("uv")
        if uv:
            result = subprocess.run([uv, "venv", "--python", spec.python, str(env_dir)], text=True, capture_output=True, timeout=self.timeout_seconds, check=False)
            if result.returncode == 0:
                return
        venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)

    def _install(self, spec: BackendSpec) -> None:
        python = self.python_path(spec)
        requirement = self.install_requirement(spec)
        uv = shutil.which("uv")
        argv = [uv, "pip", "install", "--python", str(python), requirement] if uv else [str(python), "-m", "pip", "install", requirement]
        process = subprocess.run(argv, text=True, capture_output=True, timeout=self.timeout_seconds, check=False)
        if process.returncode != 0:
            raise RuntimeError(process.stderr.strip() or process.stdout.strip())

    def _load_metadata(self, spec: BackendSpec) -> dict[str, object] | None:
        try:
            value = json.loads(self.metadata_path(spec).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _git_revision(path: Path) -> str | None:
        try:
            process = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], text=True, capture_output=True, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        revision = process.stdout.strip()
        return revision if process.returncode == 0 and len(revision) == 40 else None

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
