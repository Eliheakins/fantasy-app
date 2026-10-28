"""Roster moves: free agents, ranking adds, and applying and evaluating a trade.

Everything here works on one league's LeagueData. Players are skill players (QB, RB, WR, TE) with
projections; each team's K and DEF are its own projections (`LeagueData.kd_slot`), which a move
leaves unchanged. A trade keeps each team's roster size: a team that receives more players than it
gives drops its lowest-value players, and one that receives fewer picks up the best free agents
(an assumption, stated in decisions.md).
"""

from itertools import combinations
from typing import Any, NamedTuple

import numpy as np
import polars as pl

from fantasy.sim.lineup import Player, auto_lineup, lineup_slots
from fantasy.sim.odds import HAZARD, STAY_OUT, LeagueData, league_odds
from fantasy.sim.season import SeasonResult
from fantasy.sim.value import (
    POSITIONS,
    absence_probs,
    conditional_values,
    play_curves,
    replacement_pool,
    season_value,
    values_by_week,
)

CANDIDATES_PER_POSITION = 8
DROP_CANDIDATES = 8  # lowest rest-of-season players considered for a drop


class Waiver(NamedTuple):
    gsis_id: str
    position: str
    drop_id: str
    delta_mu: (
        float  # extra expected points over the rest of the season, depth and replacement counted
    )


def position_of(data: LeagueData) -> dict[str, str]:
    on_rosters = dict(zip(data.rosters["gsis_id"], data.rosters["position"], strict=True))
    return {**data.positions, **on_rosters}


def week_values(data: LeagueData) -> dict[int, dict[str, float]]:
    return values_by_week(data.projections)


def ros_value(data: LeagueData, ids: list[str]) -> dict[str, float]:
    """Projected points over the rest of the season, per player."""
    wanted = data.projections.filter(pl.col("gsis_id").is_in(ids))
    sums = dict(wanted.group_by("gsis_id").agg(pl.col("projection").sum()).iter_rows())
    return {i: float(sums.get(i, 0.0)) for i in ids}


def with_roster(data: LeagueData, roster_id: int, ids: list[str]) -> pl.DataFrame:
    """The league's rosters with `roster_id`'s players replaced by `ids`."""
    rest = data.rosters.filter(pl.col("roster_id") != roster_id)
    positions = position_of(data)
    rows = [(roster_id, i, positions[i]) for i in ids]
    return pl.concat([rest, pl.DataFrame(rows, schema=rest.schema, orient="row")])


def rostered(data: LeagueData, rosters: pl.DataFrame | None = None) -> set[str]:
    return set((data.rosters if rosters is None else rosters)["gsis_id"].to_list())


def free_agents(data: LeagueData, rosters: pl.DataFrame | None = None) -> list[str]:
    """Active players Sleeper lists (data.positions) with a projection and no team in the league."""
    available = set(data.projections["gsis_id"].to_list()) & set(data.positions)
    return sorted(available - rostered(data, rosters))


def team_total(
    data: LeagueData,
    ids: list[str],
    values_by_week: dict[int, dict[str, float]] | None = None,
    slots: list[str] | None = None,
    positions: dict[str, str] | None = None,
) -> float:
    """Expected skill-position points over the rest of the season with best weekly lineups.

    Pass `values_by_week` (from week_values), `slots` and `positions` when scoring many rosters
    to skip recomputing them."""
    slots = lineup_slots(data.roster_positions) if slots is None else slots
    positions = position_of(data) if positions is None else positions
    total = 0.0
    for values in (week_values(data) if values_by_week is None else values_by_week).values():
        pool = [Player(i, positions[i], values[i]) for i in ids if i in values and i in positions]
        total += auto_lineup(pool, slots).total
    return total


def team_ids(data: LeagueData, roster_id: int, rosters: pl.DataFrame | None = None) -> list[str]:
    frame = data.rosters if rosters is None else rosters
    return frame.filter(pl.col("roster_id") == roster_id)["gsis_id"].to_list()


class Valuer:
    """Expected points over the rest of the season for a set of players, counting absences and
    free-agent stand-ins (see sim/value.py). Build once per league and reuse."""

    def __init__(self, data: LeagueData) -> None:
        self.data = data
        self.slots = lineup_slots(data.roster_positions)
        self.positions = position_of(data)
        # points when playing, by week; absences are weighed separately
        self.values = conditional_values(data.projections)
        weeks = len(self.values)
        curves = play_curves(data.projections, sorted(self.values))
        self.absence = {
            g: absence_probs(curves.get(g, (1.0,)), weeks, HAZARD, STAY_OUT) for g in self.positions
        }
        self.replacements = replacement_pool(free_agents(data), self.positions, self.values)

    def __call__(self, ids: list[str]) -> float:
        return season_value(
            self.slots, self.positions, self.values, ids, self.absence, self.replacements
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
    ros = _ros_all(data)
    free = sorted(free_agents(data), key=lambda i: (-ros.get(i, 0.0), i))
    new_mine = _fit(new_mine, len(mine), taken, ros, free)
    new_theirs = _fit(new_theirs, len(theirs), taken | set(new_mine), ros, free)

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


POOL_SIZE = 6  # each team's most valuable players considered for a swap
SIZES = ((1, 1), (1, 2), (2, 1), (2, 2))  # (players I give, players I get)
SCREEN_TOL = 2.0  # rest-of-season points either side may lose in the cheap screen
SCREEN_KEEP = 24  # per partner, after the points screen, for the depth-aware ranking
SHORTLIST = 6  # per partner, after the depth-aware ranking, for a full re-simulation
CONFIRM = 20  # best swaps re-checked on fresh random draws
# A need swap may cost either side up to one percentage point of (playoff + title) odds. Chosen
# as about twice the paired Monte Carlo error of a single odds change at 20,000 sims (0.3 to
# 0.5 points on real data), so a swap is not rejected for noise alone, yet a visible loss is.
ODDS_TOL = 0.01
NEED_MIN = 3.0  # rest-of-season points (about half a point a week) that count as a need filled
SURPLUS_COST = 1.0  # a player whose loss costs less than this (points) is surplus
PER_POSITION = 2  # best players per position in a candidate pool
SURPLUS_POOL = 3  # most valuable surplus bench players added to a candidate pool
NEED_KEEP = 8  # per partner, the most even need-fit swaps sent to simulation
BENCH_SPARES = 2  # benchmark starters kept per position, in case a team already holds the first
FINDER_COLUMNS: dict[str, pl.DataType | type[pl.DataType]] = {
    "partner_id": pl.Int64,
    "give_ids": pl.List(pl.String),
    "get_ids": pl.List(pl.String),
    "my_playoff": pl.Float64,
    "my_title": pl.Float64,
    "their_playoff": pl.Float64,
    "their_title": pl.Float64,
    "se_title": pl.Float64,
    "kind": pl.String,
    "my_fit": pl.Float64,
    "their_fit": pl.Float64,
    "my_needs": pl.List(pl.String),
    "their_needs": pl.List(pl.String),
}


def trade_pool(data: LeagueData, roster_id: int, n: int = POOL_SIZE) -> list[str]:
    """A team's n players with the most rest-of-season points (zero-value players excluded)."""
    ids = team_ids(data, roster_id)
    values = ros_value(data, ids)
    ranked = sorted((i for i in ids if values[i] > 0), key=lambda i: (-values[i], i))
    return ranked[:n]


def benchmarks(data: LeagueData, valuer: Valuer) -> dict[str, list[str]]:
    """Per position, rostered players of typical starter quality (the last starter on an average
    team): the league's rank `teams x starting slots` by rest-of-season points, plus the next
    ones. Adding one to a roster measures how much a starter at that position would help."""
    ros = ros_value(data, data.rosters["gsis_id"].to_list())
    out: dict[str, list[str]] = {}
    for position in POSITIONS:
        ids = sorted(
            (i for i in ros if valuer.positions.get(i) == position), key=lambda i: (-ros[i], i)
        )
        rank = len(data.roster_ids) * max(valuer.slots.count(position), 1)
        start = max(min(rank, len(ids)) - 1, 0)
        out[position] = ids[start : start + BENCH_SPARES]
    return out


class TeamNeeds:
    """One team's positional need and surplus, from its own best weekly lineups.

    need[position]: expected points over the rest of the season that adding one typical starter at
    that position would give the team (FLEX and replacement stand-ins counted by the Valuer).
    cost(give): points lost by giving those players up; about 0 for a bench player behind a
    healthy starter. A swap's fit is the need it fills minus the cost of what it gives up."""

    def __init__(self, valuer: Valuer, ids: list[str], bench: dict[str, list[str]]) -> None:
        self.valuer, self.ids = valuer, list(ids)
        self.base = self._value(self.ids)
        self.bench = bench
        self._cost: dict[tuple[str, ...], float] = {}
        self._opened: dict[tuple[str, ...], float] = {}
        self._gain: dict[str, float] = {}
        self.need = {
            position: self.gain(next((b for b in spares if b not in self.ids), ""))
            for position, spares in bench.items()
        }

    def _value(self, ids: list[str]) -> float:
        """Best weekly lineups with free-agent stand-ins but no absence discount, so a spare
        behind a healthy starter is surplus rather than insurance."""
        v = self.valuer
        return season_value(v.slots, v.positions, v.values, ids, {}, v.replacements)

    def gain(self, player_id: str) -> float:
        """Points a single added player gives this team (0 for an empty id)."""
        if player_id and player_id not in self._gain:
            self._gain[player_id] = max(0.0, self._value([*self.ids, player_id]) - self.base)
        return self._gain.get(player_id, 0.0)

    def cost(self, give: tuple[str, ...]) -> float:
        key = tuple(sorted(give))
        if key not in self._cost:
            self._cost[key] = self.base - self._value([i for i in self.ids if i not in key])
        return self._cost[key]

    def opened(self, lost: tuple[str, ...]) -> float:
        """New need created by giving `lost` up: at each of their positions, how much more a
        typical starter would add to the team without them than with them."""
        key = tuple(sorted(lost))
        if key not in self._opened:
            rest = [i for i in self.ids if i not in key]
            base = self._value(rest)
            total = 0.0
            for position in {self.valuer.positions[i] for i in key}:
                spare = next((b for b in self.bench[position] if b not in rest), None)
                after = max(0.0, self._value([*rest, spare]) - base) if spare else 0.0
                total += max(0.0, after - self.need[position])
            self._opened[key] = total
        return self._opened[key]

    def fit(self, give: tuple[str, ...], get: tuple[str, ...]) -> tuple[float, list[str]]:
        """Need fit of a swap and the positions of need it fills: the need filled (what the best
        player received at a position of need adds, capped at that need) minus the need opened
        by what is given up. Positions that give and get equally cancel, so a like-for-like swap
        fits 0 however much better the player is."""
        at = self.valuer.positions
        net = {p: sum(at[g] == p for g in get) - sum(at[g] == p for g in give) for p in POSITIONS}
        filled = [p for p, n in net.items() if n > 0 and self.need[p] >= NEED_MIN]
        credit = sum(
            min(self.need[p], max(self.gain(g) for g in get if at[g] == p)) for p in filled
        )
        lost: list[str] = []
        for position in (p for p, n in net.items() if n < 0):
            of_position = sorted(
                (g for g in give if at[g] == position), key=lambda g: -self.cost((g,))
            )
            lost += of_position[: -net[position]]
        return credit - (self.opened(tuple(lost)) if lost else 0.0), filled

    def pool(self, ros: dict[str, float]) -> list[str]:
        """Candidates to trade away: the best players at each position plus the most valuable
        surplus bench players, who are the natural currency for a need swap."""
        at = self.valuer.positions
        live = sorted((i for i in self.ids if ros.get(i, 0.0) > 0), key=lambda i: (-ros[i], i))
        picked = [i for p in POSITIONS for i in [x for x in live if at[x] == p][:PER_POSITION]]
        surplus = [i for i in live if i not in picked and self.cost((i,)) < SURPLUS_COST]
        return picked + surplus[:SURPLUS_POOL]


def swap_kind(result: dict[str, float], my_fit: float, their_fit: float) -> str | None:
    """ "win-win" if both teams' odds rise, "need swap" if neither loses more than ODDS_TOL and
    both fill a need (fit of at least NEED_MIN), else None (rejected)."""
    if _both_gain(result):
        return "win-win"
    mine = result["my_playoff"] + result["my_title"]
    theirs = result["their_playoff"] + result["their_title"]
    if min(mine, theirs) >= -ODDS_TOL and min(my_fit, their_fit) >= NEED_MIN:
        return "need swap"
    return None


def rank_key(row: dict[str, Any]) -> tuple[float, float, float]:
    """Need fit first (the weaker side's; below NEED_MIN it counts as none, a negative one as is),
    then my title and playoff odds change."""
    weaker = min(row["my_fit"], row["their_fit"])
    return (
        -(weaker if weaker >= NEED_MIN else min(weaker, 0.0)),
        -row["my_title"],
        -row["my_playoff"],
    )


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


def _pickup(ids: list[str], taken: set[str], ros: dict[str, float], free: list[str]) -> list[str]:
    """A roster after its own best waiver move: drop the lowest player, add the best free agent."""
    worst = min(ids, key=lambda i: (ros.get(i, 0.0), i))
    return _fit([i for i in ids if i != worst], len(ids), taken, ros, free)


def _ros_all(data: LeagueData) -> dict[str, float]:
    sums = data.projections.group_by("gsis_id").agg(pl.col("projection").sum()).iter_rows()
    return {g: float(v) for g, v in sums}


def _both_gain(result: dict[str, float]) -> bool:
    """Both teams' playoff plus title odds rise. Neither alone works: a team near the playoff
    ceiling can only gain title odds, and title odds alone are too noisy."""
    return (
        result["my_playoff"] + result["my_title"] > 0
        and result["their_playoff"] + result["their_title"] > 0
    )


Swap = tuple[int, tuple[str, ...], tuple[str, ...]]  # partner roster id, I give, I get


def _rerun(
    data: LeagueData, my_id: int, swaps: list[Swap], n_sims: int, seed: int
) -> list[dict[str, float]]:
    """Both teams' odds change for each swap, on shared random draws.

    A team that ends up with an open roster spot is compared with itself after its own best
    waiver move, so a free pickup it could make anyway is not credited to the trade."""
    ros, free, taken = _ros_all(data), sorted(free_agents(data)), rostered(data)
    free.sort(key=lambda i: (-ros.get(i, 0.0), i))
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


def find_trades(data: LeagueData, my_id: int, n_sims: int = 20000, seed: int = 0) -> pl.DataFrame:
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
    values, valuer = week_values(data), Valuer(data)
    slots, positions = valuer.slots, valuer.positions  # team_total reuses them across ~10k calls
    ros, taken = _ros_all(data), rostered(data)
    free = sorted(free_agents(data), key=lambda i: (-ros.get(i, 0.0), i))
    mine = team_ids(data, my_id)
    pool_me = trade_pool(data, my_id)
    bench = benchmarks(data, valuer)
    needs = {r: TeamNeeds(valuer, team_ids(data, r), bench) for r in data.roster_ids}

    def reference(ids: list[str], opens_a_spot: bool) -> tuple[float, float]:
        ref = _pickup(ids, taken, ros, free) if opens_a_spot else ids
        return team_total(data, ref, values, slots, positions), valuer(ref)

    swaps: list[Swap] = []
    for partner_id in data.roster_ids:
        if partner_id == my_id:
            continue
        theirs = team_ids(data, partner_id)
        refs = {
            (me_open, them_open): (reference(mine, me_open), reference(theirs, them_open))
            for me_open, them_open in ((False, False), (True, False), (False, True))
        }
        local: list[Screened] = []
        pool_them = trade_pool(data, partner_id)
        for gives, gets in SIZES:
            for give in combinations(pool_me, gives):
                for get in combinations(pool_them, gets):
                    new_me = _fit(
                        [i for i in mine if i not in give] + list(get), len(mine), taken, ros, free
                    )
                    new_them = _fit(
                        [i for i in theirs if i not in get] + list(give),
                        len(theirs),
                        taken | set(new_me),
                        ros,
                        free,
                    )
                    (ref_me, vref_me), (ref_them, vref_them) = refs[(gives > gets, gets > gives)]
                    d_me = team_total(data, new_me, values, slots, positions) - ref_me
                    d_them = team_total(data, new_them, values, slots, positions) - ref_them
                    if min(d_me, d_them) >= -SCREEN_TOL:
                        local.append(
                            Screened(
                                min(d_me, d_them), give, get, new_me, new_them, vref_me, vref_them
                            )
                        )
        points = [(p, g, r) for _, p, g, r in _depth_ranked(local, partner_id, valuer)]
        want = _need_swaps(needs[my_id], needs[partner_id], ros)
        swaps += list(dict.fromkeys(points + [(partner_id, g, r) for g, r in want]))

    def label(result: dict[str, float], swap: Swap) -> dict[str, Any] | None:
        partner_id, give, get = swap
        fit_me, fills_me = needs[my_id].fit(give, get)
        fit_them, fills_them = needs[partner_id].fit(get, give)
        kind = swap_kind(result, fit_me, fit_them)
        if kind is None:
            return None
        return {
            "partner_id": partner_id, "give_ids": list(give), "get_ids": list(get), **result,
            "kind": kind, "my_fit": fit_me, "their_fit": fit_them,
            "my_needs": fills_me, "their_needs": fills_them,
        }  # fmt: skip

    first = _rerun(data, my_id, swaps, n_sims, seed)
    kept = [row for s, r in zip(swaps, first, strict=True) if (row := label(r, s))]
    kept.sort(key=rank_key)
    leaders: list[Swap] = [
        (r["partner_id"], tuple(r["give_ids"]), tuple(r["get_ids"])) for r in kept[:CONFIRM]
    ]
    second = _rerun(data, my_id, leaders, n_sims, seed + 1)
    rows = [row for s, r in zip(leaders, second, strict=True) if (row := label(r, s))]
    rows.sort(key=rank_key)
    return pl.DataFrame(drop_addons(rows, position_of(data)), schema=FINDER_COLUMNS)


def _is_addon(big: dict[str, Any], small: dict[str, Any], positions: dict[str, str]) -> bool:
    """`big` is `small` plus one like-for-like leg (same position each way) that moves my
    playoff plus title odds by less than ODDS_TOL."""
    if big["partner_id"] != small["partner_id"]:
        return False
    extra_give = set(big["give_ids"]) - set(small["give_ids"])
    extra_get = set(big["get_ids"]) - set(small["get_ids"])
    give_subset = set(small["give_ids"]) < set(big["give_ids"])
    if not (give_subset and set(small["get_ids"]) < set(big["get_ids"])):
        return False
    if len(extra_give) != 1 or len(extra_get) != 1:
        return False
    if positions[next(iter(extra_give))] != positions[next(iter(extra_get))]:
        return False
    odds = lambda r: r["my_playoff"] + r["my_title"]  # noqa: E731
    return abs(odds(big) - odds(small)) < ODDS_TOL


def drop_addons(rows: list[dict[str, Any]], positions: dict[str, str]) -> list[dict[str, Any]]:
    """Rows without the ones that are a smaller listed swap plus a like-for-like add-on leg."""
    return [r for r in rows if not any(_is_addon(r, s, positions) for s in rows)]


def position_strength(data: LeagueData, valuer: Valuer | None = None) -> pl.DataFrame:
    """Each team's value over replacement by position: roster_id, position, vor_per_week, rank.

    For every remaining week a team's best lineup is scored against the replacement level at
    each starter's position (the best stand-in free agent that week); the average per week is
    summed by position. Rank 1 is the strongest team at that position."""
    valuer = valuer or Valuer(data)
    rows: list[tuple[int, str, float]] = []
    floor = {
        week: {p.position: p.value for p in reversed(valuer.replacements.get(week, []))}
        for week in valuer.values
    }
    for roster_id in data.roster_ids:
        ids = team_ids(data, roster_id)
        totals = dict.fromkeys(POSITIONS, 0.0)
        for week, values in valuer.values.items():
            pool = [
                Player(i, valuer.positions[i], values[i])
                for i in ids
                if i in values and i in valuer.positions
            ]
            for pid in auto_lineup(pool, valuer.slots).players:
                player = next(p for p in pool if p.id == pid)
                totals[player.position] += max(
                    0.0, player.value - floor[week].get(player.position, 0.0)
                )
        weeks = max(len(valuer.values), 1)
        rows += [(roster_id, pos, total / weeks) for pos, total in totals.items()]
    frame = pl.DataFrame(rows, schema=["roster_id", "position", "vor_per_week"], orient="row")
    return frame.with_columns(
        pl.col("vor_per_week")
        .rank("min", descending=True)
        .over("position")
        .cast(pl.Int64)
        .alias("rank")
    )
