"""The week calendar, game-day and injury-status reads."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request

from fantasy import data_api
from fantasy.api_deps import Ctx, DataDir
from fantasy.api_envelope import guarded, rows
from fantasy.api_models import (
    Envelope,
    GameDayData,
    StatusChangeRow,
    WeekCalendarData,
)
from fantasy.auth import access

router = APIRouter()


@router.get("/week-calendar", response_model=Envelope[WeekCalendarData])
def week_calendar(request: Request, data_dir: DataDir) -> Any:
    """Kickoffs of the current NFL week and each league's waiver clear day, for the week strip."""
    account = getattr(request.state, "account", None)

    def build() -> dict[str, Any]:
        data = data_api.week_calendar(data_dir)
        if account is None:
            return data
        keys = set(access.only_visible(data_api.leagues(data_dir), account, data_dir)["league_key"])
        return {**data, "waivers": [w for w in data["waivers"] if w["league_key"] in keys]}

    return guarded(build)


@router.get("/leagues/{league}/game-day", response_model=Envelope[GameDayData])
def game_day(league: str, ctx: Ctx) -> Any:
    """Win chance over the day (live ticks of the current week) and the numbers now."""
    return guarded(lambda: data_api.game_day(league, ctx.data_dir, ctx.team))


@router.get("/leagues/{league}/status-changes", response_model=Envelope[list[StatusChangeRow]])
def status_changes(
    league: str,
    ctx: Ctx,
    since: Annotated[
        datetime, Query(description="Compare with the last snapshot at or before this")
    ],
) -> Any:
    """Players on the roster whose injury status changed since a time (daily Sleeper snapshots)."""
    return guarded(lambda: rows(data_api.status_changes(league, since, ctx.data_dir, ctx.team)))
