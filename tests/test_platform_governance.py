from pathlib import Path
from codecortex.platform_governance import PriorityManifest


def test_platform_priorities_are_p0_through_p5() -> None:
    manifest = PriorityManifest.load(Path("platform/priorities.json"))
    assert [item.id for item in manifest.stages] == ["P0", "P1", "P2", "P3", "P4", "P5"]
    assert manifest.priority_for("code-actions") == "P5"


def test_later_priority_requires_earlier_stages() -> None:
    manifest = PriorityManifest.load(Path("platform/priorities.json"))
    assert manifest.may_start("P3", {"P0", "P1", "P2"})
    assert not manifest.may_start("P3", {"P0", "P2"})
