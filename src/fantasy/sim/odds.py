"""Turn projections, spreads and rosters into season odds for one league.

For each team and remaining week: the best lineup by projected points (or, for the week in
progress, the starters already set, with realized points counted), its mean, its weekly
variance (player spread scaled from the projection, with measured correlations between
teammates), and a persistent per-player error shared by every week of one simulated season.

Constants marked provisional are replaced when the backtest or E3-6 / E3-7 give measured values.
"""

import zlib
from dataclasses import dataclass, field

import numpy as np
import polars as pl

from fantasy.sim.lineup import (
    Player,
    auto_lineup,
    constant_slot_count,
    lineup_slots,
    lineup_with_locks,
)
from fantasy.sim.season import SeasonInputs, SeasonResult, simulate_season

# Persistent per-player error, points a game: sd of 5-game mean error beyond what weekly noise
# explains, from walk-forward projections 2018 to 2025, averaged over both leagues' scoring.
TAU = {"QB": 1.5, "RB": 1.7, "WR": 0.8, "TE": 0.55}
DRIFT_SD = 2.0  # provisional weekly roster drift per team
PLAYOFF_WEEKS = 3


@dataclass(frozen=True)
class CurrentWeek:
    """A team's week in progress: points already scored and who is still to play."""

    realized: float
    open_players: tuple[Player, ...]  # set starters whose points are not in yet
    open_k: int
    open_def: int
    locked_starters: frozenset[str] = frozenset()  # set starters who have already scored


@dataclass(frozen=True)
class LeagueData:
    roster_ids: list[int]
    team_names: dict[int, str]
    current_week: int
    playoff_start: int
    roster_positions: list[str]
    rosters: pl.DataFrame  # roster_id, gsis_id, position (skill players on each roster)
    projections: pl.DataFrame  # gsis_id, week, projection
    cv: dict[str, float]  # position -> spread scale
    pair_rho: dict[tuple[str, str], float]  # teammates by role, both orders
    pairings: dict[int, list[tuple[int, int]]]  # week -> [(roster id a, roster id b)]
    wins0: dict[int, float]
    points0: dict[int, float]
    k_mean: float
    k_var: float
    def_mean: float
    def_var: float
    current: dict[int, CurrentWeek] = field(default_factory=dict)
    positions: dict[str, str] = field(default_factory=dict)  # gsis_id -> position, free agents too
    trade_deadline: int = 99  # last week trades are allowed
    league_id: str = ""
    played: frozenset[str] = frozenset()  # everyone who has scored this week, any roster


def lineup_moments(
    players: list[Player], cv: dict[str, float], rho: dict[tuple[str, str], float]
) -> tuple[float, float, float]:
    """(mean, total variance, persistent variance) of a lineup's points in one week."""
    ordered = sorted(players, key=lambda p: (-p.value, p.id))
    seen: dict[str, int] = {}
    roles, sds = [], []
    for p in ordered:
        seen[p.position] = seen.get(p.position, 0) + 1
        roles.append(f"{p.position}{seen[p.position]}")
        sds.append(p.value * cv[p.position])
    var = sum(s * s for s in sds)
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            var += 2 * rho.get((roles[i], roles[j]), 0.0) * sds[i] * sds[j]
    mean = sum(p.value for p in ordered)
    persistent = sum(TAU[p.position] ** 2 for p in ordered)
    return mean, var, persistent


def player_error(gsis_id: str, n_sims: int, seed: int) -> np.ndarray:
    """A player's persistent error draws, the same in every scenario for the same seed."""
    z = np.random.default_rng([seed, zlib.crc32(gsis_id.encode())]).standard_normal(n_sims)
    return z


def build_inputs(
    data: LeagueData,
    rosters: pl.DataFrame | None,
    n_sims: int,
    seed: int,
    reoptimize: bool = False,
) -> SeasonInputs:
    """`reoptimize` refills this week's unplayed slots with the best available players instead
    of keeping the lineup set in Sleeper. Move evaluators use it for both the before and after
    runs, so an acquired player can fill the slot of one traded away."""
    rosters = data.rosters if rosters is None else rosters
    weeks = list(range(data.current_week, data.playoff_start + PLAYOFF_WEEKS))
    slots = lineup_slots(data.roster_positions)
    constants = constant_slot_count(data.roster_positions)
    index = {rid: i for i, rid in enumerate(data.roster_ids)}
    n_teams, n_weeks = len(data.roster_ids), len(weeks)
    mean = np.zeros((n_teams, n_weeks))
    noise_sd = np.zeros((n_teams, n_weeks))
    shift = np.zeros((n_teams, n_weeks, n_sims))
    by_week = {
        w: dict(zip(g["gsis_id"], g["projection"], strict=True))
        for (w,), g in data.projections.group_by("week")
    }

    for rid, t in index.items():
        team = rosters.filter(pl.col("roster_id") == rid)
        position = dict(zip(team["gsis_id"], team["position"], strict=True))
        errors = {g: TAU[pos] * player_error(g, n_sims, seed) for g, pos in position.items()}
        for w, week in enumerate(weeks):
            state = data.current.get(rid) if week == data.current_week else None
            if state is not None:
                # a player traded away this week leaves the lineup; acquired players start benched
                lineup = [p for p in state.open_players if p.id in position]
                if reoptimize:
                    values = by_week.get(week, {})
                    pool = [Player(g, position[g], values.get(g, 0.0)) for g in position]
                    best = lineup_with_locks(
                        pool, slots, set(data.played) & set(position), set(state.locked_starters)
                    )
                    lineup = [p for p in pool if p.id in best.players and p.id not in data.played]
                offset, k_open, def_open = state.realized, state.open_k, state.open_def
            else:
                values = by_week.get(week, {})
                pool = [Player(g, position[g], values[g]) for g in position if g in values]
                lineup = [
                    Player(pid, position[pid], values[pid])
                    for _, pid in auto_lineup(pool, slots).slots
                ]
                offset, k_open, def_open = 0.0, constants.get("K", 0), constants.get("DEF", 0)
            m, var, persistent = lineup_moments(lineup, data.cv, data.pair_rho)
            weekly = max(var - persistent, 0.5 * var)
            fixed_var = k_open * data.k_var + def_open * data.def_var
            mean[t, w] = offset + m + k_open * data.k_mean + def_open * data.def_mean
            noise_sd[t, w] = np.sqrt(weekly + fixed_var + DRIFT_SD**2)
            for p in lineup:
                shift[t, w] += errors[p.id]

    return SeasonInputs(
        roster_ids=data.roster_ids,
        weeks=weeks,
        mean=mean,
        noise_sd=noise_sd,
        shift=shift,
        pairs={
            wk: [(index[a], index[b]) for a, b in pairs]
            for wk, pairs in data.pairings.items()
            if data.current_week <= wk < data.playoff_start
        },
        wins0=np.array([data.wins0[r] for r in data.roster_ids], dtype=float),
        points0=np.array([data.points0[r] for r in data.roster_ids], dtype=float),
        playoff_start=data.playoff_start,
        seed=seed,
    )


def league_odds(
    data: LeagueData,
    rosters: pl.DataFrame | None = None,
    n_sims: int = 20000,
    seed: int = 0,
    reoptimize: bool = False,
) -> tuple[SeasonResult, SeasonInputs]:
    inputs = build_inputs(data, rosters, n_sims, seed, reoptimize)
    return simulate_season(inputs), inputs
