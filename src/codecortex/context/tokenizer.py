"""Pluggable token counting with optional model tokenizer support."""

from __future__ import annotations

import importlib
import math
from typing import Any, Protocol


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...
    def truncate(self, text: str, limit: int) -> str: ...


class ApproxTokenCounter:
    """Dependency-free fallback compatible with historical CodeCortex estimates."""

    def count(self, text: str) -> int:
        return 0 if not text else max(1, math.ceil(len(text) / 4))

    def truncate(self, text: str, limit: int) -> str:
        if limit < 1:
            return ""
        return text[: limit * 4].rstrip()


class TiktokenCounter:
    """Exact counter for a configured tiktoken encoding when tiktoken is installed."""

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        module: Any = importlib.import_module("tiktoken")
        self.encoding = module.get_encoding(encoding_name)

    def count(self, text: str) -> int:
        return len(self.encoding.encode(text, disallowed_special=()))

    def truncate(self, text: str, limit: int) -> str:
        if limit < 1:
            return ""
        tokens = self.encoding.encode(text, disallowed_special=())[:limit]
        return str(self.encoding.decode(tokens)).rstrip()


class AutoTokenCounter:
    """Use an exact installed tokenizer and fall back to a conservative local counter."""

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        try:
            self._delegate: TokenCounter = TiktokenCounter(encoding_name)
            self.exact = True
        except (ImportError, ModuleNotFoundError):
            self._delegate = ApproxTokenCounter()
            self.exact = False

    def count(self, text: str) -> int:
        return self._delegate.count(text)

    def truncate(self, text: str, limit: int) -> str:
        return self._delegate.truncate(text, limit)
