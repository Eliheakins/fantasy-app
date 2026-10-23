"""Estimate how far actual points scatter around the baseline projection, and how that scatter
moves together across players.

projection_calibration
                   points over projection by projection size (the baseline over-projects low
                   projections), per league and position; see sim/calibration.py
marginals          quantiles of actual / calibrated projection per league and position, from
                   walk-forward residuals (projection * ratio quantile = a player-game's outcome).
                   tier -1 is all projections; tiers 0, 1 and 2 are the bottom, middle and top
                   third by projection, whose floors and ceilings differ a lot (a low projection
                   has a median far below its mean and a long upper tail)
correlation_pairs  Gaussian-copula correlation between roles (QB1, RB1, WR1, ...), for teammates
                   and for opposing players in the same game, from Spearman rank correlation of
                   residuals: rho = 2 sin(pi * rho_spearman / 6)

Run: uv run python -m fantasy.stages.distributions
"""

import math

import numpy as np
import polars as pl

from fantasy import store
from fantasy.sim.calibration import CALIBRATION_BINS, apply_curves

LEVELS = np.arange(1, 100) / 100
MIN_PROJECTION = 0.5
MIN_TIER_ROWS = 100  # a tier with fewer games than this borrows the all-tier shape
TOP = 1e9  # proj_max of the top tier and of the all-tier rows
ROLES = ["QB1", "RB1", "RB2", "WR1", "WR2", "WR3", "TE1"]
MIN_PAIR_ROWS = 200
TEAM_WEEK = ["league_id", "season", "week", "team"]


def gaussian_rho(rho_spearman: float) -> float:
    return 2 * math.sin(math.pi * rho_spearman / 6)


def residual_frame(proj: pl.DataFrame, points: pl.DataFrame) -> pl.DataFrame:
    """Actual minus projection, for games whose projection used earlier games."""
    actual = points.select("league_id", "gsis_id", "season", "week", "points")
    return (
        proj.filter(~pl.col("is_future") & pl.col("has_history"))
        .join(actual, on=["league_id", "gsis_id", "season", "week"])
        .with_columns((pl.col("points") - pl.col("projection")).alias("resid"))
    )


def estimate_curves(res: pl.DataFrame) -> pl.DataFrame:
    """Calibration curves: at each of CALIBRATION_BINS projection quantile bins per league and
    position, the median projection (center) and points over projection (factor)."""
    rows = []
    usable = res.filter(pl.col("projection") > MIN_PROJECTION)
    for (league_id, position), g in usable.group_by("league_id", "position"):
        x, y = g["projection"].to_numpy(), g["points"].to_numpy()
        edges = np.quantile(x, np.linspace(0, 1, CALIBRATION_BINS + 1))
        index = np.clip(np.digitize(x, edges[1:-1]), 0, CALIBRATION_BINS - 1)
        for k in range(CALIBRATION_BINS):
            in_bin = index == k
            if in_bin.sum() == 0:
                continue
            rows.append(
                {
                    "league_id": league_id,
                    "position": position,
                    "center": float(np.median(x[in_bin])),
                    "factor": float(y[in_bin].sum() / x[in_bin].sum()),
                    "n": int(in_bin.sum()),
                }
            )
    return pl.DataFrame(rows, schema=store.SCHEMAS["projection_calibration"]).sort(
        "league_id", "position", "center"
    )


def _quantile_rows(
    league_id: str, position: str, ratio: np.ndarray, cv: float, tier: int, proj_max: float
) -> list[dict[str, float | int | str]]:
    return [
        {
            "league_id": league_id,
            "position": position,
            "tau": float(tau),
            "ratio": float(value),
            "n": len(ratio),
            "cv": cv,
            "tier": tier,
            "proj_max": proj_max,
        }
        for tau, value in zip(LEVELS, np.quantile(ratio, LEVELS), strict=True)
    ]


def estimate_marginals(res: pl.DataFrame) -> pl.DataFrame:
    """Quantiles of actual / projection per league, position and tier (the shape around the
    mean). `res` should carry the calibrated projection.

    A Gamma with constant CV was tried first and covered only 66 to 74 percent of outcomes with
    its 80 percent interval: real games have more near-zero outcomes than a Gamma allows.
    Tier -1 is every projection; tiers 0 to 2 split the position into thirds by projection,
    because a low projection's outcome is mostly a dud with a long upper tail while a high
    projection's is steadier (position by tier cut pinball loss 2.6% out of sample).
    """
    rows: list[dict[str, float | int | str]] = []
    usable = res.filter(pl.col("projection") > MIN_PROJECTION)
    for (league_id, position), g in usable.group_by("league_id", "position"):
        points, projection = g["points"].to_numpy(), g["projection"].to_numpy()
        ratio = points / projection
        resid = g["resid"].to_numpy()
        cv = float(np.sqrt((resid**2).sum() / (projection**2).sum()))
        rows += _quantile_rows(league_id, position, ratio, cv, -1, TOP)
        edges = np.quantile(projection, [1 / 3, 2 / 3])
        tier = np.digitize(projection, edges)
        for t in range(3):
            chosen = ratio[tier == t]
            shape = chosen if len(chosen) >= MIN_TIER_ROWS else ratio
            upper = float(edges[t]) if t < 2 else TOP
            rows += _quantile_rows(league_id, position, shape, cv, t, upper)
    return pl.DataFrame(rows, schema=store.SCHEMAS["marginals"]).sort(
        "league_id", "position", "tier", "tau"
    )


def with_roles(res: pl.DataFrame) -> pl.DataFrame:
    """Label each player-game QB1, RB1, ... by projection rank within team, week and position."""
    rank = pl.col("projection").rank("ordinal", descending=True).over(*TEAM_WEEK, "position")
    return res.with_columns(role=pl.col("position") + rank.cast(pl.String)).filter(
        pl.col("role").is_in(ROLES)
    )


def _correlate(pairs: pl.DataFrame, relation: str) -> pl.DataFrame:
    return (
        pairs.group_by("league_id", "role", "role_b")
        .agg(
            pl.corr("resid", "resid_b", method="spearman").alias("rho_spearman"),
            pl.len().cast(pl.Int64).alias("n"),
        )
        .filter(pl.col("n") >= MIN_PAIR_ROWS)
        .rename({"role": "role_a"})
        .with_columns(
            relation=pl.lit(relation),
            rho=(2 * (math.pi * pl.col("rho_spearman") / 6).sin()),
        )
    )


def estimate_pairs(roled: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    base = roled.select(*TEAM_WEEK, "gsis_id", "role", "resid")
    other = base.rename({"gsis_id": "gsis_b", "role": "role_b", "resid": "resid_b"})
    same = base.join(other, on=TEAM_WEEK).filter(pl.col("role") < pl.col("role_b"))

    opponents = games.select("season", "week", "team", "opponent").unique()
    opp_side = other.rename({"team": "team_b"})
    opposing = (
        base.join(opponents, on=["season", "week", "team"])
        .join(
            opp_side,
            left_on=["league_id", "season", "week", "opponent"],
            right_on=["league_id", "season", "week", "team_b"],
        )
        .filter(pl.col("role") <= pl.col("role_b"))
    )
    out = pl.concat([_correlate(same, "same_team"), _correlate(opposing, "opposing")])
    return out.select(*store.SCHEMAS["correlation_pairs"]).sort(
        "league_id", "relation", "role_a", "role_b"
    )


def run() -> dict[str, int]:
    res = residual_frame(store.read_table("proj_baseline"), store.read_table("player_points"))
    curves = estimate_curves(res)
    calibrated = apply_curves(res, curves).with_columns(
        (pl.col("points") - pl.col("projection")).alias("resid")
    )
    marginals = estimate_marginals(calibrated)
    pairs = estimate_pairs(with_roles(calibrated), store.read_table("team_games"))
    store.write_table("projection_calibration", curves)
    store.write_table("marginals", marginals)
    store.write_table("correlation_pairs", pairs)
    return {
        "projection_calibration": curves.height,
        "marginals": marginals.height,
        "correlation_pairs": pairs.height,
    }


def calibrated(frame: pl.DataFrame) -> pl.DataFrame:
    """`frame` (league_id, position, projection) with the projection calibrated by size, when the
    curves have been estimated; otherwise unchanged."""
    try:
        curves = store.read_table("projection_calibration")
    except FileNotFoundError:
        return frame
    return apply_curves(frame, curves)


def main() -> None:
    for name, rows in run().items():
        print(f"{name}: {rows} rows")


if __name__ == "__main__":
    main()
