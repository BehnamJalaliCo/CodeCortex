"""Shared domain models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Capability(StrEnum):
    REPOSITORY = "repository"
    SYMBOLS = "symbols"
    CONTEXT = "context"
    MEMORY = "memory"
    VALIDATION = "validation"


class RequestKind(StrEnum):
    EXPLAIN = "explain"
    LOCATE = "locate"
    DEBUG = "debug"
    REFACTOR = "refactor"
    CHANGE = "change"
    REVIEW = "review"
    UNKNOWN = "unknown"


class AgentRequest(BaseModel):
    query: str = Field(min_length=1)
    project_root: str = "."
    kind: RequestKind = RequestKind.UNKNOWN
    metadata: dict[str, Any] = Field(default_factory=dict)


class RouteScore(BaseModel):
    capability: Capability
    score: float = Field(ge=0.0, le=1.0)
    reason: str


class RoutePlan(BaseModel):
    request_kind: RequestKind
    scores: list[RouteScore]
    selected: list[Capability]
    context_budget: int = Field(default=32_000, gt=0)


class ContextChunk(BaseModel):
    source: str
    content: str
    tokens: int = Field(ge=0)
    relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EngineResult(BaseModel):
    capability: Capability
    content: str = ""
    chunks: list[ContextChunk] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    request: AgentRequest
    plan: RoutePlan
    results: list[EngineResult] = Field(default_factory=list)
    context_tokens: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
