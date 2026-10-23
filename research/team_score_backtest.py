"""Are weekly team-score spreads calibrated on seasons the fit never saw?

The 2026 check (`stages/calibration.py`) has about 100 team-weeks, and the starters in it were
picked by managers who knew who was active. This builds synthetic 10-team leagues from nflverse
history instead: each week the players who played are snake-drafted by that week's projection,
each team starts its best lineup by projection (skill slots only), and the model's mean and
variance for that lineup are compared with the points the lineup scored.

Everything the model uses is fit on 2019 to 2023 (size-calibration curves, spread per position,
teammate correlations) and scored on 2024 onward. Players who did not play are left out, which is
the position of a manager setting a lineup with actives known, and the position the spreads are
fit in. The persistent per-player error (tau) is not in a single week's spread, so it is not
tested here.

Run from the repo root after `make refresh`: uv run python research/team_score_backtest.py
"""

import math

import polars as pl

from fantasy import store
from fantasy.sim.calibration import apply_curves
from fantasy.sim.lineup import Player, auto_lineup, lineup_slots
from fantasy.sim.odds import lineup_moments
from fantasy.stages.simulate import tier_spreads
from fantasy.stages.distributions import (
    estimate_curves,
    estimate_marginals,
    estimate_pairs,
    residual_frame,
    with_roles,
)

TRAIN_END = 2023
N_TEAMS = 10
ROUNDS = 12
Z50 = 0.6744897501960817
Z80 = 1.2815515655446004


def snake_teams(ranked_ids: list[str]) -> list[list[str]]:
    """Deal players in snake order to N_TEAMS teams for ROUNDS rounds."""
    teams: list[list[str]] = [[] for _ in range(N_TEAMS)]
    for pick, pid in enumerate(ranked_ids[: N_TEAMS * ROUNDS]):
        round_, slot = divmod(pick, N_TEAMS)
        teams[slot if round_ % 2 == 0 else N_TEAMS - 1 - slot].append(pid)
    return teams


def score_week(
    pool: pl.DataFrame,
    slots: list[str],
    cv: dict[str, float],
    rho: dict[tuple[str, str], float],
    tiers: dict[str, tuple[tuple[float, float], ...]],
) -> list[dict[str, float]]:
    """One week's synthetic teams: model mean and sd against the points scored. `tiers` empty
    gives the pooled spread per position."""
    ranked = pool.sort("projection", descending=True)
    by_id = {r["gsis_id"]: r for r in ranked.iter_rows(named=True)}
    rows = []
    for team in snake_teams(ranked["gsis_id"].to_list()):
        players = [Player(i, by_id[i]["position"], by_id[i]["projection"]) for i in team]
        started = auto_lineup(players, slots).players
        chosen = [p for p in players if p.id in started]
        mean, var, _ = lineup_moments(chosen, cv, rho, tiers)
        actual = sum(by_id[p.id]["points"] for p in chosen)
        rows.append({"mean": mean, "sd": math.sqrt(var), "actual": actual})
    return rows


def main() -> None:
    res = residual_frame(store.read_table("proj_baseline"), store.read_table("player_points"))
    train_raw = res.filter(pl.col("season") <= TRAIN_END)
    curves = estimate_curves(train_raw)

    def calibrate(frame: pl.DataFrame) -> pl.DataFrame:
        return apply_curves(frame, curves).with_columns(
            (pl.col("points") - pl.col("projection")).alias("resid")
        )

    train, test = calibrate(train_raw), calibrate(res.filter(pl.col("season") > TRAIN_END))
    all_marginals = estimate_marginals(train)
    marginals = all_marginals.filter(pl.col("tier") == -1)
    pairs = estimate_pairs(with_roles(train), store.read_table("team_games"))
    out = []
    for league in store.read_table("leagues", "raw").iter_rows(named=True):
        lid = league["league_id"]
        slots = lineup_slots(list(league["roster_positions"]))
        cv = dict(marginals.filter(pl.col("league_id") == lid).select("position", "cv").iter_rows())
        same = pairs.filter((pl.col("league_id") == lid) & (pl.col("relation") == "same_team"))
        rho: dict[tuple[str, str], float] = {}
        for a, b, r in same.select("role_a", "role_b", "rho").iter_rows():
            rho[(a, b)] = rho[(b, a)] = r
        tiered = tier_spreads(all_marginals.filter(pl.col("league_id") == lid))
        games = test.filter(pl.col("league_id") == lid)
        for spread, tiers in (("pooled", {}), ("by size tier", tiered)):
            for (season, _week), pool in games.group_by("season", "week"):
                for row in score_week(pool, slots, cv, rho, tiers):
                    out.append(
                        {
                            "spread": spread,
                            "league_key": league["league_key"],
                            "season": season,
                            **row,
                        }
                    )
    scores = pl.DataFrame(out).with_columns(z=(pl.col("actual") - pl.col("mean")) / pl.col("sd"))
    summary = scores.group_by("spread", "league_key", "season").agg(
        pl.len().alias("n"),
        pl.col("mean").mean().round(1).alias("mean_pts"),
        pl.col("z").mean().round(3).alias("z_mean"),
        pl.col("z").std().round(3).alias("z_sd"),
        (pl.col("z").abs() <= Z50).mean().round(3).alias("cov50"),
        (pl.col("z").abs() <= Z80).mean().round(3).alias("cov80"),
    )
    by_strength = (
        scores.with_columns(pl.col("mean").qcut(3, labels=["low", "mid", "high"]).alias("third"))
        .group_by("spread", "third")
        .agg(pl.col("z").mean().round(3).alias("z_mean"), pl.col("z").std().round(3).alias("z_sd"))
    )
    with pl.Config(tbl_rows=20):
        print(summary.sort("spread", "league_key", "season"))
        print(by_strength.sort("spread", "third"))
    for name, g in scores.group_by("spread"):
        z = g["z"]
        print(f"{name[0]}: n={g.height} z mean {z.mean():+.3f} sd {z.std():.3f}")


if __name__ == "__main__":
    main()
