from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    data_ready: bool = Field(
        ..., description="True once a manifest with at least one season exists"
    )
    data_through: str | None = Field(
        None, description='How current the data is, e.g. "2026 week 9"'
    )
    seasons: list[int] = Field(default_factory=list, description="Seasons with a shard")
