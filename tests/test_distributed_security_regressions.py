import pytest

from codecortex.distributed.organization import OrganizationPolicyStore


def test_existing_organization_cannot_be_claimed_by_a_new_owner(tmp_path) -> None:
    store = OrganizationPolicyStore(tmp_path / "org.db")
    store.create_organization("acme", "Acme", owner="alice")
    store.create_organization("acme", "Acme", owner="alice")  # idempotent for same owner
    with pytest.raises(ValueError):
        store.create_organization("acme", "Acme", owner="mallory")
    assert store.role("acme", "mallory") is None
    assert store.role("acme", "alice") == "owner"


def test_admin_cannot_escalate_to_or_modify_owner(tmp_path) -> None:
    store = OrganizationPolicyStore(tmp_path / "org.db")
    store.create_organization("acme", "Acme", owner="alice")
    store.set_member("acme", "alice", "bob", "admin")
    with pytest.raises(PermissionError):
        store.set_member("acme", "bob", "bob", "owner")
    with pytest.raises(PermissionError):
        store.set_member("acme", "bob", "alice", "member")
    store.set_member("acme", "alice", "carol", "owner")
    assert store.role("acme", "carol") == "owner"
