from codecortex.api.versioning import SUPPORTED_API_VERSIONS, current_api_version, version_manifest


def test_v1_is_stable_and_non_breaking() -> None:
    version = next(item for item in SUPPORTED_API_VERSIONS if item.version == "v1")
    assert version.status == "stable"
    assert version.breaking_changes_allowed is False
    assert current_api_version() == "v1"


def test_version_manifest_documents_compatibility_rule() -> None:
    manifest = version_manifest()
    assert manifest["current"] == "v1"
    assert "Breaking changes" in str(manifest["compatibility_rule"])
