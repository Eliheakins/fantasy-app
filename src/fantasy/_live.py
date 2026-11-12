"""Live scores: the Sleeper refresh, my live win chance and the live_win_history it appends to.

The one module the API read path calls that writes: `refresh_live` pulls Sleeper, `record_live_tick`
appends `live_win_history`.
"""

import logging
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from fantasy import store
from fantasy._engine import _league, _opponent_of, _read, current_week
from fantasy._leagues import leagues
from fantasy._outlook import live_score
from fantasy._scoreboard import scoreboard_of
from fantasy.sim.odds import LeagueData


def refresh_live(data_dir: Path | None = None) -> int:
    """Pull this week's matchups from Sleeper again so scores are current. Returns player rows."""
    from fantasy.stages.sync_sleeper import sync_week

    week = current_week(leagues(data_dir))
    if week is None:
        raise ValueError("no league has a current week")
    return sync_week(week, data_dir)


LIVE_HISTORY = "live_win_history"


log = logging.getLogger(__name__)


def _open_starters(data: LeagueData, roster_id: int) -> int:
    """Set starters still to score: players plus K and DEF slots (a game under way counts whole)."""
    state = data.current[roster_id]
    return len(state.open_players) + math.ceil(state.open_k) + math.ceil(state.open_def)


def live_win_row(
    league_key: str, data_dir: Path | None = None, team: int | None = None
) -> dict[str, Any] | None:
    """My matchup now (the viewed team's with ?team=): chance to win, points so far, projected
    finals and starters left. Display only, read from the scoreboard and live_score. None when the
    week has no matchup for the team."""
    data, mine = _league(league_key, data_dir, team)
    opp = _opponent_of(data, mine, data.current_week)
    board = scoreboard_of(data, mine, data_dir=data_dir)
    if opp is None or board.is_empty() or mine not in data.current or opp not in data.current:
        return None
    first = board.row(0, named=True)
    side = "a" if first["a_is_me"] else "b"
    score = {r["side"]: r for r in live_score(league_key, data_dir, team).iter_rows(named=True)}
    if "me" not in score or "them" not in score:
        return None
    return {
        "league_id": data.league_id,
        "week": data.current_week,
        "roster_id": mine,
        "my_team": score["me"]["team_name"],
        "opp_team": score["them"]["team_name"],
        "win_prob": first[f"{side}_win_prob"],
        "my_points": score["me"]["points"],
        "opp_points": score["them"]["points"],
        "my_projected": score["me"]["projected_final"],
        "opp_projected": score["them"]["projected_final"],
        "my_left": _open_starters(data, mine),
        "opp_left": _open_starters(data, opp),
    }


def record_live_tick(now: datetime | None = None, data_dir: Path | None = None) -> None:
    """Append my matchup of each league to live_win_history in one write, once per run_at,
    current week only (a league's older rows go). Called by the live refresh and the Refresh
    scores button, never touches sim_season_history. Any failure is logged and swallowed:
    display-only history must not fail a refresh."""
    try:
        run_at = (now or datetime.now(UTC)).isoformat(timespec="seconds")
        found = []
        for league_key in leagues(data_dir)["league_key"].to_list():
            try:
                row = live_win_row(league_key, data_dir)
            except Exception:
                log.exception("live history failed for %s", league_key)
                continue
            if row is not None:
                found.append({**row, "run_at": run_at})
        if found:
            _append_live_rows(found, data_dir)
    except Exception:
        log.exception("live history failed")


def _append_live_rows(rows: list[dict[str, Any]], data_dir: Path | None) -> None:
    schema = store.SCHEMAS[LIVE_HISTORY]
    new = pl.DataFrame([{c: r[c] for c in schema} for r in rows], schema=schema).unique(
        subset=["league_id", "roster_id", "run_at"], keep="last", maintain_order=True
    )
    old = _read(LIVE_HISTORY, data_dir, area="derived")
    for league_id, week in {(r["league_id"], r["week"]) for r in rows}:
        old = old.filter(~((pl.col("league_id") == league_id) & (pl.col("week") != week)))
    old = old.join(
        new.select("league_id", "roster_id", "run_at"),
        how="anti",
        on=["league_id", "roster_id", "run_at"],
    )
    store.write_table(LIVE_HISTORY, pl.concat([old, new]), "derived", data_dir)


def game_day(
    league_key: str, data_dir: Path | None = None, team: int | None = None
) -> dict[str, Any]:
    """The numbers now plus today's history for my team (the viewed team with ?team=).
    `as_of` is when `current` was computed: the chart adds it as the last point, so the line
    and the headline number agree (the win probability is seeded, so it only moves with the data
    and the game clock)."""
    current = live_win_row(league_key, data_dir, team)
    if current is None:
        return {"week": None, "as_of": None, "current": None, "history": []}
    table = _read(LIVE_HISTORY, data_dir, area="derived")
    mine = table.filter(
        (pl.col("league_id") == current["league_id"])
        & (pl.col("roster_id") == current["roster_id"])
        & (pl.col("week") == current["week"])
    ).sort("run_at")
    shown = {**current, "points_needed": current["opp_projected"] - current["my_points"]}
    return {
        "week": current["week"],
        "as_of": datetime.now(UTC).isoformat(timespec="seconds"),
        "current": shown,
        "history": mine.to_dicts(),
    }
