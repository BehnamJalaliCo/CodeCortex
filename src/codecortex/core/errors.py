"""Domain errors used across CodeCortex."""


class CodeCortexError(Exception):
    """Base exception for CodeCortex."""


class EngineUnavailableError(CodeCortexError):
    """Raised when a requested engine is not available."""


class RoutingError(CodeCortexError):
    """Raised when a request cannot be routed safely."""


class ContextBudgetExceededError(CodeCortexError):
    """Raised when a hard context budget cannot be satisfied."""
