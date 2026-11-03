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
            detail=(
                "Player index not loaded. "
                "Run `uv run python backend/scripts/build_data.py` and restart the API."
            ),
        )
    return state.player_index


def get_nfl_pbp_shards(state: Annotated[AppState, Depends(get_app_state)]) -> list[PbpShard]:
    return list(state.pbp_shards)


def get_llm_client(state: Annotated[AppState, Depends(get_app_state)]) -> AsyncOpenAI:
    if state.llm_client is None:
        raise HTTPException(status_code=503, detail="LLM client is not initialized.")
    return state.llm_client
