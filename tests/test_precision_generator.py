from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from codecortex.config import PrecisionIndexConfig
from codecortex.precision import PrecisionGeneratorError, PrecisionIndexGenerator
from codecortex.precision.index import default_index_path


def _generator(root: Path, *command: str, **overrides: object) -> PrecisionIndexGenerator:
    return PrecisionIndexGenerator(
        root, PrecisionIndexConfig(generator_command=tuple(command), **overrides)
    )


def test_generator_is_not_configured_by_default(tmp_path: Path) -> None:
    generator = _generator(tmp_path)
    assert not generator.configured
    with pytest.raises(PrecisionGeneratorError, match="no precision index generator"):
        generator.resolve_executable()


def test_generator_runs_a_configured_argument_vector(tmp_path: Path) -> None:
    script = tmp_path / "indexer.py"
    script.write_text(
        "import sys\nsys.stdout.write('indexed ' + ' '.join(sys.argv[1:]))\n", encoding="utf-8"
    )
    result = _generator(tmp_path, sys.executable, str(script), "--out", "index.cortexidx").generate()
    assert result.succeeded
    assert result.stdout == "indexed --out index.cortexidx"
    assert result.command[0] == str(Path(sys.executable).resolve())


def test_generator_reports_a_failing_indexer_without_raising(tmp_path: Path) -> None:
    script = tmp_path / "broken.py"
    script.write_text("import sys\nsys.stderr.write('boom')\nraise SystemExit(3)\n", encoding="utf-8")
    result = _generator(tmp_path, sys.executable, str(script)).generate()
    assert not result.succeeded
    assert result.exit_code == 3
    assert result.stderr == "boom"


def test_generator_rejects_missing_executables(tmp_path: Path) -> None:
    with pytest.raises(PrecisionGeneratorError, match="not found on PATH"):
        _generator(tmp_path, "codecortex-no-such-indexer").resolve_executable()
    with pytest.raises(PrecisionGeneratorError, match="not found"):
        _generator(tmp_path, str(tmp_path / "missing" / "indexer")).resolve_executable()


def test_generator_never_uses_a_shell(tmp_path: Path) -> None:
    """A shell metacharacter must be passed through as a literal argument."""
    script = tmp_path / "echo.py"
    script.write_text("import sys\nsys.stdout.write(sys.argv[1])\n", encoding="utf-8")
    marker = tmp_path / "pwned.txt"
    result = _generator(
        tmp_path, sys.executable, str(script), f"; touch {marker}"
    ).generate()
    assert result.stdout == f"; touch {marker}"
    assert not marker.exists()


def test_generator_enforces_its_timeout(tmp_path: Path) -> None:
    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    generator = _generator(
        tmp_path, sys.executable, str(script), generator_timeout_seconds=0.5
    )
    with pytest.raises(PrecisionGeneratorError, match="timed out"):
        generator.generate()


def test_generator_reports_a_launch_failure(tmp_path: Path) -> None:
    not_executable = tmp_path / "data.bin"
    not_executable.write_bytes(b"\x00\x01")
    os.chmod(not_executable, stat.S_IRUSR | stat.S_IWUSR)
    generator = _generator(tmp_path, str(not_executable))
    with pytest.raises(PrecisionGeneratorError, match="generation failed"):
        generator.generate()


def test_default_index_path_is_project_local(tmp_path: Path) -> None:
    assert default_index_path(tmp_path).is_relative_to(tmp_path)
    assert default_index_path(tmp_path).name == "index.cortexidx"
