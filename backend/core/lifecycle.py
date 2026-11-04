from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from openai import AsyncOpenAI

from core.config import get_settings
from core.manifest_state import refresh_manifest
from core.state import app_state
from services.llm_warmup import keep_model_warm

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # A bad or unreadable manifest must not stop the API; /health then reports no freshness.
    refresh_manifest(app_state, settings.data_dir)

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
