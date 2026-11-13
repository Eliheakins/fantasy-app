"""Trades: apply one, evaluate one, and search for the ones that help both teams.

A trade keeps each team's roster size: a team that receives more players than it gives drops its
lowest-value players, and one that receives fewer picks up the best free agents (an assumption,
stated in decisions.md). `find_trades` is built from named steps (screen, rank, simulate, label,
re-check); the labels, ranking and de-duplication live in `trade_labels`.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Any, NamedTuple

import numpy as np
import polars as pl

from fantasy.sim.needs import NEED_MIN, TeamNeeds, benchmarks
from fantasy.sim.odds import DEFAULT_SIMS, LeagueData, league_odds
from fantasy.sim.roster import (
    Valuer,
    free_agents,
    position_of,
    ros_value,
    rostered,
    team_ids,
    team_total,
    week_values,
    with_roster,
)
from fantasy.sim.season import SeasonResult
from fantasy.sim.trade_labels import FINDER_COLUMNS, drop_addons, rank_key, swap_kind

POOL_SIZE = 6  # each team's most valuable players considered for a swap
SIZES = ((1, 1), (1, 2), (2, 1), (2, 2))  # (players I give, players I get)
SCREEN_TOL = 2.0  # rest-of-season points either side may lose in the cheap screen
SCREEN_KEEP = 24  # per partner, after the points screen, for the depth-aware ranking
SHORTLIST = 6  # per partner, after the depth-aware ranking, for a full re-simulation
CONFIRM = 20  # best swaps re-checked on fresh random draws
NEED_KEEP = 8  # per partner, the most even need-fit swaps sent to simulation


def apply_trade(
    data: LeagueData, my_id: int, partner_id: int, give: list[str], get: list[str]
) -> pl.DataFrame:
    """Rosters after the trade, each team kept at its original size."""
    mine, theirs = team_ids(data, my_id), team_ids(data, partner_id)
    if not give or not get:
        raise ValueError("a trade needs at least one player on each side")
    if my_id == partner_id:
        raise ValueError("cannot trade with yourself")
    if len(set(give)) != len(give) or len(set(get)) != len(get):
        raise ValueError("a player appears twice in the trade")
    if not set(give) <= set(mine):
        raise ValueError(f"not on your roster: {sorted(set(give) - set(mine))}")
    if not set(get) <= set(theirs):
        raise ValueError(f"not on the partner's roster: {sorted(set(get) - set(theirs))}")

    ros = _ros_all(data)
    new_mine, new_theirs = _traded_rosters(
        mine, theirs, give, get, rostered(data), ros, _free_by_value(data, ros)
    )

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
    n_sims: int = DEFAULT_SIMS,
    seed: int = 0,
) -> pl.DataFrame:
    """Odds before and after for both teams, using the same random draws for both runs."""
    if data.current_week > data.trade_deadline:
        raise ValueError(f"the trade deadline (week {data.trade_deadline}) has passed")
    after_rosters = apply_trade(data, my_id, partner_id, give, get)
    before = league_odds(data, None, n_sims, seed, reoptimize=True)
    after = league_odds(data, after_rosters, n_sims, seed, reoptimize=True)
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


def _fit(
    ids: list[str], target: int, taken: set[str], ros: dict[str, float], free: list[str]
) -> list[str]:
    """Drop the lowest rest-of-season players, or add the best free agents, to reach `target`.
    Takes precomputed values so thousands of candidates stay cheap."""
    ids = list(ids)
    while len(ids) > target:
        ids.remove(min(ids, key=lambda i: (ros.get(i, 0.0), i)))
    for candidate in free:
        if len(ids) >= target:
            break
        if candidate not in taken and candidate not in ids:
            ids.append(candidate)
    return ids


def _traded_rosters(
    mine: list[str],
    theirs: list[str],
    give: Sequence[str],
    get: Sequence[str],
    taken: set[str],
    ros: dict[str, float],
    free: list[str],
) -> tuple[list[str], list[str]]:
    """Both rosters after a swap, each refit to its original size (`_fit`)."""
    new_mine = _fit([i for i in mine if i not in give] + list(get), len(mine), taken, ros, free)
    new_theirs = _fit(
        [i for i in theirs if i not in get] + list(give),
        len(theirs),
        taken | set(new_mine),
        ros,
        free,
    )
    return new_mine, new_theirs


def _pickup(ids: list[str], taken: set[str], ros: dict[str, float], free: list[str]) -> list[str]:
    """A roster after its own best waiver move: drop the lowest player, add the best free agent."""
    worst = min(ids, key=lambda i: (ros.get(i, 0.0), i))
    return _fit([i for i in ids if i != worst], len(ids), taken, ros, free)


def _ros_all(data: LeagueData) -> dict[str, float]:
    sums = data.projections.group_by("gsis_id").agg(pl.col("projection").sum()).iter_rows()
    return {g: float(v) for g, v in sums}


def _free_by_value(data: LeagueData, ros: dict[str, float]) -> list[str]:
    """Free agents, best rest-of-season points first."""
    return sorted(free_agents(data), key=lambda i: (-ros.get(i, 0.0), i))


Swap = tuple[int, tuple[str, ...], tuple[str, ...]]  # partner roster id, I give, I get


def _rerun(
    data: LeagueData, my_id: int, swaps: list[Swap], n_sims: int, seed: int
) -> list[dict[str, float]]:
    """Both teams' odds change for each swap, on shared random draws.

    A team that ends up with an open roster spot is compared with itself after its own best
    waiver move, so a free pickup it could make anyway is not credited to the trade."""
    ros, taken = _ros_all(data), rostered(data)
    free = _free_by_value(data, ros)
    base = league_odds(data, None, n_sims, seed, reoptimize=True)
    pickup_worlds: dict[int, SeasonResult] = {}

    def world_with_pickup(roster_id: int) -> SeasonResult:
        if roster_id not in pickup_worlds:
            rosters = with_roster(
                data, roster_id, _pickup(team_ids(data, roster_id), taken, ros, free)
            )
            pickup_worlds[roster_id] = league_odds(data, rosters, n_sims, seed, reoptimize=True)
        return pickup_worlds[roster_id]

    me = data.roster_ids.index(my_id)
    out = []
    for partner_id, give, get in swaps:
        my_before = world_with_pickup(my_id) if len(give) > len(get) else base
        their_before = world_with_pickup(partner_id) if len(get) > len(give) else base
        rosters = apply_trade(data, my_id, partner_id, list(give), list(get))
        after = league_odds(data, rosters, n_sims, seed, reoptimize=True)
        them = data.roster_ids.index(partner_id)
        out.append(
            {
                "my_playoff": float(after.p_playoffs[me] - my_before.p_playoffs[me]),
                "my_title": float(after.p_title[me] - my_before.p_title[me]),
                "their_playoff": float(after.p_playoffs[them] - their_before.p_playoffs[them]),
                "their_title": float(after.p_title[them] - their_before.p_title[them]),
                "se_title": paired_se(my_before.champion == me, after.champion == me),
            }
        )
    return out


class Screened(NamedTuple):
    """A swap that passed the points screen, with both rosters after it and each side's
    depth-aware reference value."""

    worst_loss: float  # the smaller of the two sides' rest-of-season point changes
    give: tuple[str, ...]
    get: tuple[str, ...]
    new_me: list[str]
    new_them: list[str]
    vref_me: float
    vref_them: float


def _depth_ranked(
    local: list[Screened], partner_id: int, valuer: Valuer
) -> list[tuple[float, int, tuple[str, ...], tuple[str, ...]]]:
    """Stage 2: the best screened swaps with one partner, by depth-aware value gain."""
    best = sorted(local, key=lambda c: -c.worst_loss)[:SCREEN_KEEP]
    scored = [
        (
            min(valuer(c.new_me) - c.vref_me, valuer(c.new_them) - c.vref_them),
            partner_id,
            c.give,
            c.get,
        )
        for c in best
    ]
    return sorted(scored, key=lambda t: -t[0])[:SHORTLIST]


Swap2 = tuple[tuple[str, ...], tuple[str, ...]]  # I give, I get


def _need_swaps(me: TeamNeeds, them: TeamNeeds, ros: dict[str, float]) -> list[Swap2]:
    """Swaps with one partner where both sides fill a need, the most even in rest-of-season
    points first (the ones a partner might also accept; the simulation then decides)."""
    pool_me, pool_them = me.pool(ros), them.pool(ros)
    found: list[tuple[float, float, tuple[str, ...], tuple[str, ...]]] = []
    for gives, gets in SIZES:
        for give in combinations(pool_me, gives):
            for get in combinations(pool_them, gets):
                fit = min(me.fit(give, get)[0], them.fit(get, give)[0])
                if fit >= NEED_MIN:
                    gap = abs(sum(ros[i] for i in give) - sum(ros[i] for i in get))
                    found.append((gap, -fit, give, get))
    found.sort()
    return [(g, r) for _, _, g, r in found[:NEED_KEEP]]


@dataclass(frozen=True)
class _Search:
    """What `find_trades` computes once per league and reuses for every partner."""

    data: LeagueData
    my_id: int
    valuer: Valuer
    values: dict[int, dict[str, float]]  # week_values, so team_total skips recomputing them
    ros: dict[str, float]
    taken: set[str]
    free: list[str]  # free agents, best rest-of-season points first
    needs: dict[int, TeamNeeds]
    mine: list[str]
    pool_me: list[str]


def _start_search(data: LeagueData, my_id: int) -> _Search:
    valuer = Valuer(data)
    ros = _ros_all(data)
    return _Search(
        data=data,
        my_id=my_id,
        valuer=valuer,
        values=week_values(data),
        ros=ros,
        taken=rostered(data),
        free=_free_by_value(data, ros),
        needs={
            r: TeamNeeds(valuer, team_ids(data, r), benchmarks(data, valuer))
            for r in data.roster_ids
        },
        mine=team_ids(data, my_id),
        pool_me=trade_pool(data, my_id),
    )


def _total(s: _Search, ids: list[str]) -> float:
    return team_total(s.data, ids, s.values, s.valuer.slots, s.valuer.positions)


def _reference(s: _Search, ids: list[str], opens_a_spot: bool) -> tuple[float, float]:
    """A roster's points and depth-aware value before a swap: as it is, or after its own best
    waiver move when the swap would leave it a spot open."""
    ref = _pickup(ids, s.taken, s.ros, s.free) if opens_a_spot else ids
    return _total(s, ref), s.valuer(ref)


def _screened(
    s: _Search,
    theirs: list[str],
    refs: dict[tuple[bool, bool], tuple[tuple[float, float], tuple[float, float]]],
    give: tuple[str, ...],
    get: tuple[str, ...],
) -> Screened | None:
    """Stage 1 for one swap: both rosters after it, kept only if neither side loses more than
    SCREEN_TOL rest-of-season points."""
    new_me, new_them = _traded_rosters(s.mine, theirs, give, get, s.taken, s.ros, s.free)
    (ref_me, vref_me), (ref_them, vref_them) = refs[(len(give) > len(get), len(get) > len(give))]
    d_me = _total(s, new_me) - ref_me
    d_them = _total(s, new_them) - ref_them
    if min(d_me, d_them) < -SCREEN_TOL:
        return None
    return Screened(min(d_me, d_them), give, get, new_me, new_them, vref_me, vref_them)


def _points_route(s: _Search, partner_id: int) -> list[Swap]:
    """Stages 1 and 2 with one partner: every swap of the two teams' top players screened by
    rest-of-season points, then the survivors ranked by depth-aware value."""
    theirs = team_ids(s.data, partner_id)
    refs = {
        (me_open, them_open): (_reference(s, s.mine, me_open), _reference(s, theirs, them_open))
        for me_open, them_open in ((False, False), (True, False), (False, True))
    }
    pool_them = trade_pool(s.data, partner_id)
    local = [
        kept
        for gives, gets in SIZES
        for give in combinations(s.pool_me, gives)
        for get in combinations(pool_them, gets)
        if (kept := _screened(s, theirs, refs, give, get))
    ]
    return [(p, g, r) for _, p, g, r in _depth_ranked(local, partner_id, s.valuer)]


def _partner_swaps(s: _Search, partner_id: int) -> list[Swap]:
    """Candidate swaps with one partner from both routes, each listed once."""
    points = _points_route(s, partner_id)
    want = _need_swaps(s.needs[s.my_id], s.needs[partner_id], s.ros)
    return list(dict.fromkeys(points + [(partner_id, g, r) for g, r in want]))


def _label(s: _Search, result: dict[str, float], swap: Swap) -> dict[str, Any] | None:
    """The finder row for a simulated swap, or None if it is neither a win-win nor a need swap."""
    partner_id, give, get = swap
    fit_me, fills_me = s.needs[s.my_id].fit(give, get)
    fit_them, fills_them = s.needs[partner_id].fit(get, give)
    kind = swap_kind(result, fit_me, fit_them)
    if kind is None:
        return None
    return {
        "partner_id": partner_id, "give_ids": list(give), "get_ids": list(get), **result,
        "kind": kind, "my_fit": fit_me, "their_fit": fit_them,
        "my_needs": fills_me, "their_needs": fills_them,
    }  # fmt: skip


def _simulated_rows(s: _Search, swaps: list[Swap], n_sims: int, seed: int) -> list[dict[str, Any]]:
    """Simulate the swaps on one set of draws and keep the labelled ones, best first."""
    results = _rerun(s.data, s.my_id, swaps, n_sims, seed)
    rows = [row for sw, r in zip(swaps, results, strict=True) if (row := _label(s, r, sw))]
    return sorted(rows, key=rank_key)


def find_trades(
    data: LeagueData, my_id: int, n_sims: int = DEFAULT_SIMS, seed: int = 0
) -> pl.DataFrame:
    """Trades (1 for 1, 1 for 2, 2 for 1, 2 for 2) that fill both teams' positions of need, best
    need fit first. Every row is labelled "win-win" (both teams' playoff plus title odds rise) or
    "need swap" (neither loses more than ODDS_TOL, both fill a need), with its need fit.

    Candidates come from two sources. Points route: stage 1 screens every swap of two teams' top
    players by change in rest-of-season points and stage 2 ranks the survivors by depth-aware value
    (finds win-wins). Need route: each team's best players per position plus its surplus bench
    players, ranked by need fit (finds need swaps). Both are re-simulated; the leaders are
    re-checked on fresh draws and those numbers are reported, so the winner of many candidates is
    not flattered by its own draws. A side with an open roster spot is compared with itself after
    its own waiver move. Nothing here says the partner will accept.
    """
    if data.current_week > data.trade_deadline:
        raise ValueError(f"the trade deadline (week {data.trade_deadline}) has passed")
    s = _start_search(data, my_id)
    swaps = [sw for pid in data.roster_ids if pid != my_id for sw in _partner_swaps(s, pid)]
    kept = _simulated_rows(s, swaps, n_sims, seed)
    leaders: list[Swap] = [
        (r["partner_id"], tuple(r["give_ids"]), tuple(r["get_ids"])) for r in kept[:CONFIRM]
    ]
    rows = _simulated_rows(s, leaders, n_sims, seed + 1)
    return pl.DataFrame(drop_addons(rows, position_of(data)), schema=FINDER_COLUMNS)
