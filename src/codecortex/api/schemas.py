"""HTTP transport schemas. Product logic lives in the application layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: str
    version: str


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    workspace_id: str
    name: str
    created_at: str


class RepositoryCreate(BaseModel):
    workspace: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    root: str = Field(min_length=1)


class RepositoryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    repository_id: str
    workspace: str
    name: str
    root: str
    created_at: str


class JobResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    job_id: str
    kind: str
    status: str
    progress: float
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    actor: str
    workspace: str | None
    repository_id: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
