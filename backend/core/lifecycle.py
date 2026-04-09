from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from openai import AsyncOpenAI

from core.config import get_settings
from core.state import app_state
from services.player_catalog import load_player_index_from_path, load_player_index_from_url
from services.shard_catalog import (
    discover_cfb_pbp_shards_local,
    discover_cfb_pbp_shards_r2,
    discover_nfl_pbp_shards_local,
    discover_nfl_pbp_shards_r2,
    parse_int_csv_env,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app_state.data_source = settings.data_source.strip().lower() or "local"

    if app_state.data_source == "r2":
        index_url = settings.player_index_url.strip()
        if not index_url:
            raise RuntimeError("DATA_SOURCE=r2 requires PLAYER_INDEX_URL (HTTPS URL to player_index.parquet)")

        public_base = settings.public_pbp_base.strip()
        if not public_base:
            raise RuntimeError("DATA_SOURCE=r2 requires PUBLIC_PBP_BASE (HTTPS base URL for nfl_pbp_YYYY.parquet)")

        years = parse_int_csv_env(settings.pbp_years)
        if not years:
            raise RuntimeError(
                "DATA_SOURCE=r2 requires PBP_YEARS (comma-separated years, e.g. 2021,2022,2023,2024)"
            )

        app_state.player_index = load_player_index_from_url(index_url)
        app_state.pbp_shards = discover_nfl_pbp_shards_r2(public_base, years)

        cfb_public_base = settings.public_cfb_pbp_base.strip()
        cfb_years = parse_int_csv_env(settings.cfb_pbp_years)
        app_state.cfb_pbp_shards = (
            discover_cfb_pbp_shards_r2(cfb_public_base, cfb_years)
            if cfb_public_base and cfb_years
            else []
        )
    elif app_state.data_source == "local":
        index_path = (
            Path(settings.player_index_path.strip())
            if settings.player_index_path.strip()
            else settings.default_player_index_path
        )
        if index_path.is_file():
            app_state.player_index = load_player_index_from_path(index_path)
            app_state.pbp_shards = discover_nfl_pbp_shards_local(settings.data_dir)
            app_state.cfb_pbp_shards = discover_cfb_pbp_shards_local(settings.data_dir)
        else:
            app_state.player_index = None
            app_state.pbp_shards = []
            app_state.cfb_pbp_shards = []
    else:
        raise RuntimeError(f"Invalid DATA_SOURCE={app_state.data_source!r}; use 'local' or 'r2'")

    key = settings.openai_api_key.strip()
    if key:
        app_state.openai_client = AsyncOpenAI(
            api_key=key,
            timeout=settings.openai_timeout_seconds,
        )
    else:
        app_state.openai_client = None

    yield

    app_state.openai_client = None
