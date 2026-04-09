"""
Natural-language → DuckDB SQL for NFL PBP (Microscope track / OpenAI proxy).
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

import polars as pl
from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from api.deps import get_openai_client, get_player_index_df, get_settings_dep
from core.config import AppSettings
from nlq_common import load_manifest, normalize_and_validate_select
from prompts import microscope_nfl_system_prompt
from services.nlq_sql_guard import (
    enforce_entity_id_filter,
    enforce_player_labels_in_results,
    reject_hallucinated_gsis_ids_when_no_entities,
)
from services.openai_client import openai_chat_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nlq/microscope", tags=["nlq"])


def load_microscope_manifest() -> dict[str, Any]:
    return load_manifest("microscope_nfl_pbp.json")


def normalize_and_validate_microscope_sql(raw: str, *, primary_view: str) -> str:
    """Backwards-compat wrapper (prefer nlq_common.normalize_and_validate_select)."""
    return normalize_and_validate_select(raw, required_relation=primary_view)


class MicroscopeEntity(BaseModel):
    gsis_id: str = Field(..., description="NFL GSIS player id string")
    display_name: str


class NlqMicroscopeRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    entities: list[MicroscopeEntity] = Field(default_factory=list)


class NlqMicroscopeResponse(BaseModel):
    sql: str


class PlayerDictionaryRow(BaseModel):
    search_key: str
    gsis_id: str
    display_name: str


@router.get("/player-dictionary", response_model=list[PlayerDictionaryRow])
async def microscope_player_dictionary(
    df: Annotated[pl.DataFrame, Depends(get_player_index_df)],
) -> list[PlayerDictionaryRow]:
    if df.height == 0:
        raise HTTPException(
            status_code=503,
            detail="Player index not loaded. Seed player_index.parquet (local) or set PLAYER_INDEX_URL (R2) and restart.",
        )
    need = {"gsis_id", "full_name"}
    if not need.issubset(set(df.columns)):
        raise HTTPException(
            status_code=503,
            detail="Player index is missing gsis_id or full_name columns.",
        )
    out: list[PlayerDictionaryRow] = []
    for row in df.select(["gsis_id", "full_name"]).iter_rows(named=True):
        gsis = str(row["gsis_id"]).strip() if row["gsis_id"] is not None else ""
        name = (row["full_name"] or "") if row["full_name"] is not None else ""
        if not gsis:
            continue
        key = name.strip().lower()
        if not key:
            key = gsis
        out.append(PlayerDictionaryRow(search_key=key, gsis_id=gsis, display_name=name.strip() or gsis))
    return out


@router.post("/sql", response_model=NlqMicroscopeResponse)
async def nlq_microscope_sql(
    req: NlqMicroscopeRequest,
    client: Annotated[AsyncOpenAI, Depends(get_openai_client)],
    settings: Annotated[AppSettings, Depends(get_settings_dep)],
) -> NlqMicroscopeResponse:
    try:
        manifest = load_microscope_manifest()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Microscope manifest not found. Add manifests/microscope_nfl_pbp.json. ({e})",
        ) from e

    primary_view = str(manifest.get("primary_view", "nfl_pbp_all"))
    system = microscope_nfl_system_prompt(manifest)
    entities_payload = json.dumps([e.model_dump() for e in req.entities], indent=2)
    user_content = (
        f"Question: {req.question}\n\n"
        f"Known entities (GSIS ids; use in passer/rusher/receiver filters when relevant):\n{entities_payload}"
    )

    raw = await openai_chat_text(
        client=client,
        model=settings.openai_model,
        system=system,
        user_content=user_content,
        max_tokens=1200,
    )

    if not raw:
        raise HTTPException(status_code=502, detail="Model returned empty output")

    try:
        sql = normalize_and_validate_select(raw, required_relation=primary_view)
    except ValueError as e:
        logger.warning("Microscope NLQ SQL validation failed: %s | raw=%r", e, raw[:500])
        raise HTTPException(
            status_code=422,
            detail=f"Model output was not valid safe SELECT SQL for {primary_view}.",
        ) from e

    player_id_slots = list(manifest.get("player_id_slots") or [])
    try:
        enforce_entity_id_filter(sql, entities=req.entities, player_id_slots=player_id_slots)
        reject_hallucinated_gsis_ids_when_no_entities(sql, entities=req.entities, player_id_slots=player_id_slots)
        enforce_player_labels_in_results(sql, player_id_slots=player_id_slots)
    except ValueError as e:
        logger.warning("Microscope NLQ post-validation failed: %s | sql=%r", e, sql[:500])
        raise HTTPException(status_code=422, detail=str(e)) from e

    return NlqMicroscopeResponse(sql=sql)
