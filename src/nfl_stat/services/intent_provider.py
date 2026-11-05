"""Picks the model for Ask's intent step: Jev when configured, the local server otherwise or on a
Jev failure. If the local server is down too, its 503 reaches the client, whose rules-first path
still answers what it can."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from nfl_stat.core.config import AppSettings
from nfl_stat.schemas.nlq import IntentOutcome, IntentRequest
from nfl_stat.services.jev_intent import JevError, translate_with_jev
from nfl_stat.services.nlq_intent import translate_question

logger = logging.getLogger(__name__)


async def answer_intent(
    req: IntentRequest, *, settings: AppSettings, llm_client: AsyncOpenAI
) -> IntentOutcome:
    key = settings.jev_api_key.get_secret_value() if settings.jev_api_key else ""
    if settings.intent_provider != "local":
        if key:
            try:
                return await translate_with_jev(
                    req,
                    api_key=key,
                    model=settings.jev_model,
                    timeout=settings.jev_timeout_seconds,
                )
            except JevError as e:
                logger.warning("Jev failed (%s); falling back to the local model", e)
        elif settings.intent_provider == "jev":
            logger.warning("INTENT_PROVIDER=jev but JEV_API_KEY is not set; using the local model")
    return await translate_question(client=llm_client, model=settings.llm_model, req=req)
