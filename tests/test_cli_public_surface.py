from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from codecortex.entrypoint import app


runner = CliRunner()


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text(
        "class Service:\n"
        "    def run(self, value: int) -> int:\n"
        "        return helper(value)\n\n"
        "def helper(value: int) -> int:\n"
        "    return value + 1\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "CodeCortex CI"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
    return root


def _ok(args: list[str]) -> str:
    result = runner.invoke(app, args)
    assert result.exit_code == 0, f"{args}: {result.stdout}\n{result.exception!r}"
    return result.stdout


def test_core_cli_workflows(tmp_path: Path) -> None:
    root = _project(tmp_path)

    _ok(["version"])
    _ok(["init", str(root)])
    _ok(["index", "--path", str(root)])
    _ok(["semantic", "Service helper", "--path", str(root), "--limit", "5"])
    _ok(["architecture", "--path", str(root)])
    _ok(["architecture-baseline", "--path", str(root)])
    _ok(["architecture-drift", "--path", str(root)])
    _ok(["impact", "Service", "--path", str(root)])
    _ok(["knowledge", "--path", str(root)])
    _ok(["history", "app.py", "--path", str(root)])
    _ok(["symbol-history", "app.py", "1", "3", "--path", str(root)])
    _ok(["pr", "HEAD~0", "--head", "HEAD", "--path", str(root)])

    _ok(["team-remember", "decision", "keep APIs stable", "--path", str(root)])
    _ok(["team-search", "stable", "--path", str(root)])
    _ok(["workspace-add", "self", str(root), "--path", str(root)])
    _ok(["workspace-search", "Service", "--path", str(root)])

    _ok(["remember", "goal", "ship safely", "--path", str(root)])
    _ok(["doctor", "--path", str(root)])
    _ok(["route", "find Service references", "--path", str(root)])
    _ok(["run", "find Service", "--path", str(root)])
    _ok(["stats", "--path", str(root)])


def test_extended_cli_and_benchmark_paths(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _ok(["backend", "list"])
    _ok(["backend", "status", "--path", str(root)])
    _ok(["backend-status", "--path", str(root)])
    _ok(["agents", "detect", "--path", str(root)])
    _ok(["agents", "configure", "--path", str(root), "--dry-run"])
    _ok(["bootstrap", "--path", str(root), "--no-backends", "--no-agents"])

    cases = root / "cases.json"
    cases.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "service",
                        "query": "Service helper",
                        "expected_paths": ["app.py"],
                        "expected_symbols": ["Service"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = root / "results.json"
    _ok(
        [
            "benchmark",
            "--path",
            str(root),
            "--cases",
            str(cases),
            "--output",
            str(output),
        ]
    )
    assert output.exists()
    _ok(["benchmark-gate", "--path", str(root)])
