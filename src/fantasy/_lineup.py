"""My lineup for a week and the lineup with the best chance to win it (see data_api)."""

from datetime import datetime

import numpy as np
import polars as pl

from fantasy import store
from fantasy._engine import (
    KD_SEED_OFFSET,
    LINEUP_SEED,
    PLAY_PROB_FLOOR,
    _constant_moments,
    _constant_points,
    _id_map,
    _injury_note,
    _league,
    _marginals,
    _names,
    _opponent_lineup,
    _opponent_of,
    _play_probs,
    _pool,
    _set_starters,
    _slots_of,
    _status_and_locks,
    _tier,
    _tier_edges,
    _week_points,
    _week_values,
)
from fantasy._schemas import ENGINE_SCHEMAS
from fantasy.config import load_config
from fantasy.sim import moves
from fantasy.sim.availability import LONG_TERM, kickoffs
from fantasy.sim.lineup import Player, lineup_slots, lineup_with_locks, swap_plan
from fantasy.sim.odds import LeagueData
from fantasy.sim.winprob import choose, pick_by_quantile, search, swap_candidates

LINEUP_SIMS = 20000
UNDERDOG = 0.45  # below this chance to win with the best lineup, variance is an asset
FAVORITE = 0.55  # above it, protect the floor
SWAP_STATUSES = frozenset({"Questionable", "Doubtful"})  # game-day calls settled at inactives


def _points_so_far(live: dict[str, tuple[float, float]], gsis_id: str) -> float:
    points, share = live.get(gsis_id, (0.0, 1.0))
    return points if share < 1.0 else 0.0


def _game_state(live: dict[str, tuple[float, float]], gsis_id: str) -> str:
    share = live.get(gsis_id, (0.0, 1.0))[1]
    if share >= 1.0:
        return "Not started"
    return "Final" if share <= 0.0 else f"Live, {share:.0%} left"


def _expected_total(p: Player, live: dict[str, tuple[float, float]], chance: float) -> float:
    """Points he is expected to end the week with: banked so far plus what is left of his game
    (he is playing, so his chance of playing no longer discounts it)."""
    points, share = live.get(p.id, (0.0, 1.0))
    if not 0.0 < share < 1.0:
        return p.value
    return points + share * p.value / max(chance, PLAY_PROB_FLOOR)


def _ranged(p: Player, spread: float | None, live: dict[str, tuple[float, float]]) -> float | None:
    """A quantile of his week's total: points banked so far plus the share of the game left times
    the full-game quantile, so a player mid-game or done keeps his range around his projection."""
    if spread is None:
        return None
    points, share = live.get(p.id, (0.0, 1.0))
    return spread if not 0.0 <= share < 1.0 else points + share * spread


def _flag_status(data: LeagueData, gsis_id: str) -> str:
    flag = data.injuries.get(gsis_id)
    return flag[0] if flag is not None else ""


def _is_out(data: LeagueData, gsis_id: str) -> bool:
    status = _flag_status(data, gsis_id)
    return status == "Out" or status in LONG_TERM


def _kickoffs_by_player(week: int) -> dict[str, datetime]:
    """Kickoff of each player's game this week, by nflverse id. Players with no team, or whose
    team has no game this week, are left out."""
    teams = _id_map("nfl_team").filter(pl.col("gsis_id").is_not_null())
    kicks = kickoffs(store.read_table("nfl_schedules", "raw"), load_config().season, week)
    return {
        g: kicks[t] for g, t in zip(teams["gsis_id"], teams["nfl_team"], strict=True) if t in kicks
    }


def _spread(
    p: Player,
    level: float,
    chance: dict[str, float],
    ratio: dict[tuple[str, int, float], float],
    edges: dict[str, list[float]],
    out: bool = False,
) -> float | None:
    """The player's full-game projection scaled to the `level` quantile, or None if unmeasured.
    A player who is out has no range: 0, not what he would score if he played."""
    if out:
        return 0.0
    full = Player(p.id, p.position, p.value / max(chance.get(p.id, 1.0), PLAY_PROB_FLOOR))
    ratio_at = ratio.get((p.position, _tier(edges, full), level))
    return None if ratio_at is None else full.value * ratio_at


def lineup(
    league_key: str,
    week: int = 0,
    now: datetime | None = None,
    loaded: tuple[LeagueData, int] | None = None,
) -> pl.DataFrame:
    """My best lineup by projected points for a remaining week, plus the bench.

    `starting_now` marks who is set to start in Sleeper (only known for the current week).
    p10 and p90 come from how actual points have scattered around projections, for the player's
    full-game projection (not discounted by his chance of playing). `loaded` is a `_league` result
    to reuse.
    """
    data, mine = loaded or _league(league_key)
    week = week or data.current_week
    names, positions = _names(), moves.position_of(data)
    values = _week_values(data, week, positions)
    pool = _pool(data, mine, positions, values)
    marginals = _marginals(data.league_id)
    ratio = {
        (r["position"], r["tier"], round(r["tau"], 2)): r["ratio"]
        for r in marginals.iter_rows(named=True)
    }
    edges = _tier_edges(marginals)
    chance = _play_probs(data, week)
    current = week == data.current_week
    starting = set(_set_starters(data.league_id, week, mine)) if current else set()

    status, locked = _status_and_locks(week, data.current_week, now)
    # a player who is out is never slotted: an empty slot scores the same, and Sleeper shows blank
    available = [p for p in pool if not _is_out(data, p.id)]
    pinned = {p.id for p in available if p.id in locked}
    best = lineup_with_locks(available, lineup_slots(data.roster_positions), pinned, starting)
    swap: dict[str, str] = {}
    if current and load_config().inactive_swap:  # advice only: the lineup above is unchanged
        flagged = {p.id for p in available if _flag_status(data, p.id) in SWAP_STATUSES}
        swap = swap_plan(best, available, flagged, _kickoffs_by_player(week), pinned)
    slot_of = {pid: slot for slot, pid in best.slots}
    live = data.live if current else {}
    rows = [
        {
            "slot": slot_of.get(p.id, "BN"),
            "gsis_id": p.id,
            "full_name": names.get(p.id, p.id),
            "position": p.position,
            "projection": _expected_total(p, live, chance.get(p.id, 1.0)),
            "p10": _ranged(p, _spread(p, 0.1, chance, ratio, edges, _is_out(data, p.id)), live),
            "p90": _ranged(p, _spread(p, 0.9, chance, ratio, edges, _is_out(data, p.id)), live),
            "starting_now": p.id in starting,
            "recommended": p.id in slot_of,
            "injury": status.get(p.id),
            "injury_note": _injury_note(data, p.id),
            "locked": p.id in locked,
            "actual": _points_so_far(live, p.id),
            "game": _game_state(live, p.id),
            "swap_in": names.get(swap[p.id], swap[p.id]) if p.id in swap else None,
        }
        for p in sorted(pool, key=lambda p: (p.id not in slot_of, -p.value))
    ]
    return pl.DataFrame(rows, schema=ENGINE_SCHEMAS["lineup"])


def _script(favourite: float) -> str:
    """The one-line read of the matchup: whether variance helps or the floor matters."""
    if favourite < UNDERDOG:
        return f"Underdog ({favourite:.0%} to win): variance helps"
    if favourite > FAVORITE:
        return f"Favorite ({favourite:.0%} to win): protect the floor"
    return f"Toss-up ({favourite:.0%} to win)"


def win_probability(
    league_key: str,
    week: int = 0,
    n_sims: int = LINEUP_SIMS,
    now: datetime | None = None,
    loaded: tuple[LeagueData, int] | None = None,
) -> pl.DataFrame:
    """My max-points lineup, the lineup set in Sleeper, and the lineup with the best chance of
    beating this week's opponent, each with its win probability on held-out draws.

    The opponent plays the lineup set in Sleeper, or their best lineup if none is set. In the
    current week a player whose game has started counts the points he has, plus a draw scaled to
    the share of his game still to play (a game is assumed to last 200 minutes from kickoff).
    Sleeper points are only as fresh as the last refresh.
    """
    loaded = loaded or _league(league_key)
    data, mine = loaded
    week = week or data.current_week
    opp = _opponent_of(data, mine, week)
    mine_rows = lineup(league_key, week, now, loaded)
    if opp is None or mine_rows.is_empty():
        return pl.DataFrame(schema=ENGINE_SCHEMAS["win_probability"])

    positions = moves.position_of(data)
    values = _week_values(data, week, positions)
    slots = lineup_slots(data.roster_positions)
    opp_ids = _opponent_lineup(data, opp, week, positions, values, slots)

    base = frozenset(mine_rows.filter(pl.col("recommended"))["gsis_id"])
    locked = set(mine_rows.filter(pl.col("locked"))["gsis_id"])
    pool_ids = list(mine_rows["gsis_id"])
    sleeper = frozenset(mine_rows.filter(pl.col("starting_now"))["gsis_id"])

    ids = sorted({*mine_rows["gsis_id"], *opp_ids})
    points, column = _week_points(data, ids, positions, values, week, n_sims)
    current = week == data.current_week

    def total(lineup_ids: frozenset[str] | list[str], team: int, team_seed: int) -> np.ndarray:
        cols = [column[i] for i in lineup_ids]
        state = data.current.get(team) if current else None
        return points[:, cols].sum(axis=1) + _constant_points(data, n_sims, team_seed, state)

    opponent = total(opp_ids, opp, LINEUP_SEED + KD_SEED_OFFSET + 1)
    cache: dict[frozenset[str], np.ndarray] = {}  # shared by train_win and the final totals

    def totals_of(c: frozenset[str]) -> np.ndarray:
        if c not in cache:
            cache[c] = total(c, mine, LINEUP_SEED + KD_SEED_OFFSET)
        return cache[c]

    half = n_sims // 2

    def train_win(c: frozenset[str]) -> float:
        return float((totals_of(c)[:half] > opponent[:half]).mean())

    def neighbors(c: frozenset[str]) -> list[frozenset[str]]:
        bench = [i for i in pool_ids if i not in c and values.get(i, 0) > 0]
        return swap_candidates(c, bench, positions, slots, locked)

    # several swaps at once are looked for, so two ceiling plays together can be found
    candidates = search(base, neighbors, train_win)
    if sleeper and sleeper not in candidates:
        candidates.append(sleeper)
    totals = {c: totals_of(c) for c in candidates}
    verdict = choose(candidates, base, totals, opponent)
    ceiling, _ = pick_by_quantile(candidates, totals, 0.9)
    floor, _ = pick_by_quantile(candidates, totals, 0.1)
    held = {
        q: {c: float(np.quantile(totals[c][half:], q)) for c in candidates} for q in (0.1, 0.5, 0.9)
    }
    opp_floor, opp_median, opp_ceiling = (
        float(np.quantile(opponent[half:], q)) for q in (0.1, 0.5, 0.9)
    )
    script = _script(verdict.win_prob[base])

    mean_of = {r["gsis_id"]: r["projection"] for r in mine_rows.iter_rows(named=True)}
    kd_mean, _ = _constant_moments(data, data.current.get(mine) if current else None)
    options = {"max_points": base, "win_prob": verdict.chosen, "ceiling": ceiling, "floor": floor}
    if sleeper:
        options["sleeper_now"] = sleeper
    rows = [
        {
            "option": name,
            "win_prob": verdict.win_prob[ids_],
            "expected_points": sum(mean_of[i] for i in ids_) + kd_mean,
            "gsis_ids": sorted(ids_),
            "slots": _slots_of(ids_, mean_of, positions, slots),
            "share_better": verdict.share_better if name == "win_prob" else 0.5,
            "tag": verdict.tag if name == "win_prob" else "",
            "floor": held[0.1][ids_],
            "median": held[0.5][ids_],
            "ceiling": held[0.9][ids_],
            "opp_floor": opp_floor,
            "opp_median": opp_median,
            "opp_ceiling": opp_ceiling,
            "script": script,
        }
        for name, ids_ in options.items()
    ]
    return pl.DataFrame(rows, schema=ENGINE_SCHEMAS["win_probability"])
