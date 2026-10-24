"""My lineup for a week and the lineup with the best chance to win it (see data_api)."""

from datetime import datetime

import numpy as np
import polars as pl

from fantasy._engine import (
    KD_SEED_OFFSET,
    LINEUP_SEED,
    PLAY_PROB_FLOOR,
    _constant_points,
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
)
from fantasy._schemas import ENGINE_SCHEMAS
from fantasy.sim import moves
from fantasy.sim.availability import LONG_TERM
from fantasy.sim.lineup import Player, lineup_slots, lineup_with_locks
from fantasy.sim.odds import LeagueData
from fantasy.sim.winprob import choose, pick_by_quantile, search, swap_candidates

LINEUP_SIMS = 20000
UNDERDOG = 0.45  # below this chance to win with the best lineup, variance is an asset
FAVORITE = 0.55  # above it, protect the floor


def _points_so_far(live: dict[str, tuple[float, float]], gsis_id: str) -> float:
    points, share = live.get(gsis_id, (0.0, 1.0))
    return points if share < 1.0 else 0.0


def _game_state(live: dict[str, tuple[float, float]], gsis_id: str) -> str:
    share = live.get(gsis_id, (0.0, 1.0))[1]
    if share >= 1.0:
        return "Not started"
    return "Final" if share <= 0.0 else f"Live, {share:.0%} left"


def _is_out(data: LeagueData, gsis_id: str) -> bool:
    flag = data.injuries.get(gsis_id)
    return flag is not None and (flag[0] == "Out" or flag[0] in LONG_TERM)


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
    values = moves.week_values(data).get(week, {})
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
    best = lineup_with_locks(
        pool, lineup_slots(data.roster_positions), {p.id for p in pool if p.id in locked}, starting
    )
    slot_of = {pid: slot for slot, pid in best.slots}
    live = data.live if current else {}
    rows = [
        {
            "slot": slot_of.get(p.id, "BN"),
            "gsis_id": p.id,
            "full_name": names.get(p.id, p.id),
            "position": p.position,
            "projection": p.value,
            "p10": _spread(p, 0.1, chance, ratio, edges, _is_out(data, p.id)),
            "p90": _spread(p, 0.9, chance, ratio, edges, _is_out(data, p.id)),
            "starting_now": p.id in starting,
            "recommended": p.id in slot_of,
            "injury": status.get(p.id),
            "injury_note": _injury_note(data, p.id),
            "locked": p.id in locked,
            "actual": _points_so_far(live, p.id),
            "game": _game_state(live, p.id),
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

    positions, values = moves.position_of(data), moves.week_values(data).get(week, {})
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
    script = _script(verdict.win_prob[base])

    mean_of = {r["gsis_id"]: r["projection"] for r in mine_rows.iter_rows(named=True)}
    options = {"max_points": base, "win_prob": verdict.chosen, "ceiling": ceiling, "floor": floor}
    if sleeper:
        options["sleeper_now"] = sleeper
    rows = [
        {
            "option": name,
            "win_prob": verdict.win_prob[ids_],
            "expected_points": sum(mean_of[i] for i in ids_),
            "gsis_ids": sorted(ids_),
            "slots": _slots_of(ids_, mean_of, positions, slots),
            "share_better": verdict.share_better if name == "win_prob" else 0.5,
            "tag": verdict.tag if name == "win_prob" else "",
            "floor": held[0.1][ids_],
            "median": held[0.5][ids_],
            "ceiling": held[0.9][ids_],
            "script": script,
        }
        for name, ids_ in options.items()
    ]
    return pl.DataFrame(rows, schema=ENGINE_SCHEMAS["win_probability"])
