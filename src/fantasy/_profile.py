"""One player's page numbers: next game range, rest of season over replacement, injury, outlook.

Display only: every number is read from what the lineup, outlook and projections already compute.
"""

from typing import Any

import polars as pl

from fantasy import store
from fantasy._engine import (
    _injury_note,
    _league,
    _marginals,
    _names,
    _play_probs,
    _tier_edges,
    _week_values,
)
from fantasy._lineup import _flag_status, _is_out, _spread
from fantasy._outlook import player_outlook
from fantasy.config import load_config
from fantasy.sim import moves
from fantasy.sim.lineup import Player

RANGE_LEVELS = (0.1, 0.5, 0.9)


def _range(data: Any, player: Player, chance: dict[str, float]) -> list[float | None]:
    """Full-game 10th, 50th and 90th percentile, scaled from the projection as the lineup does."""
    marginals = _marginals(data.league_id)
    ratio = {
        (r["position"], r["tier"], round(r["tau"], 2)): r["ratio"]
        for r in marginals.iter_rows(named=True)
    }
    edges = _tier_edges(marginals)
    out = _is_out(data, player.id)
    return [_spread(player, q, chance, ratio, edges, out) for q in RANGE_LEVELS]


def _replacement(
    data: Any, gsis_id: str, position: str, names: dict[str, str]
) -> tuple[str | None, float | None]:
    """The best other free agent at the position by points over the rest of the season."""
    positions = moves.position_of(data)
    pool = [i for i in moves.free_agents(data) if i != gsis_id and positions.get(i) == position]
    if not pool:
        return None, None
    values = moves.ros_value(data, pool)
    best = max(pool, key=lambda i: values[i])
    return names.get(best, best), values[best]


def _outlook(league_key: str, data: Any, mine: int, gsis_id: str) -> dict[str, Any] | None:
    owners = dict(zip(data.rosters["gsis_id"], data.rosters["roster_id"], strict=True))
    owner = owners.get(gsis_id)
    scope = "free" if owner is None else "mine" if owner == mine else "league"
    rows = player_outlook(league_key, scope).filter(pl.col("gsis_id") == gsis_id)
    return rows.row(0, named=True) if rows.height else None


def _table_if_present(name: str) -> pl.DataFrame | None:
    """A raw table, or None when it has not been written (the role section then hides)."""
    if not store.table_path(name, "raw", store.DATA_DIR).exists():
        return None
    return store.read_table(name, "raw")


def _role_weeks(gsis_id: str) -> list[dict[str, Any]]:
    """This season's snap share and target share by week, from the existing role tables."""
    season = load_config().season
    snaps, stats = _table_if_present("nfl_snaps"), _table_if_present("nfl_player_stats")
    snap = (
        {}
        if snaps is None
        else dict(
            snaps.filter((pl.col("gsis_id") == gsis_id) & (pl.col("season") == season))
            .select("week", "offense_pct")
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
            .iter_rows()
        )
    )
    return [
        {"week": w, "snap_share": snap.get(w), "target_share": target.get(w)}
        for w in sorted(snap.keys() | target.keys())
    ]


def player_profile(league_key: str, gsis_id: str) -> dict[str, Any]:
    """Everything the player page needs beyond the stat data; None fields where it has no data."""
    data, mine = _league(league_key)
    names, positions = _names(), moves.position_of(data)
    position = positions.get(gsis_id)
    week = data.current_week
    value = _week_values(data, week, positions).get(gsis_id)
    chance = _play_probs(data, week)
    low = mid = high = None
    if position is not None and value is not None:
        low, mid, high = _range(data, Player(gsis_id, position, value), chance)
    ros = moves.ros_value(data, [gsis_id])[gsis_id] if position is not None else None
    name, points = _replacement(data, gsis_id, position, names) if position else (None, None)
    outlook = _outlook(league_key, data, mine, gsis_id) if position is not None else None
    return {
        "gsis_id": gsis_id,
        "full_name": names.get(gsis_id),
        "position": position,
        "week": week,
        "projection": value,
        "p10": low,
        "median": mid,
        "p90": high,
        "chance_to_play": chance.get(gsis_id),
        "injury": _flag_status(data, gsis_id) or None,
        "injury_note": _injury_note(data, gsis_id),
        "ros_points": ros,
        "replacement_name": name,
        "replacement_points": points,
        "ros_over_replacement": None if ros is None or points is None else ros - points,
        "outlook_label": outlook["label"] if outlook else None,
        "why": outlook["why"] if outlook else None,
        "role_weeks": _role_weeks(gsis_id),
    }
