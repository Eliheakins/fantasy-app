"""Blend our baseline projection with Sleeper's (RotoWire) where Sleeper has one.

Weeks 1 to 6 of 2026 (past weeks, not a clean test): RMSE 6.01 Sleeper, 6.26 ours, 5.94 for an
even blend. Equal weight is the simple choice until clean pre-game snapshots can be tested.
"""

import polars as pl

SLEEPER_WEIGHT = 0.5


def blend(
    ours: pl.DataFrame,
    theirs: pl.DataFrame,
    key: str,
    zero_is_missing: frozenset[str] = frozenset(),
) -> pl.DataFrame:
    """`ours` has key, week, projection (more columns are kept); `theirs` has key, week, other.
    Rows without a Sleeper projection keep ours. A Sleeper 0 for a key in `zero_is_missing` also
    counts as no projection: Sleeper zeroes Questionable and Doubtful players, whose chance of
    playing the injury layer already applies, so blending the 0 would discount them twice."""
    joined = ours.join(
        theirs.select(key, "week", "other").unique(
            [key, "week"], keep="first", maintain_order=True
        ),
        on=[key, "week"],
        how="left",
    ).with_columns(
        pl.when(pl.col(key).is_in(zero_is_missing) & (pl.col("other") == 0))
        .then(None)
        .otherwise(pl.col("other"))
        .alias("other")
    )
    mixed = (1 - SLEEPER_WEIGHT) * pl.col("projection") + SLEEPER_WEIGHT * pl.col("other")
    return joined.with_columns(
        pl.when(pl.col("other").is_not_null())
        .then(mixed)
        .otherwise(pl.col("projection"))
        .alias("projection")
    ).drop("other")
