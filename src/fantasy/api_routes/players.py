"""Player pages: weeks, points, profile, outlook and owners."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from fastapi import Path as PathParam

from fantasy import data_api
from fantasy.api_deps import Ctx, DataDir
from fantasy.api_envelope import guarded, rows
from fantasy.api_models import (
    Envelope,
    OutlookRow,
    OwnersData,
    PlayerPointsRow,
    PlayerProfile,
    PlayerWeekRow,
)

router = APIRouter()
MAX_ID_LENGTH = 20  # nflverse ids are 10 characters (00-0012345)


@router.get("/leagues/{league}/player-weeks", response_model=Envelope[list[PlayerWeekRow]])
def player_weeks(
    league: str, ctx: Ctx, gsis_id: str, n: Annotated[int, Query(ge=1, le=18)] = 4
) -> Any:
    return guarded(lambda: rows(data_api.player_weeks(league, gsis_id, n, ctx.data_dir, ctx.team)))


@router.get("/leagues/{league}/player-points", response_model=Envelope[list[PlayerPointsRow]])
def player_points(
    league: str,
    data_dir: DataDir,
    season: Annotated[int, Query(ge=1999, le=2100)],
    gsis_id: str | None = None,
) -> Any:
    return guarded(lambda: rows(data_api.player_points(league, gsis_id, season, data_dir)))


@router.get("/leagues/{league}/players/{gsis_id}/profile", response_model=Envelope[PlayerProfile])
def player_profile(
    league: str,
    ctx: Ctx,
    gsis_id: Annotated[str, PathParam(max_length=MAX_ID_LENGTH, pattern=r"^[A-Za-z0-9_-]+$")],
) -> Any:
    return guarded(lambda: data_api.player_profile(league, gsis_id, ctx.data_dir, ctx.team))


@router.get("/leagues/{league}/outlook", response_model=Envelope[list[OutlookRow]])
def outlook(league: str, ctx: Ctx, scope: Literal["mine", "league", "free"] = "mine") -> Any:
    return guarded(lambda: rows(data_api.player_outlook(league, scope, ctx.data_dir, ctx.team)))


@router.get("/leagues/{league}/owners", response_model=Envelope[OwnersData])
def owners(league: str, ctx: Ctx) -> Any:
    def build() -> dict[str, Any]:
        return {
            "rows": rows(data_api.player_owners(league, ctx.data_dir, ctx.team)),
            "unmatched": data_api.rostered_unmatched(league, ctx.data_dir),
        }

    return guarded(build)
