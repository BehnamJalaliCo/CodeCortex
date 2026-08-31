"""Stable optional backend boundary."""

from codecortex.backends.context import ContextBackendAdapter
from codecortex.backends.contracts import (
    BackendCompatibilityError,
    BackendStatus,
    ContextIntelligence,
    GraphIntelligence,
    ManagedBackend,
    SymbolIntelligence,
)
from codecortex.backends.graph import GraphBackendAdapter
from codecortex.backends.manager import BackendManager, BackendProcessError, ProcessResult
from codecortex.backends.mcp_client import MCPError, MCPStdioClient
from codecortex.backends.spec import BACKENDS, BackendSpec
from codecortex.backends.symbols import SymbolBackendAdapter

__all__ = [
    "BACKENDS",
    "BackendCompatibilityError",
    "BackendManager",
    "BackendProcessError",
    "BackendSpec",
    "BackendStatus",
    "ContextBackendAdapter",
    "ContextIntelligence",
    "GraphBackendAdapter",
    "GraphIntelligence",
    "MCPError",
    "MCPStdioClient",
    "ManagedBackend",
    "ProcessResult",
    "SymbolBackendAdapter",
    "SymbolIntelligence",
]
