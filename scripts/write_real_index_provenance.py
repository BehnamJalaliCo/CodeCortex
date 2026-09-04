#!/usr/bin/env python3
"""Write the provenance manifests for the committed real-index fixtures.

Run by ``scripts/regenerate_real_index_fixtures.sh`` after regenerating an
index. Kept separate so the digests are computed the same way the conformance
test verifies them, rather than by two implementations that can drift.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "real_index"

#: Generation root recorded in ``Metadata.project_root``. Stable on purpose:
#: a per-run temporary path would churn the committed index on every refresh.
GENERATION_ROOT = "/tmp/codecortex-fixture"

SPECS: tuple[tuple[str, tuple[str, ...], str, str, str, str, str], ...] = (
    (
        "python_project",
        ("*.py",),
        "https://github.com/sourcegraph/scip-python",
        "8b60bbce1f2a4c7a517776cb395bbafb2e731e4f",
        "scip-python index . --project-name=codecortex-python-fixture --project-version=1.0.0",
        "scip-python",
        "0.6.6",
    ),
    (
        "typescript_project",
        ("*.ts", "*.json"),
        "https://github.com/sourcegraph/scip-typescript",
        "891eb4293709a6a587bf4468dfa1b45a85182fd9",
        "scip-typescript index --no-progress-bar",
        "scip-typescript",
        "0.4.0",
    ),
)

SCIP_ORACLE_COMMIT = "1c2b6db7e560d5233c944f36e4ac1377cc6963fc"


def digest_sources(project: Path, patterns: tuple[str, ...]) -> str:
    """Return an order-independent digest over every fixture source file."""
    digest = hashlib.sha256()
    for path in sorted(item for pattern in patterns for item in project.rglob(pattern)):
        if path.name in {"expected.json", "PROVENANCE.json"}:
            continue
        digest.update(path.relative_to(project).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> int:
    for name, patterns, repo, commit, command, tool, version in SPECS:
        project = FIXTURE_ROOT / name
        index = project / "index.scip"
        expected = project / "expected.json"
        manifest = {
            "generator_repository": repo,
            "generator_commit": commit,
            "generator_tool": tool,
            "generator_version": version,
            "command": command,
            "generated_from": GENERATION_ROOT,
            "source_fixture_hash": digest_sources(project, patterns),
            "index_hash": hashlib.sha256(index.read_bytes()).hexdigest(),
            "index_bytes": index.stat().st_size,
            "expected_json_hash": hashlib.sha256(expected.read_bytes()).hexdigest(),
            "oracle": {
                "tool": "scip",
                "repository": "https://github.com/scip-code/scip",
                "commit": SCIP_ORACLE_COMMIT,
                "lint": "clean",
                "expected_json_command": "scip print --json index.scip",
            },
            "regeneration": "scripts/regenerate_real_index_fixtures.sh",
            "note": (
                "Generated index and oracle output are committed; the indexer "
                "source is not vendored."
            ),
        }
        (project / "PROVENANCE.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{name}: sources {manifest['source_fixture_hash'][:16]} index {manifest['index_hash'][:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
