from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    data_ready: bool = Field(
        ..., description="True once the manifest lists a season and the players file"
    )
    data_through: str | None = Field(
        None, description='How current the data is, e.g. "2026 week 9"'
    )
    built_at: str | None = Field(
        None, description="When the shards were built (ISO 8601, UTC): what the stale banner ages"
    )
    seasons: list[int] = Field(default_factory=list, description="Seasons with a shard")
