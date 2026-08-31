from pathlib import Path

from codecortex.backends.factory import build_backend_stack
from codecortex.config import CortexConfig
from codecortex.core.models import Capability
from codecortex.memory import JsonMemoryStore


def test_backend_stack_keeps_builtin_engines_by_default(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("CODECORTEX_BACKENDS", "builtin")
    config = CortexConfig(project_root=tmp_path)
    memory = JsonMemoryStore(tmp_path / ".codecortex" / "memory")
    stack = build_backend_stack(config, memory)
    assert stack.active == ()
    assert stack.registry.get(Capability.REPOSITORY) is not None
    assert stack.registry.get(Capability.SYMBOLS) is not None
