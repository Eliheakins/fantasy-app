"""Blend our projection with other sources: the equal-weight mean of every source a row has.

Weeks 1 to 6 of 2026 (past weeks, not a clean test): RMSE 6.01 Sleeper, 6.26 ours, 5.94 for an
even blend. Equal weights also won with prop lines (2024 held out) and FFToday (2025, 2026 weeks 1
to 6); with few evaluation weeks fitted weights rarely beat them (docs/decisions.md).
"""

from collections.abc import Sequence

import polars as pl

SLEEPER_WEIGHT = 0.5  # Sleeper's weight when it is the only other source (research/blend_weight)


def blend_all(
    ours: pl.DataFrame,
    others: Sequence[pl.DataFrame],
    key: str,
    zero_is_missing: frozenset[str] = frozenset(),
) -> pl.DataFrame:
    """`ours` has key, week, projection (more columns are kept); each of `others` has key, week,
    other. `projection` becomes the mean of ours and every other source with a value for the row.
    A 0 for a key in `zero_is_missing` counts as no value: Sleeper zeroes Questionable and
    Doubtful players, whose chance of playing the injury layer already applies, so blending the 0
    would discount them twice."""
    joined, columns = ours, []
    for i, theirs in enumerate(others):
        column = f"_other{i}"
        value = pl.col("other")
        joined = joined.join(
            theirs.unique([key, "week"], keep="first", maintain_order=True).select(
                key,
                "week",
                pl.when(pl.col(key).is_in(zero_is_missing) & (value == 0))
                .then(None)
                .otherwise(value)
                .alias(column),
            ),
            on=[key, "week"],
            how="left",
        )
        columns.append(column)
    return joined.with_columns(pl.mean_horizontal("projection", *columns).alias("projection")).drop(
        columns
    )


def blend(
    ours: pl.DataFrame,
    theirs: pl.DataFrame,
    key: str,
    zero_is_missing: frozenset[str] = frozenset(),
) -> pl.DataFrame:
    """Ours and one other source (Sleeper) at SLEEPER_WEIGHT where it has a projection."""
    return blend_all(ours, [theirs], key, zero_is_missing)
