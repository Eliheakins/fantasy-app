"""Routes under /api. Instant reads and league-build reads run inline; simulations are jobs."""

import logging
import threading
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import polars as pl
from fastapi import APIRouter, Depends, Query, Request
from fastapi import Path as PathParam

from fantasy import _live, data_api, refresh_queue, store
from fantasy import _view as view
from fantasy._lock import PipelineBusy, pipeline_lock
from fantasy.api_deps import Ctx, DataDir, RequestContext
from fantasy.api_envelope import NO_DATA_MESSAGE, clean, fail, guarded, ok, rows, running
from fantasy.api_jobs import Busy, JobKey, JobRunner
from fantasy.api_models import (
    ActionRow,
    AssetRow,
    DigestData,
    Envelope,
    FoundTradeRow,
    GameDayData,
    LeagueRow,
    LineupRow,
    LiveScoreRow,
    LuckRow,
    ManagerGradeRow,
    MarketValueRow,
    OddsHistoryRow,
    OutlookRow,
    OwnersData,
    PartnerRow,
    PlayerPointsRow,
    PlayerProfile,
    PlayerWeekRow,
    PowerRankingRow,
    RefreshData,
    RefreshStatus,
    RosterRow,
    ScheduleRow,
    ScoreboardRow,
    ScorecardData,
    SeasonEventRow,
    SeasonOddsRow,
    SeedRow,
    StatusChangeRow,
    StatusData,
    StreamerRow,
    StrengthRow,
    TeamGradeRow,
    TeamRow,
    TradeEvaluation,
    TradeRequest,
    UnmatchedData,
    WaiverRow,
    WeekCalendarData,
    WhatIfRow,
    WinNeedRow,
    WinProbabilityData,
)
from fantasy.auth import access
from fantasy.data_api import clear_league_cache, data_version, pinned_version
from fantasy.sources.sleeper import SleeperError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
JOB_RESPONSES: dict[int | str, dict[str, Any]] = {
    202: {"description": "The job is running: envelope with status running and started_at"}
}
BUSY_MESSAGE = "The server is busy. Try again in a moment."
MAX_TRADE_EVALUATIONS = 2
TRADE_SLOTS = threading.BoundedSemaphore(MAX_TRADE_EVALUATIONS)
MAX_IDS_LENGTH = 4000
MAX_ID_LENGTH = 20  # nflverse ids are 10 characters (00-0012345)
IDEA_STAMPS = frozenset({"league_id", "created_at", "as_of_week"})  # in `ideas`, not per row
Week = Annotated[int, Query(ge=0, le=22, description="0 means the current week")]


def get_runner(request: Request) -> JobRunner:
    runner: JobRunner = request.app.state.runner
    return runner


Runner = Annotated[JobRunner, Depends(get_runner)]


def known_league(league: str, data_dir: Path) -> bool:
    try:  # the keys alone: no join with league_teams, no scoring JSON
        return league in store.read_table("leagues", "raw", data_dir)["league_key"].to_list()
    except FileNotFoundError:
        return False


def run_job(
    runner: JobRunner,
    endpoint: str,
    args: tuple[Any, ...],
    fn: Callable[[], Any],
    ctx: RequestContext,
) -> Any:
    """Start the job once per (endpoint, args, team, data version); 202 until it has finished."""
    try:
        if not known_league(args[0], ctx.data_dir):
            return fail("invalid", f"unknown league {args[0]!r}")
    except FileNotFoundError:
        return fail("no_data", NO_DATA_MESSAGE)
    version = data_version(ctx.data_dir)  # once: the key and the league build must agree
    key: JobKey = (endpoint, (*args, ctx.team), version)  # team is last: args[0] stays the league

    def pinned() -> Any:
        with pinned_version(version):  # a worker thread has no context
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
def status(request: Request, data_dir: DataDir) -> Any:
    def build() -> dict[str, Any]:
        return {
            "freshness": rows(data_api.freshness(data_dir=data_dir)),
            "missing_layers": data_api.missing_layers(data_dir),
            "simulation_behind_inputs": data_api.simulation_behind_inputs(data_dir),
            "refresh_runs": rows(data_api.refresh_runs(data_dir)),
            "data_version": data_version(data_dir),
            "live_refresh": request.app.state.live.status(),
        }

    return guarded(build)


@router.get("/refresh/status", response_model=Envelope[RefreshStatus])
def refresh_status(data_dir: DataDir) -> Any:
    """Whether a refresh is queued or running, and how the last one went."""
    return guarded(lambda: refresh_queue.status(data_dir))


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


@router.get("/leagues/{league}/seeds", response_model=Envelope[list[SeedRow]])
def seeds(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: rows(data_api.seed_distribution(league, ctx.data_dir, ctx.team)))


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


@router.get("/leagues/{league}/streamers", response_model=Envelope[list[StreamerRow]])
def streamers(league: str, ctx: Ctx, kind: Literal["K", "DEF"]) -> Any:
    return guarded(
        lambda: rows(data_api.streamers(league, kind, data_dir=ctx.data_dir, team=ctx.team))
    )


# --- league-build reads ----------------------------------------------------------------


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


@router.get("/leagues/{league}/live-score", response_model=Envelope[list[LiveScoreRow]])
def live_score(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: rows(data_api.live_score(league, ctx.data_dir, ctx.team)))


def scoreboard_data(league: str, week: int, ctx: RequestContext) -> list[dict[str, Any]]:
    board = data_api.scoreboard(league, week, data_dir=ctx.data_dir, team=ctx.team)
    return clean(view.scoreboard_rows(board))


@router.get("/leagues/{league}/scoreboard", response_model=Envelope[list[ScoreboardRow]])
def scoreboard(league: str, ctx: Ctx, week: Week = 0) -> Any:
    """Every matchup of a week, my (or the viewed) team first. About 0.5 s, so not a job."""
    return guarded(lambda: scoreboard_data(league, week, ctx))


@router.get("/leagues/{league}/scorecard", response_model=Envelope[ScorecardData])
def scorecard(league: str, data_dir: DataDir) -> Any:
    """Archived pre-kickoff projections against actual points. An instant read of parquet."""

    def build() -> dict[str, Any]:
        card = data_api.scorecard(league, data_dir)
        return {
            "rows": rows(card.rows),
            "excluded": card.excluded,
            "weeks_archived": card.weeks_archived,
            "weeks_scored": card.weeks_scored,
            "has_quantiles": card.has_quantiles,
            "sleeper_first_fetch": card.sleeper_first_fetch,
        }

    return guarded(build)


@router.get("/leagues/{league}/trade-partners", response_model=Envelope[list[PartnerRow]])
def trade_partners(league: str, ctx: Ctx) -> Any:
    return guarded(lambda: rows(data_api.trade_partners(league, ctx.data_dir, ctx.team)))


@router.get("/leagues/{league}/trade-assets", response_model=Envelope[list[AssetRow]])
def trade_assets(league: str, ctx: Ctx, roster_id: int | None = None) -> Any:
    def build() -> list[dict[str, Any]]:
        assets = data_api.trade_assets(league, roster_id, ctx.data_dir, ctx.team)
        labels = view.asset_labels(assets)
        label = pl.Series("label", [labels[g] for g in assets["gsis_id"]], dtype=pl.String)
        return rows(assets.with_columns(label))

    return guarded(build)


@router.get("/leagues/{league}/market-values", response_model=Envelope[list[MarketValueRow]])
def market_values(
    league: str,
    data_dir: DataDir,
    ids: Annotated[str, Query(max_length=MAX_IDS_LENGTH, description="comma-separated gsis ids")],
) -> Any:
    wanted = [i for i in ids.split(",") if i]
    return guarded(lambda: rows(data_api.market_values(league, wanted, data_dir)))


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
            "unmatched": data_api.rostered_unmatched(league, ctx.data_dir, ctx.team),
        }

    return guarded(build)


# --- simulations as jobs -----------------------------------------------------------------


def win_probability_data(league: str, week: int, ctx: RequestContext) -> dict[str, Any]:
    lineup_rows = data_api.lineup(league, week, data_dir=ctx.data_dir, team=ctx.team)
    odds = data_api.win_probability(league, week, data_dir=ctx.data_dir, team=ctx.team)
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
    return clean(view.action_fields(found, odds))


@router.get(
    "/leagues/{league}/waivers", response_model=Envelope[list[WaiverRow]], responses=JOB_RESPONSES
)
def waivers(league: str, ctx: Ctx, runner: Runner) -> Any:
    def build() -> list[dict[str, Any]]:
        return rows(data_api.waivers(league, data_dir=ctx.data_dir, team=ctx.team))

    return run_job(runner, "waivers", (league,), build, ctx)


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


@router.post("/live/refresh", response_model=Envelope[RefreshData])
def refresh_live(runner: Runner, data_dir: DataDir) -> Any:
    """Pull this week's matchups from Sleeper, then drop every cache."""
    try:
        with pipeline_lock(data_dir, blocking=False):
            player_rows = _live.refresh_live(data_dir)
            _live.record_live_tick(data_dir=data_dir)  # the league cache follows data_version
    except PipelineBusy:
        return fail("busy", BUSY_MESSAGE)
    except (OSError, SleeperError):
        log.exception("live refresh failed")
        return fail("server", "Sleeper refresh failed. See the server log.")
    clear_league_cache()
    runner.clear()
    return ok({"player_rows": player_rows})
