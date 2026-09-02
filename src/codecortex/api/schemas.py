"""HTTP transport schemas. Product logic lives in the application layer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    version: str


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
