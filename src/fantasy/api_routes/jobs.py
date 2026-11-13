"""Simulations as jobs: win probability, actions, waivers and trades."""

import threading
from dataclasses import asdict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query

from fantasy import _view as view
from fantasy import data_api
from fantasy.api_deps import Ctx, RequestContext
from fantasy.api_envelope import clean_rows, fail, guarded, rows
from fantasy.api_models import (
    ActionRow,
    Envelope,
    FoundTradeRow,
    TradeEvaluation,
    TradeRequest,
    WaiverRow,
    WinProbabilityData,
)
from fantasy.api_routes.common import BUSY_MESSAGE, Runner, Week, run_job

router = APIRouter()
JOB_RESPONSES: dict[int | str, dict[str, Any]] = {
    202: {"description": "The job is running: envelope with status running and started_at"}
}
MAX_TRADE_EVALUATIONS = 2
TRADE_SLOTS = threading.BoundedSemaphore(MAX_TRADE_EVALUATIONS)


def _playoff_label(league: str, week: int, ctx: RequestContext) -> str | None:
    me = data_api.my_league(league, ctx.data_dir, ctx.team)
    if me is None:
        return None
    week = week or int(me["current_week"])
    return data_api.playoff_status(league, int(me["roster_id"]), week, ctx.data_dir)


def win_probability_data(league: str, week: int, ctx: RequestContext) -> dict[str, Any]:
    lineup_rows = data_api.lineup(league, week, data_dir=ctx.data_dir, team=ctx.team)
    odds = data_api.win_probability(league, week, data_dir=ctx.data_dir, team=ctx.team)
    label = _playoff_label(league, week, ctx)
    if lineup_rows.is_empty():
        return {
            "playoff_label": label, "script": None, "swap": None, "comparison": [], "options": [],
            "lineups": {}, "summaries": {},
        }  # fmt: skip
    swap = view.swap_note(lineup_rows, odds)
    return {
        "playoff_label": label,
        "script": None if odds.is_empty() else odds["script"][0],
        "swap": None if swap is None else asdict(swap),
        "comparison": [] if odds.is_empty() else rows(view.comparison(odds)),
        "options": rows(odds),
        "lineups": {
            o: rows(view.lineup_changes(view.reslot(lineup_rows, odds, o))) for o in view.OBJECTIVES
        },
        "summaries": {
            o: asdict(view.lineup_summary(lineup_rows, odds, o)) for o in view.OBJECTIVES
        },
    }


@router.get(
    "/leagues/{league}/win-probability",
    response_model=Envelope[WinProbabilityData],
    responses=JOB_RESPONSES,
)
def win_probability(league: str, ctx: Ctx, runner: Runner, week: Week = 0) -> Any:
    def build() -> dict[str, Any]:
        return win_probability_data(league, week, ctx)

    return run_job(runner, "win-probability", (league, week), build, ctx)


@router.get(
    "/leagues/{league}/actions", response_model=Envelope[list[ActionRow]], responses=JOB_RESPONSES
)
def actions(
    league: str,
    ctx: Ctx,
    runner: Runner,
    stored_adds: Annotated[
        bool, Query(description="Use the digest's stored waiver ideas instead of re-simulating")
    ] = False,
) -> Any:
    return run_job(
        runner,
        "actions",
        (league, stored_adds),
        lambda: actions_data(league, stored_adds, ctx),
        ctx,
    )


def actions_data(league: str, stored_adds: bool, ctx: RequestContext) -> list[dict[str, Any]]:
    d, team = ctx.data_dir, ctx.team
    adds = data_api.stored_adds(league, d, team) if stored_adds else None
    found = data_api.actions(league, adds=adds, data_dir=d, team=team)
    needs_odds = "Win probability" in found["kind"].to_list()
    odds = data_api.win_probability(league, data_dir=d, team=team) if needs_odds else None
    return clean_rows(view.action_fields(found, odds))


@router.get(
    "/leagues/{league}/waivers", response_model=Envelope[list[WaiverRow]], responses=JOB_RESPONSES
)
def waivers(
    league: str, ctx: Ctx, runner: Runner, horizon: Literal["ros", "playoffs"] = "ros"
) -> Any:
    def build() -> list[dict[str, Any]]:
        return rows(data_api.waivers(league, horizon=horizon, data_dir=ctx.data_dir, team=ctx.team))

    return run_job(runner, "waivers", (league, horizon), build, ctx)


@router.post("/leagues/{league}/trades/evaluate", response_model=Envelope[TradeEvaluation])
def evaluate_trade(league: str, trade: TradeRequest, ctx: Ctx) -> Any:
    """Odds before and after plus the automatic roster moves, in one response."""

    def build() -> dict[str, Any]:
        args = (league, trade.partner_roster_id, trade.give_ids, trade.get_ids)
        odds = data_api.evaluate_trade(*args, ctx.data_dir, ctx.team)
        changes = data_api.trade_roster_changes(*args, ctx.data_dir, ctx.team)
        return {
            "odds": rows(odds),
            "roster_changes": rows(changes),
            "warning": view.roster_moves_warning(changes),
            "trade_deadline": view.trade_deadline(league, ctx.data_dir),
            "market": data_api.trade_market(
                league, [(trade.give_ids, trade.get_ids)], ctx.data_dir
            )[0],
        }

    if not TRADE_SLOTS.acquire(blocking=False):
        return fail("busy", BUSY_MESSAGE)
    try:
        return guarded(build)
    finally:
        TRADE_SLOTS.release()


@router.post(
    "/leagues/{league}/trades/find",
    response_model=Envelope[list[FoundTradeRow]],
    responses=JOB_RESPONSES,
)
def find_trades(league: str, ctx: Ctx, runner: Runner) -> Any:
    """A long job (minutes): POST again to poll, same as the GET jobs."""
    return run_job(runner, "find-trades", (league,), lambda: found_trades_data(league, ctx), ctx)


def found_trades_data(league: str, ctx: RequestContext) -> list[dict[str, Any]]:
    found = rows(data_api.find_trades(league, ctx.data_dir, ctx.team))
    pairs = [(r["give_ids"], r["get_ids"]) for r in found]
    markets = data_api.trade_market(league, pairs, ctx.data_dir)
    return [{**r, "market": m} for r, m in zip(found, markets, strict=True)]
