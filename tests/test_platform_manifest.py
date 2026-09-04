from codecortex.platform_manifest import CAPABILITIES, product_manifest


def test_product_manifest_exposes_core_control_plane_groups() -> None:
    manifest = product_manifest()
    assert manifest["product"] == "CodeCortex Platform"
    groups = set(manifest["groups"])
    assert {"intelligence", "engineering", "runtime", "scale", "administration"}.issubset(groups)


def test_mutating_product_surfaces_are_explicit() -> None:
    mutation_keys = {item.key for item in CAPABILITIES if item.mutating}
    assert "safe-code-actions" in mutation_keys
    assert "organization-rbac" in mutation_keys
