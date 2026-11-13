"""Helpers the route modules share: the job runner dependency, league checks and `run_job`."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import polars as pl
from fastapi import Depends, Query, Request

from fantasy import store
from fantasy.api_deps import RequestContext
from fantasy.api_envelope import NO_DATA_MESSAGE, fail, guarded, running
from fantasy.api_jobs import Busy, JobKey, JobRunner
from fantasy.data_api import data_version, file_stamp, pinned_version

BUSY_MESSAGE = "The server is busy. Try again in a moment."
Week = Annotated[int, Query(ge=0, le=22, description="0 means the current week")]


def get_runner(request: Request) -> JobRunner:
    runner: JobRunner = request.app.state.runner
    return runner


Runner = Annotated[JobRunner, Depends(get_runner)]


def known_league(league: str, data_dir: Path) -> bool:
    """Raises FileNotFoundError without a leagues table, so callers can answer `no_data`."""
    # the keys alone: no join with league_teams, no scoring JSON
    return league in store.read_table("leagues", "raw", data_dir)["league_key"].to_list()


def known_team(league: str, team: int, data_dir: Path) -> bool:
    """Whether `team` is a roster in `league`: any other `?team=` would start a new simulation."""
    try:
        leagues = store.read_table("leagues", "raw", data_dir).filter(
            pl.col("league_key") == league
        )
        teams = store.read_table("league_teams", "raw", data_dir)
    except FileNotFoundError:
        return False
    return (
        not leagues.is_empty()
        and teams.filter(
            (pl.col("league_id") == leagues["league_id"][0]) & (pl.col("roster_id") == team)
        ).height
        > 0
    )


def run_job(
    runner: JobRunner,
    endpoint: str,
    args: tuple[Any, ...],
    fn: Callable[[], Any],
    ctx: RequestContext,
) -> Any:
    """Start the job once per (endpoint, args, team, data files); 202 until it has finished."""
    try:
        if not known_league(args[0], ctx.data_dir):
            return fail("invalid", f"unknown league {args[0]!r}")
    except FileNotFoundError:
        return fail("no_data", NO_DATA_MESSAGE)
    if ctx.team is not None and not known_team(args[0], ctx.team, ctx.data_dir):
        return fail("invalid", f"unknown team {ctx.team} in league {args[0]!r}")
    version = data_version(
        ctx.data_dir
    )  # once: the league build and the key come from the same read
    # The key leaves out the clock bucket: a job that runs past a bucket boundary must stay the
    # one a polling client finds, not start again. Only the league build uses the full version.
    key: JobKey = (endpoint, (*args, ctx.team), file_stamp(version))  # args[0] stays the league

    def pinned() -> Any:
        with pinned_version(version):  # a worker thread has no context
            return fn()

    try:
        job = runner.submit(key, pinned, ctx.job_owner)
    except Busy as err:
        return fail("busy", str(err) or BUSY_MESSAGE)
    if not job.future.done():
        return running(job.started_at)
    if job.future.exception() is not None:
        runner.forget(key)  # reported once, the next request retries
    return guarded(job.future.result)
