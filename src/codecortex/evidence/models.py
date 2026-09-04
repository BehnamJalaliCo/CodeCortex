"""Unified evidence records shared by every CodeCortex intelligence layer."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class EvidenceKind(StrEnum):
    """What a single piece of evidence asserts."""

    DEFINITION = "definition"
    REFERENCE = "reference"
    IMPLEMENTATION = "implementation"
    CALL = "call"
    IMPORT = "import"
    TYPE_RELATION = "type_relation"
    DOCUMENTATION = "documentation"
    STRUCTURAL_MATCH = "structural_match"
    GIT_HISTORY = "git_history"
    MEMORY = "memory"
    VALIDATION = "validation"


class TrustTier(StrEnum):
    """Categorical strength of the resolution that produced the evidence.

    The tier is the agent-facing signal. It is deliberately categorical so that
    a downstream consumer never has to guess whether ``0.82`` came from a
    compiler or from a name coincidence.
    """

    EXACT = "exact"
    NEAR_EXACT = "near_exact"
    STRUCTURAL = "structural"
    INFERRED_HIGH = "inferred_high"
    INFERRED = "inferred"
    WEAK = "weak"


class ProviderState(StrEnum):
    """Availability of an evidence provider for one collection attempt."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    NOT_CONFIGURED = "not_configured"
    CREDENTIALS_MISSING = "credentials_missing"
    OFFLINE = "offline"
    ERROR = "error"


class EvidenceRecord(BaseModel):
    """One ranked, attributable observation about the repository or its dependencies."""

    evidence_id: str = ""
    kind: EvidenceKind

    provider: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    trust: TrustTier = TrustTier.INFERRED

    path: str | None = None
    start_line: int | None = None
    start_column: int | None = None
    end_line: int | None = None
    end_column: int | None = None

    symbol: str | None = None
    target_symbol: str | None = None

    content: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    exact: bool = False
    stale: bool = False

    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _fill_identity(self) -> EvidenceRecord:
        if self.exact and self.trust is not TrustTier.EXACT:
            raise ValueError("exact evidence must use the exact trust tier")
        if not self.evidence_id:
            payload = "␟".join(
                [
                    self.provider,
                    self.provenance,
                    self.kind.value,
                    self.path or "",
                    str(self.start_line),
                    str(self.start_column),
                    str(self.end_line),
                    str(self.end_column),
                    self.symbol or "",
                    self.target_symbol or "",
                    self.content,
                ]
            )
            digest = hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()
            object.__setattr__(self, "evidence_id", digest)
        return self

    @property
    def location(self) -> str:
        """Human-readable ``path:line:column`` anchor, or an empty string."""
        if self.path is None:
            return ""
        if self.start_line is None:
            return self.path
        if self.start_column is None:
            return f"{self.path}:{self.start_line}"
        return f"{self.path}:{self.start_line}:{self.start_column}"


class EvidenceRequest(BaseModel):
    """A question posed to one or more evidence providers."""

    query: str = ""
    project_root: str = "."
    path: str | None = None
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)
    symbol: str | None = None
    language: str | None = None
    kinds: tuple[EvidenceKind, ...] = ()
    limit: int = Field(default=50, ge=1, le=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderReport(BaseModel):
    """Availability and fallback state for one provider in one collection."""

    provider: str
    state: ProviderState
    detail: str = ""
    fallback: str | None = None

    @property
    def usable(self) -> bool:
        return self.state in {ProviderState.AVAILABLE, ProviderState.STALE}


class EvidenceBundle(BaseModel):
    """Ranked evidence plus the provider states that produced (or failed to produce) it."""

    records: list[EvidenceRecord] = Field(default_factory=list)
    providers: list[ProviderReport] = Field(default_factory=list)

    @property
    def exact(self) -> list[EvidenceRecord]:
        return [record for record in self.records if record.exact and not record.stale]

    @property
    def degraded(self) -> bool:
        """True when at least one provider could not deliver its strongest evidence."""
        return any(not report.usable or report.state is ProviderState.STALE for report in self.providers)

    def report_for(self, provider: str) -> ProviderReport | None:
        return next((item for item in self.providers if item.provider == provider), None)
