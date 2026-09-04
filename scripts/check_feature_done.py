#!/usr/bin/env python3
"""Validate a feature-completion JSON file against the platform DoD."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from codecortex.platform_dod import DefinitionOfDone, FeatureCompletion


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("completion", type=Path)
    args = parser.parse_args()
    dod = DefinitionOfDone.load(Path("platform/definition_of_done.json"))
    payload = json.loads(args.completion.read_text(encoding="utf-8"))
    completion = FeatureCompletion(
        str(payload["feature"]), {str(k): bool(v) for k, v in payload.get("checks", {}).items()}
    )
    missing = dod.validate(completion)
    if missing:
        raise SystemExit(f"{completion.feature} is not done: {', '.join(missing)}")
    print(f"{completion.feature}: done")


if __name__ == "__main__":
    main()
