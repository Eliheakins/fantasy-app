from __future__ import annotations

from typing import Annotated

import polars as pl
from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_nfl_pbp_shards, get_player_index_df
from schemas.api import PbpShard, PlayerDetailResponse, PlayerRecord
from services.player_catalog import get_player_row, search_players_by_name

router = APIRouter(tags=["players"])


@router.get("/search", response_model=list[PlayerRecord])
async def search_players(
    q: Annotated[str, Query(description="Substring to match against full_name (case-insensitive)")],
    df: Annotated[pl.DataFrame, Depends(get_player_index_df)],
) -> list[PlayerRecord]:
    return search_players_by_name(df, q, limit=10)


@router.get("/player/{gsis_id}", response_model=PlayerDetailResponse)
async def get_player(
    gsis_id: str,
    df: Annotated[pl.DataFrame, Depends(get_player_index_df)],
    shards: Annotated[list[PbpShard], Depends(get_nfl_pbp_shards)],
) -> PlayerDetailResponse:
    player = get_player_row(df, gsis_id)
    if player is None:
        raise HTTPException(status_code=404, detail=f"Player not found for gsis_id={gsis_id!r}")
    return PlayerDetailResponse(player=player, shards=shards)
