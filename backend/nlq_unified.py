"""
Unified NLQ endpoint that routes to Telescope or Microscope.

- Uses a cheap classifier call (gpt-4o-mini) when heuristics are ambiguous.
- Then generates SQL using the same manifests/validators as the per-track endpoints.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from api.deps import get_openai_client, get_settings_dep
from core.config import AppSettings
from nlq_common import load_manifest, normalize_and_validate_select
from nlq_microscope import MicroscopeEntity
from prompts import (
    microscope_unified_system_prompt,
    nlq_classifier_system_prompt,
    telescope_system_prompt,
)
from services.nlq_sql_guard import (
    enforce_entity_id_filter,
    enforce_player_labels_in_results,
    reject_hallucinated_espn_ids_when_no_entities,
    reject_hallucinated_gsis_ids_when_no_entities,
)
from services.openai_client import openai_chat_text

router = APIRouter(prefix="/nlq", tags=["nlq"])


class UnifiedEntity(BaseModel):
    display_name: str
    bridge_id: int | None = Field(default=None, description="Telescope: player_hub bridge_id")
    nfl_gsis_id: str | None = Field(default=None, description="Microscope NFL: GSIS id")
    cfb_espn_id: str | None = Field(default=None, description="Microscope CFB: ESPN athlete id (string)")


class UnifiedNlqRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    entities: list[UnifiedEntity] = Field(default_factory=list)


class UnifiedNlqResponse(BaseModel):
    track: Literal["telescope", "microscope_nfl", "microscope_cfb"]
    sql: str


def _looks_like_microscope_question(q: str) -> bool:
    low = q.lower()
    pbp_keywords = [
        "play-by-play",
        "play by play",
        "down",
        "ydstogo",
        "yards to go",
        "third down",
        "3rd down",
        "red zone",
        "goal to go",
        "air yards",
        "yac",
        "yards after catch",
        "success rate",
        "on the field",
        "off the field",
        "targets",
        "target share",
        "routes",
        "yards per route",
        "yprr",
        "cpoe",
        "xpass",
        "wpa",
        "vegas wpa",
    ]
    return any(k in low for k in pbp_keywords)


def _looks_like_cfb_question(q: str) -> bool:
    low = q.lower()
    return any(k in low for k in ("cfb", "college", "ncaa", "fbs", "sec", "big ten", "acc", "big 12", "pac-12"))


async def classify_track(
    *,
    client: AsyncOpenAI,
    model: str,
    question: str,
    entities: list[UnifiedEntity],
) -> Literal["telescope", "microscope_nfl", "microscope_cfb"]:
    if _looks_like_microscope_question(question):
        if _looks_like_cfb_question(question):
            return "microscope_cfb"
        if any((e.cfb_espn_id and not e.nfl_gsis_id) for e in entities):
            return "microscope_cfb"
        return "microscope_nfl"

    raw = await openai_chat_text(
        client=client,
        model=model,
        system=nlq_classifier_system_prompt(),
        user_content=f"Question: {question}",
        max_tokens=10,
    )
    token = raw.strip().lower()
    if "microscope_cfb" in token:
        return "microscope_cfb"
    if "microscope_nfl" in token or token == "microscope":
        return "microscope_nfl"
    if "telescope" in token:
        return "telescope"
    if _looks_like_microscope_question(question):
        return "microscope_cfb" if _looks_like_cfb_question(question) else "microscope_nfl"
    return "telescope"


@router.post("/unified", response_model=UnifiedNlqResponse)
async def nlq_unified(
    req: UnifiedNlqRequest,
    client: Annotated[AsyncOpenAI, Depends(get_openai_client)],
    settings: Annotated[AppSettings, Depends(get_settings_dep)],
) -> UnifiedNlqResponse:
    track = await classify_track(
        client=client,
        model=settings.openai_model,
        question=req.question,
        entities=req.entities,
    )

    if track == "telescope":
        try:
            manifest = load_manifest("gold_unified_performance.json")
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Gold manifest not found. Run the Rosetta pipeline. ({e})",
            ) from e
        system = telescope_system_prompt(manifest)
        entities = [e for e in req.entities if e.bridge_id is not None]
        entities_payload = json.dumps(
            [{"bridge_id": e.bridge_id, "display_name": e.display_name} for e in entities],
            indent=2,
        )
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
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="Model output was not valid safe SELECT SQL for gold_unified_performance.",
            ) from None
        return UnifiedNlqResponse(track="telescope", sql=sql)

    try:
        if track == "microscope_cfb":
            manifest = load_manifest("microscope_cfb_pbp.json")
        else:
            manifest = load_manifest("microscope_nfl_pbp.json")
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Microscope manifest not found. Run the Rosetta pipeline. ({e})",
        ) from e
    primary_view = str(manifest.get("primary_view", "nfl_pbp_all"))
    system = microscope_unified_system_prompt(manifest)
    if track == "microscope_cfb":
        entities = [e for e in req.entities if e.cfb_espn_id]
        entities_payload = json.dumps(
            [{"espn_id": e.cfb_espn_id, "display_name": e.display_name} for e in entities],
            indent=2,
        )
    else:
        entities = [e for e in req.entities if e.nfl_gsis_id]
        entities_payload = json.dumps(
            [{"gsis_id": e.nfl_gsis_id, "display_name": e.display_name} for e in entities],
            indent=2,
        )
    user_content = (
        f"Question: {req.question}\n\n"
        f"Known entities (use ids in passer/rusher/receiver filters when relevant):\n{entities_payload}"
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
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Model output was not valid safe SELECT SQL for {primary_view}.",
        ) from None

    player_id_slots = list(manifest.get("player_id_slots") or [])
    if track == "microscope_cfb":
        guard_entities = [
            MicroscopeEntity(gsis_id=str(e.cfb_espn_id), display_name=e.display_name)
            for e in entities
            if e.cfb_espn_id
        ]
    else:
        guard_entities = [
            MicroscopeEntity(gsis_id=str(e.nfl_gsis_id), display_name=e.display_name)
            for e in entities
            if e.nfl_gsis_id
        ]
    try:
        enforce_entity_id_filter(sql, entities=guard_entities, player_id_slots=player_id_slots)
        if track == "microscope_cfb":
            reject_hallucinated_espn_ids_when_no_entities(
                sql, entities=guard_entities, player_id_slots=player_id_slots
            )
        else:
            reject_hallucinated_gsis_ids_when_no_entities(
                sql, entities=guard_entities, player_id_slots=player_id_slots
            )
        enforce_player_labels_in_results(sql, player_id_slots=player_id_slots)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return UnifiedNlqResponse(track=track, sql=sql)
