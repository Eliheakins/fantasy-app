"""
Natural-language → DuckDB SQL for `gold_unified_performance` (OpenAI proxy).
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from api.deps import get_openai_client, get_settings_dep
from core.config import AppSettings
from nlq_common import load_manifest, normalize_and_validate_select
from prompts import telescope_system_prompt
from services.openai_client import openai_chat_text

logger = logging.getLogger(__name__)

router = APIRouter()


def load_gold_manifest() -> dict[str, Any]:
    return load_manifest("gold_unified_performance.json")


class NlqEntity(BaseModel):
    bridge_id: int = Field(..., description="Rosetta player_hub bridge_id")
    display_name: str


class NlqRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    entities: list[NlqEntity] = Field(default_factory=list)


class NlqResponse(BaseModel):
    sql: str


@router.post("/nlq", response_model=NlqResponse)
async def nlq_translate(
    req: NlqRequest,
    client: Annotated[AsyncOpenAI, Depends(get_openai_client)],
    settings: Annotated[AppSettings, Depends(get_settings_dep)],
) -> NlqResponse:
    try:
        manifest = load_gold_manifest()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Gold manifest not found. Run the Rosetta pipeline. ({e})",
        ) from e

    system = telescope_system_prompt(manifest)
    entities_payload = json.dumps([e.model_dump() for e in req.entities], indent=2)
    user_content = (
        f"Question: {req.question}\n\n"
        f"Known entities (use bridge_id IN (...) when non-empty):\n{entities_payload}"
    )

    raw = await openai_chat_text(
        client=client,
        model=settings.openai_model,
        system=system,
        user_content=user_content,
        max_tokens=800,
    )

    if not raw:
        raise HTTPException(status_code=502, detail="Model returned empty output")

    try:
        sql = normalize_and_validate_select(raw, required_relation="gold_unified_performance")
    except ValueError as e:
        logger.warning("NLQ SQL validation failed: %s | raw=%r", e, raw[:500])
        raise HTTPException(
            status_code=422,
            detail="Model output was not valid safe SELECT SQL for gold_unified_performance.",
        ) from e

    return NlqResponse(sql=sql)
