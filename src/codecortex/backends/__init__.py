"""Optional isolated backends powered by mature external engines."""

from codecortex.backends.context import ContextBackendAdapter
from codecortex.backends.graph import GraphBackendAdapter
from codecortex.backends.manager import BackendManager, BackendProcessError, ProcessResult
from codecortex.backends.mcp_client import MCPError, MCPStdioClient
from codecortex.backends.spec import BACKENDS, BackendSpec
from codecortex.backends.symbols import SymbolBackendAdapter

__all__ = [
    "BACKENDS",
    "BackendManager",
    "BackendProcessError",
    "BackendSpec",
    "ContextBackendAdapter",
    "GraphBackendAdapter",
    "MCPError",
    "MCPStdioClient",
    "ProcessResult",
    "SymbolBackendAdapter",
]
