"""Typed models for structural search and guarded rewrites."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field


class StructuralMatch(BaseModel):
    """One syntax-aware match, using one-based lines and columns."""

    path: str
    start_line: int = Field(ge=1)
    start_column: int = Field(ge=1)
    end_line: int = Field(ge=1)
    end_column: int = Field(ge=1)
    matched_text: str = ""
    captures: dict[str, str] = Field(default_factory=dict)
    rule_id: str | None = None
    language: str = ""
    replacement: str | None = None
    byte_start: int = Field(default=0, ge=0)
    byte_end: int = Field(default=0, ge=0)

    @property
    def byte_length(self) -> int:
        return max(0, self.byte_end - self.byte_start)


class RewriteFilePreview(BaseModel):
    """The proposed change to a single file, with the hash it was computed from."""

    path: str
    matches: int = Field(ge=0)
    original_sha256: str
    changed_bytes: int = Field(ge=0)
    diff: str = ""


class RewritePreview(BaseModel):
    """A reviewable, expiring plan that ``rewrite_apply`` must reference by id."""

    preview_id: str
    pattern: str
    replacement: str
    language: str
    files: list[RewriteFilePreview] = Field(default_factory=list)
    total_matches: int = Field(default=0, ge=0)
    total_changed_bytes: int = Field(default=0, ge=0)
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    affected_symbols: list[str] = Field(default_factory=list)
    affected_tests: list[str] = Field(default_factory=list)
    created_at: datetime
    expires_at: datetime
    warnings: list[str] = Field(default_factory=list)

    @property
    def expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at

    @classmethod
    def expiry(cls, ttl_seconds: int) -> tuple[datetime, datetime]:
        created = datetime.now(UTC)
        return created, created + timedelta(seconds=ttl_seconds)


class RewriteFileOutcome(BaseModel):
    path: str
    applied: bool
    reason: str = ""
    matches: int = Field(default=0, ge=0)


class RewriteResult(BaseModel):
    """What actually happened when a preview was applied."""

    preview_id: str
    applied: bool
    files: list[RewriteFileOutcome] = Field(default_factory=list)
    files_changed: int = Field(default=0, ge=0)
    matches_applied: int = Field(default=0, ge=0)
    rolled_back: bool = False
    reindexed_files: int = Field(default=0, ge=0)
    validation: dict[str, Any] = Field(default_factory=dict)
    post_impact: dict[str, Any] = Field(default_factory=dict)
    detail: str = ""


class StructuralError(RuntimeError):
    """Raised when a structural operation cannot be completed safely."""


class StructuralEngineUnavailable(StructuralError):
    """Raised when the structural engine is not installed or not runnable."""


class RewriteRejected(StructuralError):
    """Raised when policy, limits, or a changed file block a rewrite."""
