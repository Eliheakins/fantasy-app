"""Waivers: free agents ranked by the expected points they add, and their playoff and title odds.

Each add is paired with the drop that costs the least. Depth and free-agent stand-ins count (see
`Valuer`), so a backup at a position with plenty of free agents adds little.
"""

from typing import NamedTuple

import polars as pl

from fantasy.sim.odds import LeagueData, league_odds
from fantasy.sim.roster import (
    Valuer,
    free_agents,
    position_of,
    ros_value,
    team_ids,
    with_roster,
)
from fantasy.sim.value import POSITIONS

CANDIDATES_PER_POSITION = 8
DROP_CANDIDATES = 8  # lowest rest-of-season players considered for a drop


class Waiver(NamedTuple):
    gsis_id: str
    position: str
    drop_id: str
    delta_mu: (
        float  # extra expected points over the rest of the season, depth and replacement counted
    )


def waiver_candidates(
    data: LeagueData, roster_id: int, top_n: int = 25, valuer: Valuer | None = None
) -> list[Waiver]:
    """Free agents ranked by the expected points they add over the rest of the season, each
    with the drop that costs least. Depth and free-agent stand-ins count, so a backup at a
    position with plenty of free agents adds little."""
    ids = team_ids(data, roster_id)
    if not ids:
        return []
    valuer = valuer or Valuer(data)
    positions = position_of(data)
    base = valuer(ids)
    pool = free_agents(data)
    pool_value = ros_value(data, pool)
    shortlist: list[str] = []
    for position in POSITIONS:
        of_position = [p for p in pool if positions.get(p) == position]
        shortlist += sorted(of_position, key=lambda p: -pool_value[p])[:CANDIDATES_PER_POSITION]
    ranked = [best_swap(data, ids, c, base, valuer) for c in shortlist]
    return sorted(ranked, key=lambda w: -w.delta_mu)[:top_n]


def best_swap(
    data: LeagueData, ids: list[str], add: str, base: float, valuer: Valuer | None = None
) -> Waiver:
    """Add `add` and drop whoever costs the least expected points. Only the lowest-value
    players are considered for the drop, which keeps this fast."""
    valuer = valuer or Valuer(data)
    ros = ros_value(data, ids)
    drops = sorted(ids, key=lambda i: (ros[i], i))[:DROP_CANDIDATES]
    tries = [(valuer([i for i in ids if i != drop] + [add]) - base, drop) for drop in drops]
    gain, drop = max(tries, key=lambda t: (t[0], t[1]))
    return Waiver(add, position_of(data)[add], drop, gain)


def waiver_odds(
    data: LeagueData, my_id: int, adds: list[Waiver], n_sims: int = 20000, seed: int = 0
) -> pl.DataFrame:
    """Playoff and title odds for me before and after each add-drop, on the same random draws.

    `se_title` is the independent-runs standard error of the title change, an upper bound since
    shared draws make the two runs move together.
    """
    before = league_odds(data, None, n_sims, seed, reoptimize=True)
    me = data.roster_ids.index(my_id)
    rows = []
    for w in adds:
        ids = [i for i in team_ids(data, my_id) if i != w.drop_id] + [w.gsis_id]
        after = league_odds(data, with_roster(data, my_id, ids), n_sims, seed, reoptimize=True)
        p0, p1 = float(before.p_title[me]), float(after.p_title[me])
        rows.append(
            {
                "gsis_id": w.gsis_id,
                "playoff_delta": float(after.p_playoffs[me] - before.p_playoffs[me]),
                "title_delta": p1 - p0,
                "se_title": (p0 * (1 - p0) / n_sims + p1 * (1 - p1) / n_sims) ** 0.5,
            }
        )
    return pl.DataFrame(
        rows,
        schema={
            "gsis_id": pl.String,
            "playoff_delta": pl.Float64,
            "title_delta": pl.Float64,
            "se_title": pl.Float64,
        },
    )
