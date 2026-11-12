"""Lineup, schedule, strength and streamer reads."""

from typing import Any, Literal

from fastapi import APIRouter

from fantasy import _view as view
from fantasy import data_api
from fantasy.api_deps import Ctx
from fantasy.api_envelope import guarded, rows
from fantasy.api_models import (
    Envelope,
    HoleRow,
    LineupRow,
    ScheduleRow,
    StashData,
    StreamerRow,
    StrengthRow,
)
from fantasy.api_routes.common import Week

router = APIRouter()


@router.get("/leagues/{league}/streamers", response_model=Envelope[list[StreamerRow]])
def streamers(league: str, ctx: Ctx, kind: Literal["K", "DEF"]) -> Any:
    return guarded(
        lambda: rows(data_api.streamers(league, kind, data_dir=ctx.data_dir, team=ctx.team))
    )


@router.get("/leagues/{league}/lineup", response_model=Envelope[list[LineupRow]])
def lineup(league: str, ctx: Ctx, week: Week = 0) -> Any:
    return guarded(
        lambda: rows(
            view.lineup_changes(data_api.lineup(league, week, data_dir=ctx.data_dir, team=ctx.team))
        )
    )


@router.get("/leagues/{league}/schedule", response_model=Envelope[list[ScheduleRow]])
def schedule(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: rows(data_api.schedule(league, ctx.data_dir, ctx.team)))


@router.get("/leagues/{league}/strength", response_model=Envelope[list[StrengthRow]])
def strength(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: rows(data_api.position_strength(league, ctx.data_dir, ctx.team)))


@router.get("/leagues/{league}/holes", response_model=Envelope[list[HoleRow]])
def holes(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: data_api.holes(league, ctx.data_dir, ctx.team))


@router.get("/leagues/{league}/stash", response_model=Envelope[StashData])
def stash(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: data_api.stash(league, ctx.data_dir, ctx.team))
