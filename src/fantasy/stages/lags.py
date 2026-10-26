"""Lagged joins and walk-forward seasons shared by the learned model and its stat-line chance.

Every lagged value uses only games strictly before the target game; `shift` looks that many weeks
further back, for a forecast made further ahead.
"""

import polars as pl

from fantasy.store import week_index

EXTRA_HALF_LIFE = 4.0  # games, for the lagged team and advanced stats
MIN_TRAIN_SEASONS = 2  # a season with fewer earlier seasons is scored by leave-one-season-out
EARLY_BLOCK = 4  # seasons in that early block


def lag_asof(
    target: pl.DataFrame,
    table: pl.DataFrame,
    by: str,
    cols: list[str],
    prefix: str,
    shift: int = 0,
) -> pl.DataFrame:
    """Each column's weighted average over the rows of `table` strictly before the target game
    (`shift` weeks earlier, for a forecast made further ahead), as `<prefix>_<column>`. A value
    missing in the latest row carries the earlier one forward."""
    lagged = [f"{prefix}_{c}" for c in cols]
    state = (
        table.sort(by, "season", "week")
        .with_columns(
            *[
                pl.col(c)
                .forward_fill()
                .ewm_mean(half_life=EXTRA_HALF_LIFE)
                .over(by)
                .alias(f"{prefix}_{c}")
                for c in cols
            ],
            week_index().alias("t"),
        )
        .select(by, "t", *lagged)
        .sort("t")
    )
    left = target.with_columns((week_index() - shift).alias("t")).sort("t")
    return left.join_asof(
        state,
        on="t",
        by=by,
        strategy="backward",
        allow_exact_matches=False,
        check_sortedness=False,
    ).drop("t")


def latest_asof(
    target: pl.DataFrame, table: pl.DataFrame, by: str, cols: list[str], shift: int = 0
) -> pl.DataFrame:
    """For attributes that hold until they change (age, draft pick, a depth chart): the latest
    row of `table` at or before the target game, `shift` weeks earlier. A game beyond the
    table's last week keeps the last known value."""
    right = table.select(by, week_index().alias("t"), *cols).sort("t")
    left = target.with_columns((week_index() - shift).alias("t")).sort("t")
    return left.join_asof(right, on="t", by=by, strategy="backward", check_sortedness=False).drop(
        "t"
    )


def train_seasons(season: int, available: list[int]) -> list[int]:
    """The seasons a model scoring `season` may train on: earlier ones, or for the first
    seasons (too few earlier ones) the other seasons of the early block."""
    ordered = sorted(available)
    prior = [s for s in ordered if s < season]
    if len(prior) >= MIN_TRAIN_SEASONS:
        return prior
    return [s for s in ordered[:EARLY_BLOCK] if s != season]
