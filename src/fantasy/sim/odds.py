"""Turn projections, spreads and rosters into season odds for one league.

For each team and remaining week: the best lineup by projected points (or, for the week in
progress, the starters already set, with realized points counted), its mean, its weekly
variance (player spread scaled from the projection, with measured correlations between
teammates), and a persistent per-player error shared by every week of one simulated season.

TAU and the absence rates are measured; DRIFT_SD is an assumption (docs/decisions.md).
"""

import zlib
from dataclasses import dataclass, field
from functools import lru_cache

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
from fantasy.sim.value import (
    conditional_values,
    play_curves,
    replacement_pool,
    stand_ins,
    values_by_week,
)

# Persistent per-player error, points a game: sd of 5-game mean error beyond what weekly noise
# explains, from walk-forward projections 2018 to 2025, averaged over both leagues' scoring.
TAU = {"QB": 1.5, "RB": 1.7, "WR": 0.8, "TE": 0.55}
DRIFT_SD = 2.0  # assumed weekly roster drift per team, not measured
PLAYOFF_WEEKS = 3
# Absences after this week, measured on nflverse 2018 to 2025 for skill players with at least 5
# touches or targets: a player who played misses the next week 6.9% of the time, and a player who
# missed one misses another 53% of the time (a bit low, since players who never return drop out of
# the sample). Baseline projections are for games played, so these are absences on top of them.
HAZARD = 0.07
STAY_OUT = 0.55


@dataclass(frozen=True)
class CurrentWeek:
    """A team's week in progress: points already scored and who is still to play."""

    realized: float
    open_players: tuple[Player, ...]  # set starters whose points are not in yet
    open_k: float  # K and DEF slots still to score, counting a game under way by its share left
    open_def: float
    locked_starters: frozenset[str] = frozenset()  # set starters whose game has started
    kd_actual: float = 0.0  # points already scored by K and DEF starters (part of realized)


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
    played: frozenset[str] = frozenset()  # everyone whose game has started this week
    live: dict[str, tuple[float, float]] = field(default_factory=dict)  # id -> (points, share left)
    injuries: dict[str, tuple[str, str | None, str | None]] = field(
        default_factory=dict
    )  # id -> (status, body, practice)
    cv_tiers: dict[str, tuple[tuple[float, float], ...]] = field(default_factory=dict)
    # position -> ((upper projection edge, cv), ...) by size tier; the starters' spread is smaller
    kd_slot: dict[tuple[str, int, int], float] = field(default_factory=dict)
    # (kind "K" or "DEF", roster id, week) -> projected points of the team's best rostered unit


def kd_slot_mean(data: LeagueData, kind: str, roster_id: int, week: int) -> float:
    """Expected points of one K or DEF slot: the team's own projection, else the league mean."""
    league = data.k_mean if kind == "K" else data.def_mean
    return data.kd_slot.get((kind, roster_id, week), league)


def spread_cv(
    position: str,
    value: float,
    cv: dict[str, float],
    tiers: dict[str, tuple[tuple[float, float], ...]],
) -> float:
    """Spread of a player's points over his projection: the cv of his size tier when the position
    has tiers ((upper projection edge, cv) in ascending order), else the position's pooled cv."""
    for upper, tier_cv in tiers.get(position, ()):
        if value < upper:
            return tier_cv
    return cv[position]


def lineup_moments(
    players: list[Player],
    cv: dict[str, float],
    rho: dict[tuple[str, str], float],
    tiers: dict[str, tuple[tuple[float, float], ...]] | None = None,
    shares: dict[str, float] | None = None,
) -> tuple[float, float, float]:
    """(mean, total variance, persistent variance) of a lineup's points in one week.

    `shares` maps a player id to the share of his game still to play (default 1): his value is
    already scaled by it, so his persistent error is too."""
    ordered = sorted(players, key=lambda p: (-p.value, p.id))
    seen: dict[str, int] = {}
    roles, sds = [], []
    for p in ordered:
        seen[p.position] = seen.get(p.position, 0) + 1
        roles.append(f"{p.position}{seen[p.position]}")
        sds.append(p.value * spread_cv(p.position, p.value, cv, tiers or {}))
    var = sum(s * s for s in sds)
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            var += 2 * rho.get((roles[i], roles[j]), 0.0) * sds[i] * sds[j]
    mean = sum(p.value for p in ordered)
    left = shares or {}
    persistent = sum((TAU[p.position] * left.get(p.id, 1.0)) ** 2 for p in ordered)
    return mean, var, persistent


# An entry is n_weeks x n_sims bytes (about 220 KB at 20000 sims); 768 entries is under 300 MB at
# the longest horizon, and both leagues need about 500 (measured 2026-10-25).
ABSENCE_CACHE_SIZE = 768


@lru_cache(maxsize=ABSENCE_CACHE_SIZE)
def absence_path(
    gsis_id: str,
    curve: tuple[float, ...],
    n_weeks: int,
    n_sims: int,
    seed: int,
    hazard: float,
    stay_out: float,
) -> np.ndarray:
    """(n_weeks, n_sims) True where the player is out. While his injury curve lasts (the chance
    of playing each week, rising as he recovers) one draw decides when he returns, so an
    absence lingers; after it the weeks follow a two-state chain. The draws belong to the
    player, so his path is the same in every roster scenario and follows him in a trade."""
    u = np.random.default_rng([seed, zlib.crc32(gsis_id.encode()), 17]).random((n_weeks, n_sims))
    out = np.empty((n_weeks, n_sims), dtype=bool)
    for w in range(n_weeks):
        if w < len(curve):
            out[w] = u[0] >= curve[w]
        else:
            out[w] = np.where(out[w - 1], u[w] < stay_out, u[w] < hazard)
    out.setflags(write=False)
    return out


def player_error(gsis_id: str, n_sims: int, seed: int) -> np.ndarray:
    """A player's persistent error draws, the same in every scenario for the same seed."""
    return np.random.default_rng([seed, zlib.crc32(gsis_id.encode())]).standard_normal(n_sims)


def _current_lineup(
    data: LeagueData,
    state: CurrentWeek,
    position: dict[str, str],
    values: dict[str, float],
    slots: list[str],
    reoptimize: bool,
) -> list[Player]:
    """This week's open lineup. A player traded away leaves it; acquired players start benched
    unless `reoptimize` refills the unplayed slots with the best available."""
    lineup = [p for p in state.open_players if p.id in position]
    if not reoptimize:
        return lineup
    pool = [Player(g, position[g], values.get(g, 0.0)) for g in position]
    best = lineup_with_locks(
        pool, slots, set(data.played) & set(position), set(state.locked_starters)
    )
    in_progress = [p for p in state.open_players if p.id in data.played and p.id in position]
    return in_progress + [p for p in pool if p.id in best.players and p.id not in data.played]


def _subtract_absences(
    shift_row: np.ndarray,
    lineup: list[Player],
    own: set[str],
    available: list[Player],
    full_total: float,
    slots: list[str],
    draws: tuple[dict[str, tuple[float, ...]], int, int, int, int],
) -> None:
    """Lower `shift_row` (this team and week, over sims) in the runs where a starter is out: he
    falls back to the bench or a stand-in. `draws` is (curves, week index, weeks, sims, seed)."""
    curves, w, n_weeks, n_sims, seed = draws
    for p in lineup:
        if p.id not in own:
            continue
        rest = [q for q in available if q.id != p.id]
        loss = full_total - auto_lineup(rest, slots).total
        gone = absence_path(
            p.id, curves.get(p.id, (1.0,)), n_weeks, n_sims, seed, HAZARD, STAY_OUT
        )[w]
        shift_row -= loss * gone


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
    by_week = values_by_week(data.projections)
    # stand-ins for absent starters: the best free agents, not counting anyone rostered before
    # or after this scenario (a player dropped in it is assumed claimed by someone else)
    taken = set(data.rosters["gsis_id"].to_list()) | set(rosters["gsis_id"].to_list())
    free_ids = [g for g in data.positions if g not in taken]
    replacements = replacement_pool(free_ids, data.positions, by_week)
    curves = play_curves(data.projections, weeks)
    later = conditional_values(data.projections)
    for rid, t in index.items():
        team = rosters.filter(pl.col("roster_id") == rid)
        position = dict(zip(team["gsis_id"], team["position"], strict=True))
        errors = {g: TAU[pos] * player_error(g, n_sims, seed) for g, pos in position.items()}
        for w, week in enumerate(weeks):
            state = data.current.get(rid) if week == data.current_week else None
            if state is not None:
                # a player traded away this week leaves the lineup; acquired players start benched
                lineup = _current_lineup(
                    data, state, position, by_week.get(week, {}), slots, reoptimize
                )
                offset, k_open, def_open = state.realized, state.open_k, state.open_def
            else:
                # expected points when playing: absences are drawn below, never discounted twice
                values = (later if w >= 1 else by_week).get(week, {})
                pool = [Player(g, position[g], values[g]) for g in position if g in values]
                # holes (byes, absences, weak starters) fall back to stand-in free agents
                floor = stand_ins(replacements.get(week, []), set(position))
                full = auto_lineup(pool + floor, slots)
                known = {p.id: p for p in pool + floor}
                lineup = [known[pid] for _, pid in full.slots]
                offset, k_open, def_open = 0.0, constants.get("K", 0), constants.get("DEF", 0)
            # in-progress players enter at projection * share left; so does their persistent error
            left = (
                {p.id: data.live.get(p.id, (0.0, 1.0))[1] for p in lineup}
                if state is not None
                else {}
            )
            m, var, persistent = lineup_moments(lineup, data.cv, data.pair_rho, data.cv_tiers, left)
            weekly = max(var - persistent, 0.5 * var)
            fixed_var = k_open * data.k_var + def_open * data.def_var
            mean[t, w] = (
                offset + m
                + k_open * kd_slot_mean(data, "K", rid, week)
                + def_open * kd_slot_mean(data, "DEF", rid, week)
            )  # fmt: skip
            noise_sd[t, w] = np.sqrt(weekly + fixed_var + DRIFT_SD**2)
            for p in lineup:
                if p.id not in errors:  # a stand-in free agent
                    errors[p.id] = TAU[p.position] * player_error(p.id, n_sims, seed)
                shift[t, w] += errors[p.id] * left.get(p.id, 1.0)
            if w >= 1 and HAZARD > 0 and state is None:
                # a starter who is out falls back to the bench or a stand-in
                _subtract_absences(
                    shift[t, w], lineup, set(position), pool + floor, full.total, slots,
                    (curves, w, n_weeks, n_sims, seed),
                )  # fmt: skip

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
        wins0=np.array([data.wins0.get(r, 0.0) for r in data.roster_ids], dtype=float),
        points0=np.array([data.points0.get(r, 0.0) for r in data.roster_ids], dtype=float),
        playoff_start=data.playoff_start,
        seed=seed,
    )


def league_odds(
    data: LeagueData,
    rosters: pl.DataFrame | None = None,
    n_sims: int = 20000,
    seed: int = 0,
    reoptimize: bool = False,
) -> SeasonResult:
    return simulate_season(build_inputs(data, rosters, n_sims, seed, reoptimize))
