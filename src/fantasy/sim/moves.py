"""Roster moves: free agents, ranking adds, and applying and evaluating a trade.

Everything here works on one league's LeagueData. Players are skill players (QB, RB, WR, TE) with
projections; K and DEF are constants in the simulator. A trade keeps each team's roster size: a
team that receives more players than it gives drops its lowest-value players, and one that
receives fewer picks up the best free agents (an assumption, stated in decisions.md).
"""

from typing import Any, NamedTuple

import numpy as np
import polars as pl

from fantasy.sim.lineup import Player, auto_lineup, lineup_slots
from fantasy.sim.odds import PLAYOFF_WEEKS, LeagueData, league_odds

CANDIDATES_PER_POSITION = 10


class Waiver(NamedTuple):
    gsis_id: str
    position: str
    drop_id: str
    delta_mu: float  # extra expected points over the rest of the season


def remaining_weeks(data: LeagueData) -> list[int]:
    return list(range(data.current_week, data.playoff_start + PLAYOFF_WEEKS))


def position_of(data: LeagueData) -> dict[str, str]:
    on_rosters = dict(zip(data.rosters["gsis_id"], data.rosters["position"], strict=True))
    return {**data.positions, **on_rosters}


def week_values(data: LeagueData) -> dict[int, dict[str, float]]:
    return {
        week: dict(zip(g["gsis_id"], g["projection"], strict=True))
        for (week,), g in data.projections.group_by("week")
    }


def ros_value(data: LeagueData, ids: list[str]) -> dict[str, float]:
    """Projected points over the rest of the season, per player."""
    wanted = data.projections.filter(pl.col("gsis_id").is_in(ids))
    sums = dict(wanted.group_by("gsis_id").agg(pl.col("projection").sum()).iter_rows())
    return {i: float(sums.get(i, 0.0)) for i in ids}


def rostered(data: LeagueData, rosters: pl.DataFrame | None = None) -> set[str]:
    return set((data.rosters if rosters is None else rosters)["gsis_id"].to_list())


def free_agents(data: LeagueData, rosters: pl.DataFrame | None = None) -> list[str]:
    """Active players Sleeper lists (data.positions) with a projection and no team in the league."""
    available = set(data.projections["gsis_id"].to_list()) & set(data.positions)
    return sorted(available - rostered(data, rosters))


def team_total(
    data: LeagueData, ids: list[str], values_by_week: dict[int, dict[str, float]] | None = None
) -> float:
    """Expected skill-position points over the rest of the season with best weekly lineups.

    Pass `values_by_week` (from week_values) when scoring many rosters to skip regrouping."""
    slots = lineup_slots(data.roster_positions)
    positions = position_of(data)
    total = 0.0
    for values in (week_values(data) if values_by_week is None else values_by_week).values():
        pool = [Player(i, positions[i], values[i]) for i in ids if i in values and i in positions]
        total += auto_lineup(pool, slots).total
    return total


def team_ids(data: LeagueData, roster_id: int, rosters: pl.DataFrame | None = None) -> list[str]:
    frame = data.rosters if rosters is None else rosters
    return frame.filter(pl.col("roster_id") == roster_id)["gsis_id"].to_list()


def waiver_candidates(data: LeagueData, roster_id: int, top_n: int = 25) -> list[Waiver]:
    """Free agents ranked by the extra points they add if the lowest-value player is dropped."""
    ids = team_ids(data, roster_id)
    if not ids:
        return []
    positions = position_of(data)
    base = team_total(data, ids)
    pool = free_agents(data)
    pool_value = ros_value(data, pool)
    shortlist: list[str] = []
    for position in ("QB", "RB", "WR", "TE"):
        of_position = [p for p in pool if positions.get(p) == position]
        shortlist += sorted(of_position, key=lambda p: -pool_value[p])[:CANDIDATES_PER_POSITION]
    ranked = [best_swap(data, ids, c, base) for c in shortlist]
    return sorted(ranked, key=lambda w: -w.delta_mu)[:top_n]


def best_swap(data: LeagueData, ids: list[str], add: str, base: float) -> Waiver:
    """Add `add` and drop whoever costs the least expected points (bye weeks included)."""
    tries = [(team_total(data, [i for i in ids if i != drop] + [add]) - base, drop) for drop in ids]
    gain, drop = max(tries, key=lambda t: (t[0], t[1]))
    return Waiver(add, position_of(data)[add], drop, gain)


def waiver_odds(
    data: LeagueData, my_id: int, adds: list[Waiver], n_sims: int = 20000, seed: int = 0
) -> pl.DataFrame:
    """Playoff and title odds for me before and after each add-drop, on the same random draws.

    `se_title` is the independent-runs standard error of the title change, an upper bound since
    shared draws make the two runs move together.
    """
    before, _ = league_odds(data, None, n_sims, seed, reoptimize=True)
    me = data.roster_ids.index(my_id)
    rows = []
    for w in adds:
        ids = [i for i in team_ids(data, my_id) if i != w.drop_id] + [w.gsis_id]
        rest = data.rosters.filter(pl.col("roster_id") != my_id)
        mine = pl.DataFrame(
            [(my_id, i, position_of(data)[i]) for i in ids], schema=rest.schema, orient="row"
        )
        after, _ = league_odds(data, pl.concat([rest, mine]), n_sims, seed, reoptimize=True)
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


def fit_size(data: LeagueData, ids: list[str], target: int, taken: set[str]) -> list[str]:
    """Drop the lowest-value players, or add the best free agents, until len(ids) == target."""
    ids = list(ids)
    while len(ids) > target:
        values = ros_value(data, ids)
        ids.remove(min(ids, key=lambda i: (values[i], i)))
    if len(ids) < target:
        pool = [p for p in free_agents(data) if p not in taken and p not in ids]
        pool_value = ros_value(data, pool)
        ids += sorted(pool, key=lambda p: (-pool_value[p], p))[: target - len(ids)]
    return ids


def apply_trade(
    data: LeagueData, my_id: int, partner_id: int, give: list[str], get: list[str]
) -> pl.DataFrame:
    """Rosters after the trade, each team kept at its original size."""
    mine, theirs = team_ids(data, my_id), team_ids(data, partner_id)
    if not give or not get:
        raise ValueError("a trade needs at least one player on each side")
    if my_id == partner_id:
        raise ValueError("cannot trade with yourself")
    if not set(give) <= set(mine):
        raise ValueError(f"not on your roster: {sorted(set(give) - set(mine))}")
    if not set(get) <= set(theirs):
        raise ValueError(f"not on the partner's roster: {sorted(set(get) - set(theirs))}")

    new_mine = [i for i in mine if i not in give] + list(get)
    new_theirs = [i for i in theirs if i not in get] + list(give)
    taken = rostered(data) | set(new_mine) | set(new_theirs)
    new_mine = fit_size(data, new_mine, len(mine), taken)
    new_theirs = fit_size(data, new_theirs, len(theirs), taken | set(new_mine))

    positions = position_of(data)
    changed = [
        (rid, gid, positions[gid]) for rid, ids in ((my_id, new_mine), (partner_id, new_theirs))
        for gid in ids
    ]  # fmt: skip
    others = data.rosters.filter(~pl.col("roster_id").is_in([my_id, partner_id]))
    schema = {"roster_id": pl.Int64, "gsis_id": pl.String, "position": pl.String}
    return pl.concat([others, pl.DataFrame(changed, schema=schema, orient="row")])


def evaluate_trade(
    data: LeagueData,
    my_id: int,
    partner_id: int,
    give: list[str],
    get: list[str],
    n_sims: int = 20000,
    seed: int = 0,
) -> pl.DataFrame:
    """Odds before and after for both teams, using the same random draws for both runs."""
    if data.current_week > data.trade_deadline:
        raise ValueError(f"the trade deadline (week {data.trade_deadline}) has passed")
    after_rosters = apply_trade(data, my_id, partner_id, give, get)
    before, _ = league_odds(data, None, n_sims, seed, reoptimize=True)
    after, _ = league_odds(data, after_rosters, n_sims, seed, reoptimize=True)
    rows = []
    for side, rid in (("me", my_id), ("them", partner_id)):
        i = data.roster_ids.index(rid)
        rows.append(
            {
                "side": side,
                "roster_id": rid,
                "team_name": data.team_names[rid],
                "playoff_before": float(before.p_playoffs[i]),
                "playoff_after": float(after.p_playoffs[i]),
                "title_before": float(before.p_title[i]),
                "title_after": float(after.p_title[i]),
                "wins_before": float(before.exp_wins[i]),
                "wins_after": float(after.exp_wins[i]),
            }
        )
    return pl.DataFrame(rows)


POOL_SIZE = 6  # each team's most valuable players considered for a swap
SCREEN_TOL = 2.0  # rest-of-season points either side may lose in the cheap screen
SHORTLIST = 8  # swaps per partner that get a full re-simulation
CONFIRM = 10  # best swaps re-checked on fresh random draws
FINDER_COLUMNS = {
    "partner_id": pl.Int64,
    "give_id": pl.String,
    "get_id": pl.String,
    "my_playoff": pl.Float64,
    "my_title": pl.Float64,
    "their_playoff": pl.Float64,
    "their_title": pl.Float64,
    "se_title": pl.Float64,
}


def trade_pool(data: LeagueData, roster_id: int, n: int = POOL_SIZE) -> list[str]:
    """A team's n players with the most rest-of-season points (zero-value players excluded)."""
    ids = team_ids(data, roster_id)
    values = ros_value(data, ids)
    ranked = sorted((i for i in ids if values[i] > 0), key=lambda i: (-values[i], i))
    return ranked[:n]


def paired_se(before: np.ndarray, after: np.ndarray) -> float:
    """Standard error of the change in a 0/1 outcome measured on the same random draws."""
    diff = after.astype(float) - before.astype(float)
    return float(diff.std() / np.sqrt(diff.size))


def _rerun(
    data: LeagueData, my_id: int, swaps: list[tuple[int, str, str]], n_sims: int, seed: int
) -> list[dict[str, float]]:
    """Both teams' odds change for each (partner, give, get), against one unchanged baseline."""
    before, _ = league_odds(data, None, n_sims, seed, reoptimize=True)
    me = data.roster_ids.index(my_id)
    out = []
    for partner_id, give, get in swaps:
        after, _ = league_odds(
            data,
            apply_trade(data, my_id, partner_id, [give], [get]),
            n_sims,
            seed,
            reoptimize=True,
        )
        them = data.roster_ids.index(partner_id)
        out.append(
            {
                "my_playoff": float(after.p_playoffs[me] - before.p_playoffs[me]),
                "my_title": float(after.p_title[me] - before.p_title[me]),
                "their_playoff": float(after.p_playoffs[them] - before.p_playoffs[them]),
                "their_title": float(after.p_title[them] - before.p_title[them]),
                "se_title": paired_se(before.champion == me, after.champion == me),
            }
        )
    return out


def _both_gain(result: dict[str, float]) -> bool:
    """Both teams' playoff plus title odds rise. Neither alone works: a team near the playoff
    ceiling can only gain title odds, and title odds alone are too noisy."""
    return (
        result["my_playoff"] + result["my_title"] > 0
        and result["their_playoff"] + result["their_title"] > 0
    )


def find_trades(data: LeagueData, my_id: int, n_sims: int = 20000, seed: int = 0) -> pl.DataFrame:
    """One-for-one trades that raise both teams' odds, best for me first.

    Stage 1 screens every swap of two teams' top players by rest-of-season points; stage 2
    re-simulates the best few per partner and keeps those where both teams' playoff plus title odds
    rise; stage 3 re-checks the leaders on fresh draws and reports those
    numbers, so the winner of many candidates is not flattered by its own draws.
    """
    if data.current_week > data.trade_deadline:
        raise ValueError(f"the trade deadline (week {data.trade_deadline}) has passed")
    values = week_values(data)
    mine = team_ids(data, my_id)
    base_mine = team_total(data, mine, values)
    screened: list[tuple[float, int, str, str]] = []
    for partner_id in data.roster_ids:
        if partner_id == my_id:
            continue
        theirs = team_ids(data, partner_id)
        base_theirs = team_total(data, theirs, values)
        local = []
        for give in trade_pool(data, my_id):
            for get in trade_pool(data, partner_id):
                d_me = team_total(data, [i for i in mine if i != give] + [get], values) - base_mine
                d_them = (
                    team_total(data, [i for i in theirs if i != get] + [give], values) - base_theirs
                )
                if min(d_me, d_them) >= -SCREEN_TOL:
                    local.append((min(d_me, d_them), partner_id, give, get))
        screened += sorted(local, key=lambda t: -t[0])[:SHORTLIST]

    swaps = [(p, g, r) for _, p, g, r in screened]
    first = _rerun(data, my_id, swaps, n_sims, seed)
    kept = [(s, r) for s, r in zip(swaps, first, strict=True) if _both_gain(r)]
    kept.sort(key=lambda sr: (-sr[1]["my_title"], -sr[1]["my_playoff"]))
    leaders = [s for s, _ in kept[:CONFIRM]]
    second = _rerun(data, my_id, leaders, n_sims, seed + 1)
    rows: list[dict[str, Any]] = [
        {"partner_id": p, "give_id": g, "get_id": r, **res}
        for (p, g, r), res in zip(leaders, second, strict=True)
        if _both_gain(res)
    ]
    rows.sort(key=lambda r: (-r["my_title"], -r["my_playoff"]))
    return pl.DataFrame(rows, schema=FINDER_COLUMNS)
