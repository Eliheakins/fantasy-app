"""Every matchup of a week at once: projected totals, ranges and chances to win (see data_api).

One joint draw covers the starters of all matchups, so a matchup's two totals come from the
same draws. Teams play the lineup set in Sleeper (current week) or their best lineup.
"""

from typing import Any

import numpy as np
import polars as pl

from fantasy import store
from fantasy._engine import (
    KD_SEED_OFFSET,
    LINEUP_SEED,
    _constant_points,
    _opponent_lineup,
    _week_points,
)
from fantasy._schemas import ENGINE_SCHEMAS
from fantasy.sim import moves
from fantasy.sim.lineup import lineup_slots
from fantasy.sim.odds import LeagueData

SCOREBOARD_SIMS = 20000
NOT_STARTED, LIVE, FINAL = "Not started", "Live", "Final"
LOW, MID, HIGH = 0.1, 0.5, 0.9

Stats = dict[str, float | None]


def _status(shares: list[float]) -> str:
    if all(s >= 1.0 for s in shares):
        return NOT_STARTED
    return FINAL if all(s <= 0.0 for s in shares) else LIVE


def _side(prefix: str, data: LeagueData, team: int, mine: int, stats: Stats) -> dict[str, Any]:
    named: dict[str, Any] = {
        "roster_id": team,
        "team_name": data.team_names.get(team, str(team)),
        "is_me": team == mine,
        **stats,
    }
    return {f"{prefix}_{k}": v for k, v in named.items()}


def _final_stats(points: float) -> Stats:
    return {
        "projected": points, "floor": points, "median": points, "ceiling": points,
        "win_prob": None, "points": points, "share_left": 0.0,
    }  # fmt: skip


def _past_week(
    data: LeagueData, mine: int, week: int, matchup_of: dict[int, int | None]
) -> list[dict[str, Any]]:
    played = store.read_table("matchups", "raw").filter(
        (pl.col("league_id") == data.league_id) & (pl.col("week") == week)
    )
    score = dict(zip(played["roster_id"], played["points"], strict=True))
    return [
        {
            "week": week, "matchup_id": matchup_of.get(a), "status": FINAL,
            **_side("a", data, a, mine, _final_stats(float(score.get(a) or 0.0))),
            **_side("b", data, b, mine, _final_stats(float(score.get(b) or 0.0))),
        }
        for a, b in data.pairings.get(week, [])
    ]  # fmt: skip


def _totals(
    data: LeagueData, week: int, lineups: dict[int, list[str]], n_sims: int
) -> dict[int, np.ndarray]:
    """Each team's points for the week (scored so far plus the draw for what is left)."""
    ids = sorted({i for lineup in lineups.values() for i in lineup})
    positions, values = moves.position_of(data), moves.week_values(data).get(week, {})
    points, column = (
        _week_points(data, ids, positions, values, week, n_sims)
        if ids
        else (np.zeros((n_sims, 0)), {})
    )
    current = week == data.current_week
    return {
        team: points[:, [column[i] for i in lineup]].sum(axis=1)
        + _constant_points(
            data,
            n_sims,
            LINEUP_SEED + KD_SEED_OFFSET + team,
            data.current.get(team) if current else None,
        )
        for team, lineup in lineups.items()
    }


def _live_side(
    data: LeagueData, team: int, lineup: list[str], total: np.ndarray, current: bool
) -> tuple[Stats, float]:
    """The side's numbers and the average share of its starters' games still to play."""
    live = data.live if current else {}
    share = float(np.mean([live.get(i, (0.0, 1.0))[1] for i in lineup])) if lineup else 1.0
    state = data.current.get(team) if current else None
    low, mid, high = np.quantile(total, [LOW, MID, HIGH])
    stats: Stats = {
        "projected": float(total.mean()), "floor": float(low), "median": float(mid),
        "ceiling": float(high), "win_prob": None,
        "points": 0.0 if state is None else state.realized, "share_left": share,
    }  # fmt: skip
    return stats, share


def _projected_week(
    data: LeagueData,
    mine: int,
    week: int,
    matchup_of: dict[int, int | None],
    n_sims: int,
) -> list[dict[str, Any]]:
    pairs = data.pairings[week]
    positions, values = moves.position_of(data), moves.week_values(data).get(week, {})
    slots = lineup_slots(data.roster_positions)
    lineups = {
        t: _opponent_lineup(data, t, week, positions, values, slots) for pair in pairs for t in pair
    }
    totals = _totals(data, week, lineups, n_sims)
    current = week == data.current_week
    rows = []
    for a, b in pairs:
        stats_a, share_a = _live_side(data, a, lineups[a], totals[a], current)
        stats_b, share_b = _live_side(data, b, lineups[b], totals[b], current)
        win_a = float((totals[a] > totals[b]).mean() + 0.5 * (totals[a] == totals[b]).mean())
        rows.append(
            {
                "week": week, "matchup_id": matchup_of.get(a),
                "status": _status([share_a, share_b]),
                **_side("a", data, a, mine, {**stats_a, "win_prob": win_a}),
                **_side("b", data, b, mine, {**stats_b, "win_prob": 1.0 - win_a}),
            }
        )  # fmt: skip
    return rows


def scoreboard_of(
    data: LeagueData, mine: int, week: int = 0, n_sims: int = SCOREBOARD_SIMS
) -> pl.DataFrame:
    """One row per matchup of `week` (0: the current week), my matchup first.

    A past week shows final scores from Sleeper. A later week shows projections from best
    lineups; playoff weeks that are not set yet (placeholders) come back empty. Points scored
    are only as fresh as the last refresh."""
    week = week or data.current_week
    placeholder = week > data.current_week and week >= data.playoff_start
    if not data.pairings.get(week) or placeholder:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["scoreboard"])
    table = store.read_table("matchups", "raw").filter(
        (pl.col("league_id") == data.league_id) & (pl.col("week") == week)
    )
    matchup_of = dict(zip(table["roster_id"], table["matchup_id"], strict=True))
    if week < data.current_week:
        rows = _past_week(data, mine, week, matchup_of)
    else:
        rows = _projected_week(data, mine, week, matchup_of, n_sims)
    rows.sort(key=lambda r: (not (r["a_is_me"] or r["b_is_me"]), r["matchup_id"] or 0))
    return pl.DataFrame(rows, schema=ENGINE_SCHEMAS["scoreboard"])
