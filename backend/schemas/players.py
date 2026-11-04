"""The static player list the browser reads (`players.json`), written by the data build."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PlayerEntry(BaseModel):
    gsis_id: str = Field(..., min_length=1)
    full_name: str = Field(..., min_length=1)
    position: str | None = None
    team: str | None = None
    headshot_url: str | None = None
    birth_date: str | None = Field(None, description="ISO date")
    years_exp: int | None = None


class PlayersFile(BaseModel):
    schema_version: Literal[1] = 1
    players: list[PlayerEntry]
