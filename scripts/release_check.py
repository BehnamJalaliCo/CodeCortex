#!/usr/bin/env python3
"""Fail a release when tag, package version, or distribution identity drift."""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path

DISTRIBUTION = "codecortex-context-engine"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    args = parser.parse_args()
    payload = tomllib.loads(args.pyproject.read_text(encoding="utf-8"))
    project = payload["project"]
    name = str(project["name"])
    version = str(project["version"])
    if name != DISTRIBUTION:
        raise SystemExit(f"distribution mismatch: expected {DISTRIBUTION}, got {name}")
    expected = f"v{version}"
    if args.tag != expected:
        raise SystemExit(f"tag/version mismatch: tag={args.tag}, expected={expected}")
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:a\d+|b\d+|rc\d+)?", args.tag):
        raise SystemExit(f"unsupported release tag: {args.tag}")
    print(f"release identity verified: {name} {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
