"""Shared contracts that keep CLI, MCP and web transports behaviorally aligned."""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class MeasurementKind(StrEnum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class MeasurementValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float | int | None = None
    kind: MeasurementKind
    unit: str | None = None

    @classmethod
    def measured(cls, value: float | int, unit: str | None = None) -> "MeasurementValue":
        return cls(value=value, kind=MeasurementKind.MEASURED, unit=unit)

    @classmethod
    def estimated(cls, value: float | int, unit: str | None = None) -> "MeasurementValue":
        return cls(value=value, kind=MeasurementKind.ESTIMATED, unit=unit)

    @classmethod
    def unavailable(cls, unit: str | None = None) -> "MeasurementValue":
        return cls(value=None, kind=MeasurementKind.UNAVAILABLE, unit=unit)


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True)

    items: tuple[T, ...] = ()
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
