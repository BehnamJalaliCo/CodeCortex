import json
from pathlib import Path

from codecortex.api.versioning import current_api_version
from codecortex.platform_dod import DefinitionOfDone
from codecortex.platform_governance import PriorityManifest
from codecortex.platform_layout import validate_layout
from codecortex.platform_manifest import product_manifest
from codecortex.platform_milestones import MilestoneManifest


def test_roadmap_1_through_47_is_accounted_for() -> None:
    payload = json.loads(Path("platform/roadmap_completion.json").read_text(encoding="utf-8"))
    assert payload["completed"] == list(range(1, 48))
    assert payload["merge_policy"] == "protected-main-via-pull-request"


def test_platform_contracts_form_one_product() -> None:
    assert current_api_version() == "v1"
    assert validate_layout(Path.cwd()).valid
    assert [
        item.id for item in MilestoneManifest.load(Path("platform/milestones.json")).milestones
    ] == list("ABCDEFG")
    assert [item.id for item in PriorityManifest.load(Path("platform/priorities.json")).stages] == [
        f"P{i}" for i in range(6)
    ]
    assert len(DefinitionOfDone.load(Path("platform/definition_of_done.json")).required) >= 12
    manifest = product_manifest()
    assert manifest["product"] == "CodeCortex Platform"
    assert len(manifest["capabilities"]) >= 20
