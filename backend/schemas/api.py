from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlayerRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gsis_id: str
    full_name: str | None = None

    @field_validator("gsis_id", mode="before")
    @classmethod
    def gsis_id_as_str(cls, v: Any) -> str:
        if v is None:
            raise ValueError("gsis_id is required")
        return str(v).strip()

    position: str | None = None
    team: str | None = None
    headshot_url: str | None = None
    birth_date: date | datetime | str | None = None
    years_exp: int | float | None = None


class PlayerDictionaryRow(BaseModel):
    gsis_id: str
    display_name: str
    search_key: str = Field(..., description="Lowercased name used for fuzzy matching")
    position: str | None = None
    team: str | None = None


class PbpShard(BaseModel):
    year: int = Field(..., description="Season year from the parquet filename")
    path: str = Field(..., description="URL path under the API (/data/...)")


class PlayerDetailResponse(BaseModel):
    player: PlayerRecord
    shards: list[PbpShard]


class HealthResponse(BaseModel):
    status: str
    player_index_loaded: bool
    data_through: str | None = Field(
        None, description='How current the data is, e.g. "2026 week 9"'
    )
    seasons: list[int] = Field(default_factory=list, description="Seasons with a shard")
