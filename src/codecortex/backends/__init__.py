"""Optional isolated backends powered by mature external engines."""

from codecortex.backends.graph import GraphBackendAdapter
from codecortex.backends.manager import BackendManager, BackendProcessError, ProcessResult
from codecortex.backends.spec import BACKENDS, BackendSpec

__all__ = [
    "BACKENDS",
    "BackendManager",
    "BackendProcessError",
    "BackendSpec",
    "GraphBackendAdapter",
    "ProcessResult",
]
