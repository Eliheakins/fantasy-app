"""League list, roster, teams and season odds."""

from typing import Any

from fastapi import APIRouter, Request

from fantasy import _view as view
from fantasy import data_api
from fantasy.api_deps import Ctx, DataDir
from fantasy.api_envelope import guarded, rows
from fantasy.api_models import (
    Envelope,
    LeagueRow,
    RosterRow,
    SeasonOddsRow,
    TeamRow,
    UnmatchedData,
)
from fantasy.auth import access

router = APIRouter()


@router.get("/leagues", response_model=Envelope[list[LeagueRow]])
def leagues(request: Request, data_dir: DataDir) -> Any:
    account = getattr(request.state, "account", None)

    def build() -> list[dict[str, Any]]:
        mine = access.only_visible(data_api.leagues(data_dir), account, data_dir)
        return [
            {
                **r,
                "record": view.record_string(r["wins"], r["losses"], r["ties"]),
                "trade_deadline": view.trade_deadline(r["league_key"], data_dir),
            }
            for r in rows(access.with_account_team(mine, account, data_dir))
        ]

    return guarded(build)


@router.get("/leagues/{league}/roster", response_model=Envelope[list[RosterRow]])
def roster(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: rows(data_api.roster(league, ctx.data_dir, ctx.team)))


@router.get("/unmatched", response_model=Envelope[UnmatchedData])
def unmatched(data_dir: DataDir) -> Any:
    def build() -> dict[str, Any]:
        names = view.unmatched_names(data_api.unmatched(data_dir))
        return {"count": len(names), "names": names}

    return guarded(build)


@router.get("/leagues/{league}/teams", response_model=Envelope[list[TeamRow]])
def teams(league: str, request: Request, data_dir: DataDir) -> Any:
    own = access.default_team(getattr(request.state, "account", None), league, data_dir)

    def build() -> list[dict[str, Any]]:
        return [
            {
                **r,
                "is_me": r["is_me"] if own is None else r["roster_id"] == own,
                "record": view.record_string(r["wins"], r["losses"], r["ties"]),
            }
            for r in rows(data_api.teams(league, data_dir))
        ]

    return guarded(build)


@router.get("/leagues/{league}/season-odds", response_model=Envelope[list[SeasonOddsRow]])
def season_odds(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: rows(data_api.season_odds(league, ctx.data_dir, ctx.team)))
