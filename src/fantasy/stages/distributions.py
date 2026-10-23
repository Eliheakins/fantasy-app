"""Estimate how far actual points scatter around the baseline projection, and how that scatter
moves together across players.

marginals          coefficient of variation per league and position, from walk-forward residuals
                   (a Gamma with mean = projection and this CV is the marginal for one player-game)
correlation_pairs  Gaussian-copula correlation between roles (QB1, RB1, WR1, ...), for teammates
                   and for opposing players in the same game, from Spearman rank correlation of
                   residuals: rho = 2 sin(pi * rho_spearman / 6)

Run: uv run python -m fantasy.stages.distributions
"""

import math

import polars as pl

from fantasy import store

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


def estimate_cv(res: pl.DataFrame) -> pl.DataFrame:
    """cv^2 = sum of squared residuals / sum of squared projections (a ratio estimator)."""
    return (
        res.filter(pl.col("projection") > 0)
        .group_by("league_id", "position")
        .agg(
            ((pl.col("resid") ** 2).sum() / (pl.col("projection") ** 2).sum()).sqrt().alias("cv"),
            pl.len().cast(pl.Int64).alias("n"),
        )
        .sort("league_id", "position")
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
    marginals = estimate_cv(res).select(*store.SCHEMAS["marginals"])
    pairs = estimate_pairs(with_roles(res), store.read_table("team_games"))
    store.write_table("marginals", marginals)
    store.write_table("correlation_pairs", pairs)
    return {"marginals": marginals.height, "correlation_pairs": pairs.height}


def main() -> None:
    for name, rows in run().items():
        print(f"{name}: {rows} rows")


if __name__ == "__main__":
    main()
