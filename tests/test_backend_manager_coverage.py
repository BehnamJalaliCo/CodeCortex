from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from codecortex.backends.manager import (
    BackendManager,
    BackendProcessError,
    ProcessResult,
    _discover_source_root,
)
from codecortex.backends.spec import BackendSpec

REV = "a" * 40


def _spec(**overrides: object) -> BackendSpec:
    values: dict[str, object] = {
        "key": "demo",
        "capabilities": ("query",),
        "package": "demo-package",
        "source_url": "https://example.invalid/demo.git",
        "revision": REV,
        "command": "demo",
        "license_id": "Apache-2.0",
        "extras": (),
        "python": "3.13",
        "vendor_path": None,
    }
    values.update(overrides)
    return BackendSpec(**values)  # type: ignore[arg-type]


def test_paths_metadata_and_unconfigured(tmp_path: Path) -> None:
    manager = BackendManager(cache_root=tmp_path, source_root=tmp_path)
    spec = _spec()
    assert manager.environment_dir(spec) == tmp_path / "demo" / REV[:12]
    assert manager.metadata_path(spec).name == ".codecortex-backend.json"
    assert manager.command_path(spec).name.startswith("demo")
    assert manager.install_requirement(spec).startswith("git+")
    assert manager.installation_metadata(spec) is None
    assert not manager.is_installed(_spec(package=""))
    with pytest.raises(RuntimeError):
        manager.install_requirement(_spec(package=""))
    with pytest.raises(RuntimeError):
        manager.ensure(_spec(package=""))


def test_local_source_validation_and_requirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    local = source / "vendor" / "demo"
    local.mkdir(parents=True)
    (local / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0'\n", encoding="utf-8")
    manager = BackendManager(cache_root=tmp_path / "cache", source_root=source)

    monkeypatch.setattr(manager, "_git_revision", lambda _path: REV)
    spec = _spec(vendor_path="vendor/demo", extras=("one", "two"))
    assert manager.local_source_path(spec) == local
    requirement = manager.install_requirement(spec)
    assert "demo-package[one,two]" in requirement
    assert local.as_uri() in requirement

    monkeypatch.setattr(manager, "_git_revision", lambda _path: "b" * 40)
    with pytest.raises(RuntimeError, match="revision mismatch"):
        manager.local_source_path(spec)

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    escaping = _spec(vendor_path="../outside")
    with pytest.raises(RuntimeError, match="escapes source root"):
        manager.local_source_path(escaping)

    assert manager.local_source_path(_spec(vendor_path="missing")) is None


def test_ensure_install_probe_remove_and_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = BackendManager(cache_root=tmp_path, source_root=tmp_path, health_ttl_seconds=60)
    spec = _spec()

    def create_environment(env_dir: Path, _spec_value: BackendSpec) -> None:
        del env_dir
        manager.command_path(spec).parent.mkdir(parents=True, exist_ok=True)
        manager.command_path(spec).write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(manager, "_create_environment", create_environment)
    monkeypatch.setattr(manager, "_install", lambda _spec_value: None)
    command = manager.ensure(spec)
    assert command.exists()
    metadata = manager.installation_metadata(spec)
    assert metadata and metadata["revision"] == REV
    assert manager.is_installed(spec)
    assert manager.ensure(spec) == command

    calls = 0

    def fake_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = manager.run(spec, ("hello",), provision=False)
    assert result.returncode == 0 and result.stdout == "ok"
    assert manager.probe(spec, force=True)
    cached_calls = calls
    assert manager.probe(spec)
    assert calls == cached_calls

    manager.remove(spec)
    assert not manager.environment_dir(spec).exists()
    assert not manager.probe(spec, provision=False, force=True)


def test_run_error_and_probe_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = BackendManager(cache_root=tmp_path, source_root=tmp_path)
    spec = _spec()
    command = manager.command_path(spec)
    command.parent.mkdir(parents=True)
    command.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=3, stdout="", stderr="boom"),
    )
    with pytest.raises(BackendProcessError, match="boom"):
        manager.run(spec, (), provision=False)
    unchecked = manager.run(spec, (), provision=False, check=False)
    assert unchecked.returncode == 3

    monkeypatch.setattr(manager, "is_installed", lambda _spec_value: True)
    monkeypatch.setattr(
        manager,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("bad")),
    )
    assert not manager.probe(spec, force=True)

    missing = BackendManager(cache_root=tmp_path / "missing", source_root=tmp_path)
    with pytest.raises(FileNotFoundError):
        missing.run(spec, (), provision=False)


def test_environment_install_metadata_git_and_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = BackendManager(cache_root=tmp_path, source_root=tmp_path, timeout_seconds=0.01)
    spec = _spec()
    env_dir = manager.environment_dir(spec)

    monkeypatch.setattr(
        "codecortex.backends.manager.shutil.which",
        lambda name: "/usr/bin/uv" if name == "uv" else None,
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    manager._create_environment(env_dir, spec)

    manager.python_path(spec).parent.mkdir(parents=True, exist_ok=True)
    manager.python_path(spec).write_text("", encoding="utf-8")
    manager._install(spec)

    metadata = manager.metadata_path(spec)
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text("[]", encoding="utf-8")
    assert manager.installation_metadata(spec) is None
    metadata.write_text("not-json", encoding="utf-8")
    assert manager.installation_metadata(spec) is None

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=REV + "\n", stderr=""),
    )
    assert manager._git_revision(tmp_path) == REV
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError()),
    )
    assert manager._git_revision(tmp_path) is None

    lock = tmp_path / "lock"
    manager._acquire_lock(lock)
    assert lock.is_dir()
    manager._release_lock(lock)
    manager._release_lock(lock)


def test_backend_process_error_message() -> None:
    result = ProcessResult(("demo",), 7, "stdout fallback", "", 1.0)
    error = BackendProcessError(result)
    assert error.result is result
    assert "stdout fallback" in str(error)


def test_source_root_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODECORTEX_SOURCE_ROOT", str(tmp_path))
    assert _discover_source_root() == tmp_path.resolve()
    monkeypatch.setenv("CODECORTEX_SOURCE_ROOT", str(tmp_path / "missing"))
    assert _discover_source_root() is None
