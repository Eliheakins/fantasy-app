"""Season tables (odds, rankings, grades, luck) and the digest."""

import logging
from typing import Any

import polars as pl
from fastapi import APIRouter

from fantasy import _view as view
from fantasy import data_api
from fantasy.api_deps import Ctx, RequestContext
from fantasy.api_envelope import NO_DATA_MESSAGE, fail, guarded, ok, rows
from fantasy.api_models import (
    BracketData,
    DigestData,
    Envelope,
    LuckRow,
    ManagerGradeRow,
    OddsHistoryRow,
    PowerRankingRow,
    SeasonEventRow,
    SeedRow,
    TeamGradeRow,
    WhatIfRow,
    WinNeedRow,
)
from fantasy.api_routes.common import Week, known_league

log = logging.getLogger(__name__)
router = APIRouter()
IDEA_STAMPS = frozenset({"league_id", "created_at", "as_of_week"})  # in `ideas`, not per row


@router.get("/leagues/{league}/seeds", response_model=Envelope[list[SeedRow]])
def seeds(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: rows(data_api.seed_distribution(league, ctx.data_dir, ctx.team)))


@router.get("/leagues/{league}/bracket", response_model=Envelope[BracketData])
def bracket(league: str, ctx: Ctx) -> Any:
    """The winners bracket with each side's chance to win its round; no_data before it is set."""
    try:
        view = data_api.bracket(league, ctx.data_dir, ctx.team)
    except FileNotFoundError as err:
        log.warning("bracket %s: %s", league, err)
        return fail("no_data", NO_DATA_MESSAGE)
    except ValueError as err:
        return fail("invalid", str(err))
    return fail("no_data", view.message) if view.message else ok({"rounds": view.rounds})


@router.get("/leagues/{league}/odds-history", response_model=Envelope[list[OddsHistoryRow]])
def odds_history(league: str, ctx: Ctx) -> Any:
    """Every team's saved runs, oldest first."""
    return guarded(
        lambda: rows(data_api.odds_history(league, ctx.data_dir, ctx.team).sort("run_at"))
    )


@router.get("/leagues/{league}/power-rankings", response_model=Envelope[list[PowerRankingRow]])
def power_rankings(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: rows(data_api.power_rankings(league, ctx.data_dir, ctx.team)))


@router.get("/leagues/{league}/team-grades", response_model=Envelope[list[TeamGradeRow]])
def team_grades(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: rows(data_api.team_grades(league, ctx.data_dir, ctx.team)))


@router.get("/leagues/{league}/digest", response_model=Envelope[DigestData])
def digest(league: str, ctx: Ctx) -> Any:
    """Last week, projection misses, odds change and stored move ideas in one read."""
    return guarded(lambda: digest_data(league, ctx))


def watch_rows(league: str, ctx: RequestContext) -> list[dict[str, Any]]:
    """The drop-risk watch; empty, with the reason logged, when the league has no engine data."""
    try:
        return rows(data_api.watchlist(league, ctx.data_dir, ctx.team))
    except (ValueError, FileNotFoundError):
        log.warning("no drop-risk watch for %s", league, exc_info=True)
        return []


def digest_data(league: str, ctx: RequestContext) -> dict[str, Any]:
    d, team = ctx.data_dir, ctx.team
    if not known_league(league, d):
        raise ValueError(f"unknown league {league!r}")
    last = rows(data_api.last_week(league, d, team))
    waivers = rows(data_api.move_ideas(league, "waiver", d, team))
    trades = rows(data_api.move_ideas(league, "trade", d, team))
    stored = [*waivers, *trades]
    week = rows(data_api.leagues(d).filter(pl.col("league_key") == league))[0]["current_week"]
    deadline = view.trade_deadline(league, d)

    def shown(ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{k: v for k, v in r.items() if k not in IDEA_STAMPS} for r in ideas]

    return {
        "last_week": last[0] if last else None,
        "performance": rows(data_api.player_vs_projection(league, 0, d, team)),
        "watch": watch_rows(league, ctx),
        "odds_change": rows(data_api.odds_change(league, d, team)),
        "waivers": shown(waivers),
        "trades": shown(trades),
        "ideas": {
            "is_mine": data_api.ideas_are_mine(league, d, team),
            "created_at": stored[0]["created_at"] if stored else None,
            "as_of_week": stored[0]["as_of_week"] if stored else None,
            "current_week": week,
            "trade_deadline": deadline,
            "deadline_passed": deadline is not None and week is not None and week > deadline,
        },
    }


@router.get("/leagues/{league}/luck", response_model=Envelope[list[LuckRow]])
def luck(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: rows(data_api.luck(league, ctx.data_dir, ctx.team)))


@router.get("/leagues/{league}/manager-grades", response_model=Envelope[list[ManagerGradeRow]])
def manager_grades(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: rows(data_api.manager_grades(league, ctx.data_dir, ctx.team)))


@router.get("/leagues/{league}/win-needs", response_model=Envelope[list[WinNeedRow]])
def win_needs(league: str, ctx: Ctx) -> Any:
    """Playoff odds by wins in the next four games (empty until simulate has run)."""
    return guarded(lambda: rows(data_api.win_needs(league, ctx.data_dir, ctx.team)))


@router.get("/leagues/{league}/season-events", response_model=Envelope[list[SeasonEventRow]])
def season_events(league: str, ctx: Ctx) -> Any:
    """Annotations for the season-odds chart, oldest first."""
    return guarded(lambda: rows(data_api.season_events(league, ctx.data_dir, ctx.team)))


@router.get("/leagues/{league}/what-if", response_model=Envelope[list[WhatIfRow]])
def what_if(league: str, ctx: Ctx, week: Week = 0) -> Any:
    return guarded(lambda: rows(data_api.what_if(league, week, ctx.data_dir, ctx.team)))
