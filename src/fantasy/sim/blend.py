"""Blend our projection with other sources: the equal-weight mean of every source a row has,
and SLEEPER_WEIGHT where Sleeper is the only other one.

Weeks 1 to 6 of 2026 (past weeks, not a clean test): RMSE 6.01 Sleeper, 6.26 ours, 5.94 for an
even blend. Equal weights also won with prop lines (2024 held out) and FFToday (2025, 2026 weeks 1
to 6); with few evaluation weeks fitted weights rarely beat them (docs/decisions.md).
"""

from collections.abc import Mapping

import polars as pl

SLEEPER_WEIGHT = 0.5  # Sleeper's weight when it is the only other source (research/blend_weight)


def blend_all(
    ours: pl.DataFrame,
    others: Mapping[str, pl.DataFrame],
    key: str,
    zero_is_missing: frozenset[str] = frozenset(),
    sleeper_weight: float = SLEEPER_WEIGHT,
) -> pl.DataFrame:
    """`ours` has key, week, projection (more columns are kept); each of `others` (by source name,
    as in `blend_sources`) has key, week, other. `projection` becomes the mean of ours and every
    other source with a value for the row, except that a row whose only other value is Sleeper's
    is `(1 - sleeper_weight) * ours + sleeper_weight * sleeper`. A 0 for a key in
    `zero_is_missing` counts as no value: Sleeper zeroes Questionable and Doubtful players, whose
    chance of playing the injury layer already applies, so blending the 0 would discount them
    twice."""
    joined, columns = ours, {}
    for name, theirs in others.items():
        column = f"_other_{name}"
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
        columns[name] = column
    blended = pl.mean_horizontal("projection", *columns.values())
    if "sleeper" in columns:
        sleeper = pl.col(columns["sleeper"])
        only_sleeper = sleeper.is_not_null() & pl.col("projection").is_not_null()
        for name, column in columns.items():
            if name != "sleeper":
                only_sleeper = only_sleeper & pl.col(column).is_null()
        weighted = (1 - sleeper_weight) * pl.col("projection") + sleeper_weight * sleeper
        blended = pl.when(only_sleeper).then(weighted).otherwise(blended)
    return joined.with_columns(blended.alias("projection")).drop(list(columns.values()))


def blend(
    ours: pl.DataFrame,
    theirs: pl.DataFrame,
    key: str,
    zero_is_missing: frozenset[str] = frozenset(),
) -> pl.DataFrame:
    """Ours and Sleeper at SLEEPER_WEIGHT where Sleeper has a projection."""
    return blend_all(ours, {"sleeper": theirs}, key, zero_is_missing)
