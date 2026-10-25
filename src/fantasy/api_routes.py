"""Routes under /api. Instant reads and league-build reads run inline; simulations are jobs."""

import logging
import threading
from collections.abc import Callable
from dataclasses import asdict
from typing import Annotated, Any, Literal

import httpx
import polars as pl
from fastapi import APIRouter, Depends, Query, Request

from fantasy import _view as view
from fantasy import data_api, store
from fantasy._engine import _clear_league_cache, data_version, pinned_version, viewing_team
from fantasy.api_envelope import NO_DATA_MESSAGE, clean, fail, guarded, ok, rows, running
from fantasy.api_jobs import Busy, JobKey, JobRunner
from fantasy.api_models import (
    ActionRow,
    AssetRow,
    Envelope,
    FoundTradeRow,
    LeagueRow,
    LineupRow,
    LiveScoreRow,
    LuckRow,
    ManagerGradeRow,
    MarketValueRow,
    OddsHistoryRow,
    OutlookRow,
    PartnerRow,
    PlayerWeekRow,
    PowerRankingRow,
    RefreshData,
    RosterRow,
    ScheduleRow,
    SeasonOddsRow,
    SeedRow,
    StatusData,
    StreamerRow,
    StrengthRow,
    TeamGradeRow,
    TeamRow,
    TradeEvaluation,
    TradeRequest,
    UnmatchedData,
    WaiverRow,
    WhatIfRow,
    WinProbabilityData,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
JOB_RESPONSES: dict[int | str, dict[str, Any]] = {
    202: {"description": "The job is running: envelope with status running and started_at"}
}
BUSY_MESSAGE = "The server is busy. Try again in a moment."
MAX_TRADE_EVALUATIONS = 2
TRADE_SLOTS = threading.BoundedSemaphore(MAX_TRADE_EVALUATIONS)
REFRESH_LOCK = threading.Lock()
MAX_IDS_LENGTH = 4000
Team = Annotated[
    int | None, Query(description="Roster id to view as; omitted means my team (Sleeper is_me)")
]
Week = Annotated[int, Query(ge=0, le=22, description="0 means the current week")]


def get_runner(request: Request) -> JobRunner:
    runner: JobRunner = request.app.state.runner
    return runner


Runner = Annotated[JobRunner, Depends(get_runner)]


def as_team(team: int | None, fn: Callable[[], Any]) -> Callable[[], Any]:
    """`fn` run with `team` treated as my team (the real me when None)."""

    def run() -> Any:
        with viewing_team(team):
            return fn()

    return run


def known_league(league: str) -> bool:
    return league in data_api.leagues(store.DATA_DIR)["league_key"].to_list()


def run_job(
    runner: JobRunner,
    endpoint: str,
    args: tuple[Any, ...],
    fn: Callable[[], Any],
    team: int | None = None,
) -> Any:
    """Start the job once per (endpoint, args, team, data version); 202 until it has finished."""
    try:
        if not known_league(args[0]):
            return fail("invalid", f"unknown league {args[0]!r}")
    except FileNotFoundError:
        return fail("no_data", NO_DATA_MESSAGE)
    version = data_version()  # once: the key and the league build must agree
    key: JobKey = (endpoint, (*args, team), version)  # team is last: args[0] stays the league

    def pinned() -> Any:
        with pinned_version(version), viewing_team(team):  # a worker thread has no context
            return fn()

    try:
        job = runner.submit(key, pinned)
    except Busy:
        return fail("busy", BUSY_MESSAGE)
    if not job.future.done():
        return running(job.started_at)
    if job.future.exception() is not None:
        runner.forget(key)  # reported once, the next request retries
    return guarded(job.future.result)


# --- instant reads -------------------------------------------------------------------


@router.get("/status", response_model=Envelope[StatusData])
def status(request: Request) -> Any:
    def build() -> dict[str, Any]:
        return {
            "freshness": rows(data_api.freshness()),
            "missing_layers": data_api.missing_layers(store.DATA_DIR),
            "simulation_behind_inputs": data_api.simulation_behind_inputs(store.DATA_DIR),
            "data_version": data_version(),
            "live_refresh": request.app.state.live.status(),
        }

    return guarded(build)


@router.get("/leagues", response_model=Envelope[list[LeagueRow]])
def leagues() -> Any:
    def build() -> list[dict[str, Any]]:
        return [
            {
                **r,
                "record": view.record_string(r["wins"], r["losses"], r["ties"]),
                "trade_deadline": view.trade_deadline(r["league_key"], store.DATA_DIR),
            }
            for r in rows(data_api.leagues(store.DATA_DIR))
        ]

    return guarded(build)


@router.get("/leagues/{league}/roster", response_model=Envelope[list[RosterRow]])
def roster(league: str, team: Team = None) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.roster(league, store.DATA_DIR))))


@router.get("/unmatched", response_model=Envelope[UnmatchedData])
def unmatched() -> Any:
    def build() -> dict[str, Any]:
        names = view.unmatched_names(data_api.unmatched(store.DATA_DIR))
        return {"count": len(names), "names": names}

    return guarded(build)


@router.get("/leagues/{league}/teams", response_model=Envelope[list[TeamRow]])
def teams(league: str) -> Any:
    def build() -> list[dict[str, Any]]:
        return [
            {**r, "record": view.record_string(r["wins"], r["losses"], r["ties"])}
            for r in rows(data_api.teams(league, store.DATA_DIR))
        ]

    return guarded(build)


@router.get("/leagues/{league}/season-odds", response_model=Envelope[list[SeasonOddsRow]])
def season_odds(league: str, team: Team = None) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.season_odds(league, store.DATA_DIR))))


@router.get("/leagues/{league}/seeds", response_model=Envelope[list[SeedRow]])
def seeds(league: str, team: Team = None) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.seed_distribution(league))))


@router.get("/leagues/{league}/odds-history", response_model=Envelope[list[OddsHistoryRow]])
def odds_history(league: str, team: Team = None) -> Any:
    """Every team's saved runs, oldest first."""
    return guarded(
        as_team(team, lambda: rows(data_api.odds_history(league, store.DATA_DIR).sort("run_at")))
    )


@router.get("/leagues/{league}/power-rankings", response_model=Envelope[list[PowerRankingRow]])
def power_rankings(league: str, team: Team = None) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.power_rankings(league, store.DATA_DIR))))


@router.get("/leagues/{league}/team-grades", response_model=Envelope[list[TeamGradeRow]])
def team_grades(league: str, team: Team = None) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.team_grades(league, store.DATA_DIR))))


@router.get("/leagues/{league}/luck", response_model=Envelope[list[LuckRow]])
def luck(league: str, team: Team = None) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.luck(league, store.DATA_DIR))))


@router.get("/leagues/{league}/manager-grades", response_model=Envelope[list[ManagerGradeRow]])
def manager_grades(league: str, team: Team = None) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.manager_grades(league, store.DATA_DIR))))


@router.get("/leagues/{league}/what-if", response_model=Envelope[list[WhatIfRow]])
def what_if(league: str, week: Week = 0, team: Team = None) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.what_if(league, week, store.DATA_DIR))))


@router.get("/leagues/{league}/streamers", response_model=Envelope[list[StreamerRow]])
def streamers(league: str, kind: Literal["K", "DEF"], team: Team = None) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.streamers(league, kind))))


# --- league-build reads ----------------------------------------------------------------


@router.get("/leagues/{league}/lineup", response_model=Envelope[list[LineupRow]])
def lineup(league: str, week: Week = 0, team: Team = None) -> Any:
    return guarded(as_team(team, lambda: rows(view.lineup_changes(data_api.lineup(league, week)))))


@router.get("/leagues/{league}/schedule", response_model=Envelope[list[ScheduleRow]])
def schedule(league: str, team: Team = None) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.schedule(league))))


@router.get("/leagues/{league}/strength", response_model=Envelope[list[StrengthRow]])
def strength(league: str, team: Team = None) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.position_strength(league))))


@router.get("/leagues/{league}/live-score", response_model=Envelope[list[LiveScoreRow]])
def live_score(league: str, team: Team = None) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.live_score(league))))


@router.get("/leagues/{league}/trade-partners", response_model=Envelope[list[PartnerRow]])
def trade_partners(league: str, team: Team = None) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.trade_partners(league))))


@router.get("/leagues/{league}/trade-assets", response_model=Envelope[list[AssetRow]])
def trade_assets(league: str, roster_id: int | None = None, team: Team = None) -> Any:
    def build() -> list[dict[str, Any]]:
        assets = data_api.trade_assets(league, roster_id)
        labels = view.asset_labels(assets)
        label = pl.Series("label", [labels[g] for g in assets["gsis_id"]], dtype=pl.String)
        return rows(assets.with_columns(label))

    return guarded(as_team(team, build))


@router.get("/leagues/{league}/market-values", response_model=Envelope[list[MarketValueRow]])
def market_values(
    league: str,
    ids: Annotated[str, Query(max_length=MAX_IDS_LENGTH, description="comma-separated gsis ids")],
) -> Any:
    wanted = [i for i in ids.split(",") if i]
    return guarded(lambda: rows(data_api.market_values(league, wanted, store.DATA_DIR)))


@router.get("/leagues/{league}/player-weeks", response_model=Envelope[list[PlayerWeekRow]])
def player_weeks(
    league: str, gsis_id: str, n: Annotated[int, Query(ge=1, le=18)] = 4, team: Team = None
) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.player_weeks(league, gsis_id, n))))


@router.get("/leagues/{league}/outlook", response_model=Envelope[list[OutlookRow]])
def outlook(
    league: str, scope: Literal["mine", "league", "free"] = "mine", team: Team = None
) -> Any:
    return guarded(as_team(team, lambda: rows(data_api.player_outlook(league, scope))))


# --- simulations as jobs -----------------------------------------------------------------


def win_probability_data(league: str, week: int) -> dict[str, Any]:
    lineup_rows = data_api.lineup(league, week)
    odds = data_api.win_probability(league, week)
    if lineup_rows.is_empty():
        return {
            "script": None, "swap": None, "comparison": [], "options": [],
            "lineups": {}, "summaries": {},
        }  # fmt: skip
    swap = view.swap_note(lineup_rows, odds)
    return {
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
def win_probability(league: str, runner: Runner, week: Week = 0, team: Team = None) -> Any:
    return run_job(
        runner, "win-probability", (league, week), lambda: win_probability_data(league, week), team
    )


@router.get(
    "/leagues/{league}/actions", response_model=Envelope[list[ActionRow]], responses=JOB_RESPONSES
)
def actions(league: str, runner: Runner, team: Team = None) -> Any:
    return run_job(runner, "actions", (league,), lambda: actions_data(league), team)


def actions_data(league: str) -> list[dict[str, Any]]:
    found = data_api.actions(league)
    needs_odds = "Win probability" in found["kind"].to_list()
    odds = data_api.win_probability(league) if needs_odds else None
    return clean(view.action_fields(found, odds))


@router.get(
    "/leagues/{league}/waivers", response_model=Envelope[list[WaiverRow]], responses=JOB_RESPONSES
)
def waivers(league: str, runner: Runner, team: Team = None) -> Any:
    return run_job(runner, "waivers", (league,), lambda: rows(data_api.waivers(league)), team)


@router.post("/leagues/{league}/trades/evaluate", response_model=Envelope[TradeEvaluation])
def evaluate_trade(league: str, trade: TradeRequest, team: Team = None) -> Any:
    """Odds before and after plus the automatic roster moves, in one response."""

    def build() -> dict[str, Any]:
        args = (league, trade.partner_roster_id, trade.give_ids, trade.get_ids)
        odds = data_api.evaluate_trade(*args)
        changes = data_api.trade_roster_changes(*args)
        return {
            "odds": rows(odds),
            "roster_changes": rows(changes),
            "warning": view.roster_moves_warning(changes),
            "trade_deadline": view.trade_deadline(league, store.DATA_DIR),
        }

    if not TRADE_SLOTS.acquire(blocking=False):
        return fail("busy", BUSY_MESSAGE)
    try:
        return guarded(as_team(team, build))
    finally:
        TRADE_SLOTS.release()


@router.post(
    "/leagues/{league}/trades/find",
    response_model=Envelope[list[FoundTradeRow]],
    responses=JOB_RESPONSES,
)
def find_trades(league: str, runner: Runner, team: Team = None) -> Any:
    """A long job (minutes): POST again to poll, same as the GET jobs."""
    return run_job(
        runner, "find-trades", (league,), lambda: rows(data_api.find_trades(league)), team
    )


@router.post("/live/refresh", response_model=Envelope[RefreshData])
def refresh_live(runner: Runner) -> Any:
    """Pull this week's matchups from Sleeper, then drop every cache."""
    if not REFRESH_LOCK.acquire(blocking=False):
        return fail("busy", BUSY_MESSAGE)
    try:
        player_rows = data_api.refresh_live()
    except (OSError, httpx.HTTPError):
        log.exception("live refresh failed")
        return fail("server", "Sleeper refresh failed. See the server log.")
    finally:
        REFRESH_LOCK.release()
    _clear_league_cache()
    runner.clear()
    return ok({"player_rows": player_rows})
