#!/usr/bin/env python3
"""Fail CI when a platform architecture boundary is crossed."""
from __future__ import annotations

import json
from pathlib import Path


def files_for(scope: Path) -> list[Path]:
    if scope.is_file():
        return [scope]
    return [path for path in scope.rglob("*") if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".js", ".jsx"}]


def main() -> None:
    root = Path.cwd()
    manifest = json.loads((root / "platform/architecture_rules.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    for rule in manifest["rules"]:
        scope = root / rule["scope"]
        for path in files_for(scope):
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in rule["forbidden"]:
                if token in text:
                    failures.append(f"{rule['id']}: {path.relative_to(root)} contains {token!r}")
    if failures:
        raise SystemExit("Platform architecture violations:\n" + "\n".join(failures))
    print(f"Platform architecture: {len(manifest['rules'])} rules passed")


if __name__ == "__main__":
    main()
