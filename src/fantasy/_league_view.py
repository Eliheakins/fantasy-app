"""League page reads behind data_api: power rankings, luck, manager grades and what-ifs.

Each takes `me`, my row from `data_api.leagues` (this module never calls `leagues`, see the note
in data_api). Completed weeks are those before the current week and before the playoffs.
Simulation tables (`sim_*`) are optional: without them the sim columns come back empty.
"""

from pathlib import Path
from typing import Any

import polars as pl

from fantasy._engine import _read
from fantasy._schemas import ENGINE_SCHEMAS
from fantasy.sim.lineup import ActualPlayer, best_actual
from fantasy.sim.schedule import all_play, completed, pairings

LINEUP_POSITIONS = frozenset({"QB", "RB", "WR", "TE", "K", "DEF"})


def _empty(name: str) -> pl.DataFrame:
    return pl.DataFrame(schema=ENGINE_SCHEMAS[name])


def _settings(me: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    leagues = _read("leagues", data_dir).filter(pl.col("league_id") == me["league_id"])
    return leagues.row(0, named=True)


def _through(me: dict[str, Any], settings: dict[str, Any]) -> int:
    return min(int(me["current_week"]) - 1, int(settings["playoff_week_start"]) - 1)


def _teams(me: dict[str, Any], data_dir: Path) -> pl.DataFrame:
    teams = _read("league_teams", data_dir).filter(pl.col("league_id") == me["league_id"])
    return teams.select("roster_id", "team_name", "is_me")


def _matchups(me: dict[str, Any], data_dir: Path) -> pl.DataFrame:
    return _read("matchups", data_dir).filter(pl.col("league_id") == me["league_id"])


def power_rankings(me: dict[str, Any], data_dir: Path) -> pl.DataFrame:
    odds = _read("sim_season", data_dir, area="derived").filter(
        pl.col("league_id") == me["league_id"]
    )
    if odds.is_empty():
        return _empty("power_rankings")
    weeks = _read("sim_team_weeks", data_dir, area="derived").filter(
        pl.col("league_id") == me["league_id"]
    )
    first = weeks["week"].min()
    exp_now = weeks.filter(pl.col("week") == first).select(
        "roster_id", pl.col("exp_points").alias("exp_points_week")
    )
    exp = weeks.select("week", "roster_id", "exp_points")
    games = pairings(_matchups(me, data_dir)).filter(
        pl.col("week").is_in(weeks["week"].unique().to_list())
    )
    faced = pl.concat(
        [
            games.select(
                "week", pl.col("roster_a").alias("roster_id"), pl.col("roster_b").alias("opp")
            ),
            games.select(
                "week", pl.col("roster_b").alias("roster_id"), pl.col("roster_a").alias("opp")
            ),
        ]
    )
    sos = (
        faced.join(exp.rename({"roster_id": "opp", "exp_points": "opp_points"}), on=["week", "opp"])
        .group_by("roster_id")
        .agg(pl.col("opp_points").mean().alias("sos_remaining"))
    )
    table = (
        odds.join(_teams(me, data_dir).select("roster_id", "is_me"), on="roster_id")
        .join(exp_now, on="roster_id", how="left")
        .join(sos, on="roster_id", how="left")
        .with_columns(
            pl.col("exp_points_week").rank("ordinal", descending=True).cast(pl.Int64).alias("rank"),
            pl.col("sos_remaining")
            .rank("ordinal", descending=True)
            .cast(pl.Int64)
            .alias("sos_rank"),
        )
    )
    return table.select(*ENGINE_SCHEMAS["power_rankings"]).sort("rank", nulls_last=True)


def luck(me: dict[str, Any], data_dir: Path) -> pl.DataFrame:
    through = _through(me, _settings(me, data_dir))
    record = all_play(_matchups(me, data_dir), through)
    if record.is_empty():
        return _empty("luck")
    games = pl.col("ap_wins") + pl.col("ap_losses") + pl.col("ap_ties")
    expected = (pl.col("ap_wins") + 0.5 * pl.col("ap_ties")) / games * pl.col("weeks")
    table = (
        record.join(_teams(me, data_dir), on="roster_id")
        .with_columns(expected.alias("exp_wins"))
        .with_columns((pl.col("wins") + 0.5 * pl.col("ties") - pl.col("exp_wins")).alias("luck"))
    )
    return table.select(*ENGINE_SCHEMAS["luck"]).sort("luck", descending=True)


def _lineup_options(players: pl.DataFrame) -> dict[str, tuple[str, ...]]:
    """sleeper_id -> the lineup positions he can fill (fantasy_positions, else his position)."""
    out = {}
    for r in players.iter_rows(named=True):
        listed = r["fantasy_positions"] or [r["position"]]
        kept = tuple(p for p in listed if p in LINEUP_POSITIONS)
        if kept:
            out[r["sleeper_id"]] = kept
    return out


def manager_grades(me: dict[str, Any], data_dir: Path) -> pl.DataFrame:
    settings = _settings(me, data_dir)
    played = completed(_matchups(me, data_dir), _through(me, settings))
    if played.is_empty():
        return _empty("manager_grades")
    options = _lineup_options(_read("sleeper_players", data_dir))
    scored = _read("matchup_players", data_dir).join(
        played.select("league_id", "week", "roster_id"), on=["league_id", "week", "roster_id"]
    )
    optimal: dict[int, float] = {}
    actual: dict[int, float] = {}
    weeks: dict[int, int] = {}
    for (roster_id, _week), g in scored.group_by("roster_id", "week"):
        roster_positions = list(settings["roster_positions"])
        players = [
            ActualPlayer(r["sleeper_id"], options[r["sleeper_id"]], r["points"] or 0.0)
            for r in g.iter_rows(named=True)
            if r["sleeper_id"] in options
        ]
        key = int(roster_id)
        optimal[key] = optimal.get(key, 0.0) + best_actual(players, roster_positions)
        actual[key] = actual.get(key, 0.0) + float(g.filter(pl.col("is_starter"))["points"].sum())
        weeks[key] = weeks.get(key, 0) + 1
    table = pl.DataFrame(
        [(r, weeks[r], actual[r], optimal[r]) for r in optimal],
        schema={
            "roster_id": pl.Int64,
            "weeks": pl.Int64,
            "actual_points": pl.Float64,
            "optimal_points": pl.Float64,
        },
        orient="row",
    )
    table = table.join(_teams(me, data_dir), on="roster_id").with_columns(
        (pl.col("actual_points") / pl.col("optimal_points")).alias("efficiency"),
        (pl.col("optimal_points") - pl.col("actual_points")).alias("bench_points_left"),
    )
    return table.select(*ENGINE_SCHEMAS["manager_grades"]).sort("efficiency", descending=True)


def what_if(me: dict[str, Any], week: int, data_dir: Path) -> pl.DataFrame:
    """My playoff and title odds if each side of each matchup in `week` wins (0 is this week).
    Nothing for a completed week or a playoff week."""
    settings = _settings(me, data_dir)
    week = week or int(me["current_week"])
    if week < int(me["current_week"]) or week >= int(settings["playoff_week_start"]):
        return _empty("what_if")
    lid, mine = me["league_id"], me["roster_id"]
    conditional = _read("sim_conditional", data_dir, area="derived").filter(
        (pl.col("league_id") == lid) & (pl.col("week") == week) & (pl.col("roster_id") == mine)
    )
    plain = _read("sim_season", data_dir, area="derived").filter(
        (pl.col("league_id") == lid) & (pl.col("roster_id") == mine)
    )
    if conditional.is_empty() or plain.is_empty():
        return _empty("what_if")
    base = plain.row(0, named=True)
    names = _teams(me, data_dir).select("roster_id", "team_name")
    table = (
        conditional.join(
            names.rename({"roster_id": "winner_id", "team_name": "winner"}), on="winner_id"
        )
        .join(names.rename({"roster_id": "loser_id", "team_name": "loser"}), on="loser_id")
        .with_columns(
            ((pl.col("winner_id") == mine) | (pl.col("loser_id") == mine)).alias("involves_me"),
            (pl.col("p_playoffs") - base["p_playoffs"]).alias("d_playoffs"),
            (pl.col("p_title") - base["p_title"]).alias("d_title"),
            pl.min_horizontal("winner_id", "loser_id").alias("_pair"),
        )
    )
    ordered = table.sort(["involves_me", "_pair", "winner_id"], descending=[True, False, False])
    return ordered.select(*ENGINE_SCHEMAS["what_if"])
