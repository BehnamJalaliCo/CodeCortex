from pathlib import Path
from codecortex.platform_milestones import MilestoneManifest


def test_release_milestones_are_ordered_a_through_g() -> None:
    manifest = MilestoneManifest.load(Path("platform/milestones.json"))
    assert [item.id for item in manifest.milestones] == list("ABCDEFG")
    assert manifest.milestones[0].name == "Foundation"
    assert manifest.milestones[-1].name == "Safe Development Platform"


def test_milestone_completion_requires_every_capability() -> None:
    manifest = MilestoneManifest.load(Path("platform/milestones.json"))
    required = set(manifest.milestones[0].requires)
    assert manifest.completion(required)["A"] is True
    assert manifest.completion(required - {next(iter(required))})["A"] is False
