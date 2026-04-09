from __future__ import annotations

from typing import Annotated

import polars as pl
from fastapi import Depends, HTTPException
from openai import AsyncOpenAI

from core.config import AppSettings, get_settings
from core.state import AppState, app_state
from schemas.api import PbpShard


def get_app_state() -> AppState:
    return app_state


def get_settings_dep() -> AppSettings:
    return get_settings()


def get_player_index_df(
    state: Annotated[AppState, Depends(get_app_state)],
) -> pl.DataFrame:
    if state.player_index is None:
        raise HTTPException(
            status_code=503,
            detail="Player index not loaded. Seed data (e.g. python scripts/build_data.py with DATA_LOCAL_DIR) and restart the service.",
        )
    return state.player_index


def get_nfl_pbp_shards(state: Annotated[AppState, Depends(get_app_state)]) -> list[PbpShard]:
    return list(state.pbp_shards)


def get_cfb_pbp_shards(state: Annotated[AppState, Depends(get_app_state)]) -> list[PbpShard]:
    return list(state.cfb_pbp_shards)


def get_openai_client(
    state: Annotated[AppState, Depends(get_app_state)],
    settings: Annotated[AppSettings, Depends(get_settings_dep)],
) -> AsyncOpenAI:
    if not settings.openai_api_key.strip():
        raise HTTPException(
            status_code=503,
            detail="NLQ is not configured: set OPENAI_API_KEY on the API service.",
        )
    if state.openai_client is None:
        raise HTTPException(
            status_code=503,
            detail="OpenAI client is not initialized.",
        )
    return state.openai_client
