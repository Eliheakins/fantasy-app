from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI

from api.deps import get_llm_client, get_settings_dep
from core.config import AppSettings
from schemas.nlq import IntentOutcome, IntentRequest
from services.nlq_intent import IntentError, translate_question

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nlq", tags=["nlq"])


@router.post("/intent", response_model=IntentOutcome)
async def nlq_intent(
    req: IntentRequest,
    client: Annotated[AsyncOpenAI, Depends(get_llm_client)],
    settings: Annotated[AppSettings, Depends(get_settings_dep)],
) -> IntentOutcome:
    try:
        return await translate_question(client=client, model=settings.llm_model, req=req)
    except IntentError as e:
        logger.warning("NLQ intent rejected after retry: %s | question=%r", e, req.question)
        raise HTTPException(
            status_code=422,
            detail="I couldn't turn that into a query. Try naming the stat and a season.",
        ) from e
