"""The week calendar (kickoffs, waiver clear days) and my players' injury status changes."""

import json
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from fantasy._engine import _read
from fantasy._leagues import leagues, my_league
from fantasy.config import load_config
from fantasy.sim.availability import kickoffs, missing_kickoffs


def _waiver_day(settings_json: str | None) -> tuple[int | None, bool]:
    """Sleeper's waiver clear day (0 is Monday) and whether waivers run daily instead."""
    try:
        settings = json.loads(settings_json) if settings_json else {}
    except json.JSONDecodeError:
        return None, False  # unreadable settings: this league gets no waiver day
    if not isinstance(settings, dict):
        return None, False
    if settings.get("daily_waivers"):
        return None, True  # daily waivers have no single clear day
    day = settings.get("waiver_day_of_week")
    return (day if isinstance(day, int) else None), False


def week_calendar(data_dir: Path | None = None) -> dict[str, Any]:
    """The current NFL week, each team's kickoff (US Eastern) and each league's waiver clear day.
    The week is the highest current week over my leagues, as the live refresh reads it."""
    current = leagues(data_dir)
    weeks = current["current_week"].drop_nulls()
    week = int(weeks.max()) if len(weeks) else None  # type: ignore[arg-type]
    games: dict[str, datetime] = {}
    unknown: set[str] = set()
    if week is not None:
        schedules, season = _read("nfl_schedules", data_dir), load_config().season
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # teams with no kickoff time are reported below
            games = kickoffs(schedules, season, week)
        unknown = missing_kickoffs(schedules, season, week) - set(games)
    raw = _read("leagues", data_dir)
    settings = dict(raw.select("league_key", "settings").iter_rows()) if "settings" in raw else {}
    waivers = []
    for league_key, name in current.select("league_key", "name").iter_rows():
        day, daily = _waiver_day(settings.get(league_key))
        waivers.append({"league_key": league_key, "name": name, "day_of_week": day, "daily": daily})
    return {
        "week": week,
        "kickoffs": [{"team": t, "kickoff": k.isoformat()} for t, k in sorted(games.items())]
        + [{"team": t, "kickoff": None} for t in sorted(unknown)],
        "waivers": waivers,
    }


def _as_utc(iso: str) -> datetime:
    parsed = datetime.fromisoformat(iso)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def status_changes(
    league_key: str, since: datetime, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """My players whose injury status differs between the last daily Sleeper snapshot at or before
    `since` and the latest one. Empty when no snapshot is that old or none is newer."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        raise ValueError(f"unknown league {league_key!r}")
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)  # a time with no zone is read as UTC
    columns = ["sleeper_id", "full_name", "position", "team", "before", "after"]
    empty = pl.DataFrame(schema=dict.fromkeys(columns, pl.String))
    snaps = _read("sleeper_player_status", data_dir, area="archive")
    stamps = {t: _as_utc(t) for t in snaps["fetched_at"].drop_nulls().unique()}
    old = [t for t, at in stamps.items() if at <= since]
    if not old:
        return empty
    before_at, after_at = max(old, key=stamps.__getitem__), max(stamps, key=stamps.__getitem__)
    if before_at == after_at:
        return empty

    def pick(at: str, name: str) -> pl.DataFrame:
        return snaps.filter(pl.col("fetched_at") == at).select(
            "sleeper_id", pl.col("injury_status").alias(name)
        )

    mine = _read("rosters", data_dir).filter(
        (pl.col("league_id") == me["league_id"]) & (pl.col("roster_id") == me["roster_id"])
    )
    players = _read("sleeper_players", data_dir).select(
        "sleeper_id", "full_name", "position", "team"
    )
    return (
        mine.select("sleeper_id")
        .join(pick(before_at, "before"), on="sleeper_id", how="left")
        .join(pick(after_at, "after"), on="sleeper_id", how="left")
        .filter(pl.col("before").ne_missing(pl.col("after")))
        .join(players, on="sleeper_id", how="left")
        .select(columns)
        .sort("full_name", "sleeper_id")
    )
