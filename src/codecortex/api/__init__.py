"""ASGI service adapter for the CodeCortex platform."""

from codecortex.api.app import create_app

__all__ = ["create_app"]
