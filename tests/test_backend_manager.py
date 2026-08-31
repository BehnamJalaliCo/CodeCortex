from pathlib import Path

import pytest

from codecortex.backends.manager import BackendManager
from codecortex.backends.spec import BACKENDS, BackendSpec


def _configured_spec() -> BackendSpec:
    return BackendSpec(
        key="graph",
        capabilities=("graph",),
        package="example-backend",
        source_url="https://example.invalid/backend.git",
        revision="a" * 40,
        command="example-backend",
        license_id="Apache-2.0",
    )


def test_default_backend_specs_do_not_embed_sources() -> None:
    for spec in BACKENDS.values():
        assert not spec.configured
        with pytest.raises(RuntimeError):
            _ = spec.source_requirement


def test_backend_manager_uses_revision_scoped_environment(tmp_path: Path) -> None:
    manager = BackendManager(tmp_path)
    spec = _configured_spec()
    environment = manager.environment_dir(spec)
    assert environment.parent.name == spec.key
    assert environment.name == spec.revision[:12]
    assert manager.metadata_path(spec).parent == environment
