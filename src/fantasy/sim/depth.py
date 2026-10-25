"""Bench depth by position: what each team's non-starters are worth over free-agent stand-ins."""

import math

import polars as pl

from fantasy.sim.lineup import Player, auto_lineup
from fantasy.sim.moves import Valuer, ros_value, team_ids
from fantasy.sim.odds import LeagueData
from fantasy.sim.value import POSITIONS


def _starts_per_week(ids: list[str], valuer: Valuer) -> dict[str, float]:
    """Average starters at each position over the weeks, from the team's best weekly lineups."""
    totals = dict.fromkeys(POSITIONS, 0)
    for values in valuer.values.values():
        pool = [
            Player(i, valuer.positions[i], values[i])
            for i in ids
            if i in values and i in valuer.positions
        ]
        for pid in auto_lineup(pool, valuer.slots).players:
            totals[valuer.positions[pid]] += 1
    weeks = max(len(valuer.values), 1)
    return {pos: n / weeks for pos, n in totals.items()}


def position_depth(data: LeagueData, valuer: Valuer | None = None) -> pl.DataFrame:
    """roster_id, position, depth_per_week: points a week the bench at a position adds over
    stand-ins, counting byes and injuries (the team's season value with and without it).

    The bench is the players at the position beyond the (rounded up) average number its best
    lineups start there, best rest-of-season points first kept as starters."""
    valuer = valuer or Valuer(data)
    weeks = max(len(valuer.values), 1)
    rows: list[tuple[int, str, float]] = []
    for roster_id in data.roster_ids:
        ids = team_ids(data, roster_id)
        base = valuer(ids)
        starts = _starts_per_week(ids, valuer)
        ros = ros_value(data, ids)
        for pos in POSITIONS:
            at_pos = sorted(
                (i for i in ids if valuer.positions.get(i) == pos), key=lambda i: (-ros[i], i)
            )
            bench = set(at_pos[math.ceil(starts[pos] - 1e-9) :])
            lost = base - valuer([i for i in ids if i not in bench]) if bench else 0.0
            rows.append((roster_id, pos, max(0.0, lost) / weeks))
    return pl.DataFrame(rows, schema=["roster_id", "position", "depth_per_week"], orient="row")
