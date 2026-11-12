"""One player's page numbers: next game range, rest of season over replacement, injury, outlook.

Display only: every number is read from what the lineup, outlook and projections already compute,
through the lineup's own helpers so the two pages agree (live games included).
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

import polars as pl

from fantasy import store
from fantasy._engine import (
    _injury_note,
    _league,
    _names,
    _play_probs,
    _week_values,
    data_version,
)
from fantasy._lineup import (
    _expected_total,
    _flag_status,
    _is_out,
    _ranged,
    _ratio_table,
    _spread,
)
from fantasy._next_game import bye_week, next_games
from fantasy._outlook import player_outlook
from fantasy.config import REGULAR_SEASON_WEEKS, load_config
from fantasy.sim import moves
from fantasy.sim.lineup import Player
from fantasy.sim.odds import LeagueData

RANGE_LEVELS = (0.1, 0.5, 0.9)


def _range(
    data: LeagueData,
    player: Player,
    chance: dict[str, float],
    live: dict[str, tuple[float, float]],
    data_dir: Path | None,
) -> tuple[float | None, float | None, float | None, float]:
    """Week range (10th, median, 90th) and expected total as the Lineup page computes them."""
    ratio, edges = _ratio_table(data.league_id, data_dir)
    out = _is_out(data, player.id)
    low, mid, high = (
        _ranged(player, _spread(player, q, chance, ratio, edges, out), live) for q in RANGE_LEVELS
    )
    return low, mid, high, _expected_total(player, live, chance.get(player.id, 1.0))


def _shown_week(
    data: LeagueData, gsis_id: str, by_week: dict[int, dict[str, float]]
) -> tuple[int | None, float | None]:
    """The week whose range to show and the points if this week's game is already final.

    A final game, a bye or no projection this week moves on to the next week that has one."""
    current = data.current_week
    points, share = data.live.get(gsis_id, (0.0, 1.0))
    final = gsis_id in data.live and share <= 0
    if not final and gsis_id in by_week.get(current, {}):
        return current, None
    later = [w for w in sorted(by_week) if w > current and gsis_id in by_week[w]]
    return (later[0] if later else None), (points if final else None)


def _replacement(
    data: LeagueData, gsis_id: str, position: str, names: dict[str, str]
) -> tuple[str | None, float | None]:
    """The best other free agent at the position by points over the rest of the season."""
    positions = moves.position_of(data)
    pool = [
        i
        for i in moves.free_agents(data)
        if i != gsis_id and positions.get(i) == position and not _is_out(data, i)
    ]
    if not pool:
        return None, None
    values = moves.ros_value(data, pool)
    best = max(pool, key=lambda i: values[i])
    return names.get(best, best), values[best]


@lru_cache(maxsize=8)
def _outlook_rows(
    league_key: str, version: str, data_dir: str, mine: int, scope: str
) -> dict[str, dict[str, Any]]:
    """player_outlook for one scope, by player; `version`, `data_dir` and `mine` key the cache."""
    rows = player_outlook(league_key, scope, Path(data_dir), mine)
    return {r["gsis_id"]: r for r in rows.iter_rows(named=True)}


def _outlook(
    league_key: str, data: LeagueData, mine: int, gsis_id: str, data_dir: Path | None
) -> dict[str, Any] | None:
    owners = dict(zip(data.rosters["gsis_id"], data.rosters["roster_id"], strict=True))
    owner = owners.get(gsis_id)
    scope = "free" if owner is None else "mine" if owner == mine else "league"
    root = store.resolve(data_dir)
    rows = _outlook_rows(league_key, data_version(root), str(root), mine, scope)
    return rows.get(gsis_id)


def _table_scan(name: str, data_dir: Path | None) -> pl.LazyFrame | None:
    """A lazy scan of a raw table, or None when it has not been written (the section hides)."""
    path = store.table_path(name, "raw", data_dir)
    return pl.scan_parquet(path) if path.exists() else None


def _role_weeks(gsis_id: str, data_dir: Path | None) -> list[dict[str, Any]]:
    """This season's regular-season snap share and target share by week, filtered at the scan."""
    season = load_config().season
    snaps = _table_scan("nfl_snaps", data_dir)
    stats = _table_scan("nfl_player_stats", data_dir)
    snap = (
        {}
        if snaps is None
        else dict(
            snaps.filter(
                (pl.col("gsis_id") == gsis_id)
                & (pl.col("season") == season)
                & (pl.col("week") <= REGULAR_SEASON_WEEKS)  # nfl_snaps has no season type
            )
            .select("week", "offense_pct")
            .collect()
            .iter_rows()
        )
    )
    target = (
        {}
        if stats is None
        else dict(
            stats.filter(
                (pl.col("player_id") == gsis_id)
                & (pl.col("season") == season)
                & (pl.col("season_type") == "REG")
            )
            .select("week", "target_share")
            .collect()
            .iter_rows()
        )
    )
    return [
        {"week": w, "snap_share": snap.get(w), "target_share": target.get(w)}
        for w in sorted(snap.keys() | target.keys())
    ]


def player_profile(
    league_key: str, gsis_id: str, data_dir: Path | None = None, team: int | None = None
) -> dict[str, Any]:
    """Everything the player page needs beyond the stat data; None fields where it has no data."""
    data, mine = _league(league_key, data_dir, team)
    names, positions = _names(data_dir), moves.position_of(data)
    position = positions.get(gsis_id)
    by_week = {
        **moves.week_values(data),
        data.current_week: _week_values(data, data.current_week, positions),
    }
    week, result = _shown_week(data, gsis_id, by_week) if position is not None else (None, None)
    low = mid = high = projection = chance_to_play = None
    if week is not None and position is not None:
        chance = _play_probs(data, week)
        live = data.live if week == data.current_week else {}
        value = by_week[week][gsis_id]
        low, mid, high, projection = _range(
            data, Player(gsis_id, position, value), chance, live, data_dir
        )
        chance_to_play = chance.get(gsis_id)
    has_ros = (data.projections["gsis_id"] == gsis_id).any()
    ros = moves.ros_value(data, [gsis_id])[gsis_id] if has_ros else None
    name, points = _replacement(data, gsis_id, position, names) if position else (None, None)
    outlook = _outlook(league_key, data, mine, gsis_id, data_dir) if position is not None else None
    upcoming = next_games([gsis_id], data.current_week, data_dir).get(gsis_id)
    return {
        "gsis_id": gsis_id,
        "full_name": names.get(gsis_id),
        "position": position,
        "week": week,
        "result_week": data.current_week if result is not None else None,
        "result_points": result,
        "projection": projection,
        "p10": low,
        "median": mid,
        "p90": high,
        "chance_to_play": chance_to_play,
        "injury": _flag_status(data, gsis_id) or None,
        "injury_note": _injury_note(data, gsis_id),
        "is_out": position is not None and _is_out(data, gsis_id),
        "ros_points": ros,
        "replacement_name": name,
        "replacement_points": points,
        "ros_over_replacement": None if ros is None or points is None else ros - points,
        "outlook_label": outlook["label"] if outlook else None,
        "why": outlook["why"] if outlook else None,
        "role_weeks": _role_weeks(gsis_id, data_dir),
        "next_game": upcoming.long() if upcoming else None,
        "bye_week": bye_week(gsis_id, data_dir),
    }
