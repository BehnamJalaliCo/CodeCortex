"""Crash isolation, repository discovery, and engine discovery."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from codecortex.config import StructuralConfig
from codecortex.indexing.discovery import iter_repository_files
from codecortex.languages.sandbox import IsolatedParserProvider, native_provider
from codecortex.structural.engine import StructuralEngine


class _DeadPool:
    """Stands in for a worker pool whose process died mid-task."""

    def __init__(self) -> None:
        self.submissions = 0

    def submit(self, *_args, **_kwargs):
        self.submissions += 1
        raise BrokenPipeError("worker died")

    def shutdown(self, **_kwargs) -> None:
        return None


def test_worker_death_is_survivable_and_eventually_disables_native() -> None:
    provider = IsolatedParserProvider(max_restarts=2)
    provider._pool = _DeadPool()

    assert provider.parse("javascript", "const a = 1;") == []
    assert provider.degraded is False

    provider._pool = _DeadPool()
    assert provider.parse("javascript", "const a = 1;") == []
    # Second death in the same run: stop paying for restarts.
    assert provider.degraded is True

    provider._pool = _DeadPool()
    assert provider.parse("javascript", "const a = 1;") == []


def test_isolated_provider_parses_real_source() -> None:
    if not IsolatedParserProvider.available():
        pytest.skip("parsers extra is not installed")
    provider = IsolatedParserProvider()
    try:
        units = provider.parse("javascript", "function greet(name) { return helper(name); }")
    finally:
        provider.close()
    assert [unit.name for unit in units] == ["greet"]


def test_native_provider_honours_in_process_opt_out(monkeypatch: pytest.MonkeyPatch) -> None:
    if not IsolatedParserProvider.available():
        pytest.skip("parsers extra is not installed")
    monkeypatch.setenv("CODECORTEX_NATIVE_INPROCESS", "1")
    assert not isinstance(native_provider(), IsolatedParserProvider)
    monkeypatch.setenv("CODECORTEX_NATIVE_INPROCESS", "0")
    assert isinstance(native_provider(), IsolatedParserProvider)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"},
    )


def test_discovery_skips_ignored_paths_in_a_git_repository(tmp_path: Path) -> None:
    if not shutil_which("git"):
        pytest.skip("git is not installed")
    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("generated/\n")
    (tmp_path / "kept.py").write_text("value = 1\n")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "huge.py").write_text("value = 2\n")

    found = {path.name for path in iter_repository_files(tmp_path)}
    assert "kept.py" in found
    assert "huge.py" not in found


def test_discovery_falls_back_outside_git(tmp_path: Path) -> None:
    (tmp_path / "kept.py").write_text("value = 1\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.py").write_text("value = 2\n")

    found = {path.name for path in iter_repository_files(tmp_path)}
    assert found == {"kept.py"}


def test_structural_engine_found_beside_the_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shipped = bindir / "ast-grep"
    shipped.write_text("#!/bin/sh\n")
    shipped.chmod(0o755)

    monkeypatch.setattr(sys, "executable", str(bindir / "python"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))

    engine = StructuralEngine(tmp_path, config=StructuralConfig())
    assert engine.argv_prefix()[0] == str(shipped)


def shutil_which(name: str) -> str | None:
    import shutil

    return shutil.which(name)
