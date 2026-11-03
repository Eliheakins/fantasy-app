from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from openai import AsyncOpenAI

from core.config import get_settings
from core.state import app_state
from services.llm_warmup import keep_model_warm
from services.player_catalog import load_player_index_from_path
from services.shard_catalog import discover_nfl_pbp_shards_local


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    if settings.player_index_path.is_file():
        app_state.player_index = load_player_index_from_path(settings.player_index_path)
        app_state.pbp_shards = discover_nfl_pbp_shards_local(settings.data_dir)
    else:
        app_state.player_index = None
        app_state.pbp_shards = []

    # Local servers ignore the key, but the SDK requires a non-empty one.
    app_state.llm_client = AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key="local",
        timeout=settings.llm_timeout_seconds,
    )

    warm_task = asyncio.create_task(keep_model_warm(app_state.llm_client, settings.llm_model))

    yield

    warm_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await warm_task
    await app_state.llm_client.close()
    app_state.llm_client = None
