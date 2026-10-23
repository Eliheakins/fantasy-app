"""Adjust projections for two in-season changes: players coming back from missed games, and
players whose teammates are out.

A player in his first game back plays below his projection (about 60% for a quarterback, 75% to
80% for the others), and a smaller shortfall in the second game back; the ramp is spread across the
games he might return in using his injury curve. A receiver or back whose teammates are out
gains points in proportion to the target or carry share they leave behind. Both effects are
measured in `stages/outlook.py`; see docs/decisions.md for how they were tested.

`projection` keeps meaning expected points counting the chance of not playing, and `play_prob`
the chance of playing, so a flagged player is never discounted twice.
"""

from typing import NamedTuple

import polars as pl

MIN_SHARE = (0.04, 0.08)  # an absent teammate counts if his target or carry share is above this
Effects = dict[tuple[str, str], float]  # (position, kind) -> value


class Context(NamedTuple):
    """The live situation: who is back this week and each player's recent usage."""

    missed: dict[str, tuple[int, bool]]  # gsis id -> (team games missed, on the injury report)
    after_return: dict[str, bool]  # played last week after missing games -> was it an injury
    usage: dict[str, tuple[str, float, float]]  # gsis id -> (team, target share, carry share)


def effects_dict(table: pl.DataFrame) -> Effects:
    return {(r["position"], r["kind"]): r["value"] for r in table.iter_rows(named=True)}


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def return_factors(
    chances: list[float], missed_last: bool, after_return: bool, first: float, second: float
) -> list[float]:
    """The multiplier on points-when-playing for each of a player's coming games.

    `chances` are his chances of playing each game (his injury curve, 1.0 when healthy). A game
    is his first back when he was out the game before and plays this one; with one draw deciding
    when he returns, that has probability `p_k - p_{k-1}`. `first` and `second` are the ratios
    of points to projection in the first and second game back."""
    previous = 0.0 if missed_last else 1.0  # chance he played the game before the first listed
    firsts = []
    for p in chances:
        firsts.append(_clip(p - previous))
        previous = p
    out = []
    for k, p in enumerate(chances):
        if p <= 0:
            out.append(1.0)
            continue
        carry = firsts[k - 1] if k >= 1 else (1.0 if after_return else 0.0)
        shortfall = (firsts[k] / p) * (1.0 - first) + _clip(carry / p) * (1.0 - second)
        out.append(max(0.0, 1.0 - shortfall))
    return out


def _counts(target: float, carry: float) -> bool:
    return target > MIN_SHARE[0] or carry > MIN_SHARE[1]


def apply_outlook(
    projections: pl.DataFrame, context: Context, effects: Effects, current_week: int
) -> pl.DataFrame:
    """`projections` (gsis_id, week, projection, play_prob, team, position) with the return ramp
    and teammate vacancy applied, plus `outlook_factor` and `vacancy_points` columns."""
    rows = projections.sort("gsis_id", "week")
    position = dict(zip(rows["gsis_id"], rows["position"], strict=True))
    ahead = rows.filter(pl.col("week") >= current_week)

    chances: dict[str, dict[int, float]] = {}
    for g, p, week in zip(ahead["gsis_id"], ahead["play_prob"], ahead["week"], strict=True):
        chances.setdefault(g, {})[week] = p
    factor: dict[tuple[str, int], float] = {}
    for g, by_week in chances.items():
        weeks = sorted(by_week)
        pos = position[g]
        by_chance = [by_week[w] for w in weeks]
        injured = (
            context.missed.get(g, (0, False))[1]
            or context.after_return.get(g, False)
            or min(by_chance) < 1.0  # flagged now: any absence is an injury absence
        )
        kind = "injury" if injured else "other"
        ramp = return_factors(
            by_chance,
            g in context.missed,
            g in context.after_return,
            effects.get((pos, f"first_back_{kind}"), 1.0),
            effects.get((pos, f"second_back_{kind}"), 1.0),
        )
        factor.update({(g, w): f for w, f in zip(weeks, ramp, strict=True)})

    # share left behind by absent teammates, per team and week
    vacated: dict[tuple[str, int], tuple[float, float]] = {}
    for g, team, week, p in zip(
        ahead["gsis_id"], ahead["team"], ahead["week"], ahead["play_prob"], strict=True
    ):
        _, target, carry = context.usage.get(g, ("", 0.0, 0.0))
        if _counts(target, carry):
            t0, c0 = vacated.get((team, week), (0.0, 0.0))
            vacated[(team, week)] = (t0 + (1 - p) * target, c0 + (1 - p) * carry)

    ramps, bumps = [], []
    for g, team, week, p in zip(
        rows["gsis_id"], rows["team"], rows["week"], rows["play_prob"], strict=True
    ):
        if week < current_week:
            ramps.append(1.0)
            bumps.append(0.0)
            continue
        _, target, carry = context.usage.get(g, ("", 0.0, 0.0))
        counted = _counts(target, carry)
        own_t, own_c = ((1 - p) * target, (1 - p) * carry) if counted else (0.0, 0.0)
        t_gone, c_gone = vacated.get((team, week), (0.0, 0.0))
        pos = position[g]
        bumps.append(
            effects.get((pos, "vac_target"), 0.0) * max(0.0, t_gone - own_t)
            + effects.get((pos, "vac_carry"), 0.0) * max(0.0, c_gone - own_c)
        )
        ramps.append(factor.get((g, week), 1.0))
    return rows.with_columns(
        pl.Series("outlook_factor", ramps, dtype=pl.Float64),
        pl.Series("vacancy_points", bumps, dtype=pl.Float64),
    ).with_columns(
        (
            pl.col("projection") * pl.col("outlook_factor")
            + pl.col("play_prob") * pl.col("vacancy_points")
        ).alias("projection")
    )
