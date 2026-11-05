from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI

from nfl_stat.api.deps import get_llm_client, get_settings_dep
from nfl_stat.core.config import AppSettings
from nfl_stat.schemas.nlq import IntentOutcome, IntentRequest
from nfl_stat.services.intent_provider import answer_intent
from nfl_stat.services.llm_client import ModelError, ModelTimeout, ModelUnavailable
from nfl_stat.services.nlq_intent import IntentError

logger = logging.getLogger(__name__)


def model_status(err: ModelError) -> int:
    if isinstance(err, ModelUnavailable):
        return 503
    return 504 if isinstance(err, ModelTimeout) else 502


router = APIRouter(prefix="/nlq", tags=["nlq"])


@router.post("/intent", response_model=IntentOutcome)
async def nlq_intent(
    req: IntentRequest,
    client: Annotated[AsyncOpenAI, Depends(get_llm_client)],
    settings: Annotated[AppSettings, Depends(get_settings_dep)],
) -> IntentOutcome:
    try:
        return await answer_intent(req, settings=settings, llm_client=client)
    except IntentError as e:
        logger.warning("NLQ intent rejected after retry: %s | question=%r", e, req.question)
        raise HTTPException(
            status_code=422,
            detail="I couldn't turn that into a query. Try naming the stat and a season.",
        ) from e
    except ModelError as e:
        raise HTTPException(status_code=model_status(e), detail=str(e)) from e
