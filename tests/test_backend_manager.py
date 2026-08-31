from pathlib import Path

from codecortex.backends.manager import BackendManager
from codecortex.backends.spec import BACKENDS


def test_backend_specs_are_revision_pinned() -> None:
    for spec in BACKENDS.values():
        assert len(spec.revision) == 40
        assert spec.source_requirement.endswith(spec.revision)
        assert spec.command
        assert spec.license_id


def test_backend_manager_uses_revision_scoped_environment(tmp_path: Path) -> None:
    manager = BackendManager(tmp_path)
    spec = BACKENDS["graph"]
    environment = manager.environment_dir(spec)
    assert environment.parent.name == spec.key
    assert environment.name == spec.revision[:12]
    assert manager.metadata_path(spec).parent == environment
