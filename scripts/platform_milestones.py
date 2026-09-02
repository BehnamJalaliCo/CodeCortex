#!/usr/bin/env python3
from pathlib import Path
from codecortex.platform_milestones import MilestoneManifest


def main() -> None:
    manifest = MilestoneManifest.load(Path("platform/milestones.json"))
    for milestone in manifest.milestones:
        print(f"{milestone.id}: {milestone.name} ({len(milestone.requires)} requirements)")


if __name__ == "__main__":
    main()
