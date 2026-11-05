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

from fantasy.sim.scoring_scale import Effects

HALF_LIFE = 4.0  # games, for the usage averages
MIN_SHARE = (0.04, 0.08)  # an absent teammate counts if his target or carry share is above this


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


def usage_table(stats: pl.DataFrame, team_stats: pl.DataFrame) -> pl.DataFrame:
    """Per player-game: target and carry share, and their exponentially weighted averages
    (`*_ewma` includes the game, `*_prior` stops before it)."""
    team_carries = team_stats.filter(pl.col("season_type") == "REG").select(
        "team", "season", "week", pl.col("carries").alias("team_carries")
    )
    rows = (
        stats.filter(pl.col("season_type") == "REG")
        .select(
            pl.col("player_id").alias("gsis_id"),
            "season",
            "week",
            "team",
            "target_share",
            "carries",
        )
        .join(team_carries, on=["team", "season", "week"], how="left")
        .with_columns(
            pl.col("target_share").fill_null(0.0),
            (pl.col("carries").fill_null(0.0) / pl.col("team_carries"))
            .fill_null(0.0)
            .alias("carry_share"),
        )
        .sort("gsis_id", "season", "week")
    )
    rows = rows.with_columns(
        pl.col("target_share").ewm_mean(half_life=HALF_LIFE).over("gsis_id").alias("target_ewma"),
        pl.col("carry_share").ewm_mean(half_life=HALF_LIFE).over("gsis_id").alias("carry_ewma"),
    )
    return rows.with_columns(
        pl.col("target_ewma").shift(1).over("gsis_id").alias("target_prior"),
        pl.col("carry_ewma").shift(1).over("gsis_id").alias("carry_prior"),
    )


def live_context(
    stats: pl.DataFrame,
    team_stats: pl.DataFrame,
    team_games: pl.DataFrame,
    injuries: pl.DataFrame,
    season: int,
    current_week: int,
) -> Context:
    """Who is back this week, and each player's latest usage, from games before `current_week`.

    A missed stretch counts as an injury absence when the player was on the injury report in the
    week before it began or during it."""
    usage = usage_table(stats.filter(pl.col("season") <= season), team_stats)
    played = usage.filter((pl.col("season") == season) & (pl.col("week") < current_week))
    games = (
        team_games.filter((pl.col("game_type") == "REG") & (pl.col("season") == season))
        .select("team", "week")
        .filter(pl.col("week") < current_week)
        .sort("team", "week")
        .with_columns(pl.int_range(pl.len()).over("team").alias("g"))
    )
    seen = played.join(games, on=["team", "week"], how="inner").sort("gsis_id", "week")
    team_last = games.group_by("team").agg(pl.col("g").max().alias("team_last"))
    per_player = (
        seen.group_by("gsis_id")
        .agg(
            pl.col("g").last().alias("last_g"),
            pl.col("g").diff().last().alias("last_gap"),
            pl.col("week").last().alias("last_week"),
            pl.col("week").shift(1).last().alias("prev_week"),
            pl.col("team").last().alias("team"),
        )
        .join(team_last, on="team")
        .with_columns((pl.col("team_last") - pl.col("last_g")).alias("missed"))
    )
    listed: dict[str, set[int]] = {}
    reports = injuries.filter((pl.col("season") == season) & (pl.col("game_type") == "REG"))
    for g, week in zip(reports["gsis_id"], reports["week"], strict=True):
        listed.setdefault(g, set()).add(week)

    def reported(gsis_id: str, low: int, high: int) -> bool:
        return any(low <= w <= high for w in listed.get(gsis_id, ()))

    missed: dict[str, tuple[int, bool]] = {}
    after: dict[str, bool] = {}
    for r in per_player.iter_rows(named=True):
        g = r["gsis_id"]
        if r["missed"] >= 1:
            missed[g] = (int(r["missed"]), reported(g, r["last_week"] - 1, current_week - 1))
        elif r["last_gap"] is not None and r["last_gap"] >= 2 and r["prev_week"] is not None:
            after[g] = reported(g, r["prev_week"] - 1, r["last_week"] - 1)
    latest = (
        usage.sort("gsis_id", "season", "week")
        .group_by("gsis_id")
        .agg(pl.col("team").last(), pl.col("target_ewma").last(), pl.col("carry_ewma").last())
    )
    shares = {
        r["gsis_id"]: (r["team"], float(r["target_ewma"]), float(r["carry_ewma"]))
        for r in latest.iter_rows(named=True)
    }
    return Context(missed, after, shares)
