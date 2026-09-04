#!/usr/bin/env python3
from pathlib import Path

from codecortex.platform_governance import PriorityManifest


def main() -> None:
    manifest = PriorityManifest.load(Path("platform/priorities.json"))
    for stage in manifest.stages:
        print(f"{stage.id}: {stage.name} — {len(stage.items)} items")


if __name__ == "__main__":
    main()
