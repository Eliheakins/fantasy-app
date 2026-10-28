"""Weekly digest reads behind data_api: last week's result, projection misses, odds change and
the move ideas the digest stage stored.

Each takes `me`, my row from `data_api.leagues` (this module never calls `leagues`, see the note in
data_api). Luck and bench points left reuse the League page's season totals: last week's figure is
the total through that week minus the total through the week before.
"""

from pathlib import Path
from typing import Any

import polars as pl

from fantasy import _league_view, store
from fantasy._engine import _read
from fantasy._schemas import ENGINE_SCHEMAS
from fantasy.config import load_config
from fantasy.sim.schedule import completed

IDEA_KINDS = ("waiver", "trade")


def _empty(name: str) -> pl.DataFrame:
    return pl.DataFrame(schema=ENGINE_SCHEMAS[name])


def _season_value(table: pl.DataFrame, roster_id: int, column: str) -> float | None:
    mine = table.filter(pl.col("roster_id") == roster_id)
    return None if mine.is_empty() else float(mine[column][0])


def _week_figure(
    me: dict[str, Any], week: int, data_dir: Path, read: Any, column: str
) -> float | None:
    """A League page season total, taken through `week` minus through the week before."""
    through = read({**me, "current_week": week + 1}, data_dir)
    now = _season_value(through, me["roster_id"], column)
    if now is None:
        return None
    before = _season_value(read({**me, "current_week": week}, data_dir), me["roster_id"], column)
    return now - (before or 0.0)


def _nfl_week_over(me: dict[str, Any], week: int, data_dir: Path) -> bool:
    """Every NFL game of the week has a score. False without schedule rows for the season."""
    games = _read("nfl_schedules", data_dir).filter(
        (pl.col("season") == load_config().season) & (pl.col("week") == week)
    )
    return not games.is_empty() and games["home_score"].null_count() == 0


def last_scored_week(me: dict[str, Any], data_dir: Path) -> int:
    """The latest finished week: the week before the current one, or the current week itself once
    every NFL game in it is final (Sleeper keeps the old week until it rolls over midweek)."""
    current = int(me["current_week"])
    return current if _nfl_week_over(me, current, data_dir) else current - 1


def last_week(me: dict[str, Any], data_dir: Path) -> pl.DataFrame:
    """My game in the last finished week; empty in week 1 or if it was not scored."""
    week = last_scored_week(me, data_dir)
    if week < 1:
        return _empty("last_week")
    settings = _league_view._settings(me, data_dir)
    games = completed(_league_view._matchups(me, data_dir), week).filter(pl.col("week") == week)
    mine = games.filter(pl.col("roster_id") == me["roster_id"])
    if mine.is_empty():
        return _empty("last_week")
    game = mine.row(0, named=True)
    other = games.filter(
        (pl.col("matchup_id") == game["matchup_id"]) & (pl.col("roster_id") != me["roster_id"])
    )
    if other.is_empty():
        return _empty("last_week")
    rival = other.row(0, named=True)
    names = dict(
        zip(*_league_view._teams(me, data_dir).select("roster_id", "team_name"), strict=True)
    )
    scored = week < int(settings["playoff_week_start"])  # the League page counts no playoff weeks
    luck = _week_figure(me, week, data_dir, _league_view.luck, "luck") if scored else None
    bench = (
        _week_figure(me, week, data_dir, _league_view.manager_grades, "bench_points_left")
        if scored
        else None
    )
    diff = game["points"] - rival["points"]
    row = {
        "week": week,
        "roster_id": me["roster_id"],
        "team_name": me["team_name"],
        "opponent": names.get(rival["roster_id"]),
        "points": game["points"],
        "opp_points": rival["points"],
        "result": "W" if diff > 0 else "L" if diff < 0 else "T",
        "bench_points_left": bench,
        "luck": luck,
    }
    return pl.DataFrame([row], schema=ENGINE_SCHEMAS["last_week"])


def player_vs_projection(me: dict[str, Any], week: int, data_dir: Path) -> pl.DataFrame:
    """My starters at skill positions in a week (0: last finished week): points against the last
    `proj_snapshots` row for the player that week. The column follows `projection_model`; no
    Sleeper blend or injury layer, so not the number the app showed. Null where no snapshot."""
    week = week or last_scored_week(me, data_dir)
    league = _read("leagues", data_dir).filter(pl.col("league_id") == me["league_id"])
    if week < 1 or league.is_empty():
        return _empty("player_vs_projection")
    starters = _read("matchup_players", data_dir).filter(
        (pl.col("league_id") == me["league_id"])
        & (pl.col("week") == week)
        & (pl.col("roster_id") == me["roster_id"])
        & pl.col("is_starter")
    )
    players = _read("sleeper_players", data_dir).select("sleeper_id", "full_name", "position")
    id_map = _read("id_map", data_dir, area="derived").select("sleeper_id", "gsis_id")
    column = "learned" if store.projection_name(data_dir) == "proj_learned" else "baseline"
    last = (
        _read("proj_snapshots", data_dir, area="archive")
        .filter(
            (pl.col("league_id") == me["league_id"])
            & (pl.col("season") == league["season"][0])
            & (pl.col("week") == week)
        )
        .sort("fetched_at")
        .group_by("gsis_id")
        .agg(pl.col(column).last().alias("projection"))
    )
    table = (
        starters.join(players, on="sleeper_id")
        .filter(pl.col("position").is_in(store.SKILL))
        .join(id_map, on="sleeper_id")
        .join(last, on="gsis_id", how="left")
        .with_columns((pl.col("points") - pl.col("projection")).alias("diff"))
    )
    return table.select(*ENGINE_SCHEMAS["player_vs_projection"]).sort("diff", nulls_last=True)


def odds_change(history: pl.DataFrame, league_id: str, mine: int) -> pl.DataFrame:
    """Every team's odds in the latest run against the last run of the nearest earlier
    `as_of_week` (several refreshes in a week: the last one counts). Null, never zero, when
    there is no earlier week or the team was not in it."""
    runs = history.filter(pl.col("league_id") == league_id)
    if runs.is_empty():
        return _empty("odds_change")
    last_runs = runs.group_by("as_of_week").agg(pl.col("run_at").max())
    latest_week = runs.filter(pl.col("run_at") == runs["run_at"].max())["as_of_week"][0]
    earlier = last_runs.filter(pl.col("as_of_week") < latest_week)
    prev_week = None if earlier.is_empty() else int(earlier["as_of_week"].max())  # type: ignore[arg-type]

    def take(week: int) -> pl.DataFrame:
        run = last_runs.filter(pl.col("as_of_week") == week)
        return runs.join(run, on=["as_of_week", "run_at"])

    now = take(latest_week).select("roster_id", "team_name", "as_of_week", "p_playoffs", "p_title")
    if prev_week is None:
        before = _empty("odds_change").select("roster_id", "p_playoffs", "p_title")
    else:
        before = take(prev_week).select("roster_id", "p_playoffs", "p_title")
    before = before.rename({"p_playoffs": "prev_playoffs", "p_title": "prev_title"})
    table = now.join(before, on="roster_id", how="left").with_columns(
        (pl.col("roster_id") == mine).alias("is_me"),
        pl.lit(prev_week, dtype=pl.Int64).alias("prev_as_of_week"),
        (pl.col("p_playoffs") - pl.col("prev_playoffs")).alias("d_playoffs"),
        (pl.col("p_title") - pl.col("prev_title")).alias("d_title"),
    )
    return table.select(*ENGINE_SCHEMAS["odds_change"]).sort("p_title", descending=True)


def is_my_team(me: dict[str, Any], data_dir: Path) -> bool:
    """The viewed team is my own (Sleeper's is_me), the only one the digest stage stores for."""
    teams = _league_view._teams(me, data_dir)
    return bool(teams.filter(pl.col("roster_id") == me["roster_id"])["is_me"].any())


def move_ideas(me: dict[str, Any], kind: str, data_dir: Path) -> pl.DataFrame:
    """Stored ideas of a kind ("waiver" or "trade"), best first. Empty for any team but mine."""
    if kind not in IDEA_KINDS:
        raise ValueError(f"kind must be one of {IDEA_KINDS}, not {kind!r}")
    empty = pl.DataFrame(schema=store.SCHEMAS["move_ideas"])
    if not is_my_team(me, data_dir):
        return empty
    stored = _read("move_ideas", data_dir, area="derived")
    mine = stored.filter((pl.col("league_id") == me["league_id"]) & (pl.col("kind") == kind))
    return mine.sort("rank") if not mine.is_empty() else empty


def stored_adds(me: dict[str, Any], data_dir: Path) -> pl.DataFrame:
    """Stored waiver ideas in the shape of `waivers`, for `actions(adds=...)`."""
    ideas = move_ideas(me, "waiver", data_dir)
    rows = [
        {
            "gsis_id": r["get_ids"][0] if r["get_ids"] else None,
            "full_name": r["get"],
            "position": None,
            "drop_name": r["give"],
            "delta_points": r["delta_points"],
            "playoff_delta": r["playoff_delta"],
            "title_delta": r["title_delta"],
            "se_title": r["se_title"],
            "trending_adds": None,
        }
        for r in ideas.iter_rows(named=True)
    ]
    return pl.DataFrame(rows, schema=ENGINE_SCHEMAS["waivers"])
