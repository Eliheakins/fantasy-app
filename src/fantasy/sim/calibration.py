"""Calibrate the baseline projection by how big it is.

Walk-forward projections 2019 to 2025 against actual points show the baseline over-projects
low-projected players (running backs below about 6 points score 73% of it on average) and
slightly under-projects the top third (about 104% to 105% at RB, WR and TE). Calibrating the
mean by projection level cut mean absolute error 2.75% and RMSE 0.6% out of sample (fit on
2019 to 2023, scored on 2024 to 2025).

The curve is piecewise linear through the factor (points over projection) at the median
projection of each of CALIBRATION_BINS quantile bins, flat beyond the ends. It is estimated in
`stages/distributions.py` per league and position. Our baseline is calibrated before it is
blended with Sleeper's projections, which have their own bias.
"""

from pathlib import Path

import numpy as np
import polars as pl

from fantasy import store

CALIBRATION_BINS = 8


def apply_curves(frame: pl.DataFrame, curves: pl.DataFrame) -> pl.DataFrame:
    """`frame` (league_id, position, projection) with `projection` multiplied by the factor for
    its league and position. A league and position without a curve is left alone. Other columns
    are kept."""
    out = []
    indexed = frame.with_row_index("_row")
    for (league_id, position), group in indexed.group_by(
        "league_id", "position", maintain_order=True
    ):
        rows = curves.filter((pl.col("league_id") == league_id) & (pl.col("position") == position))
        if rows.is_empty():
            out.append(group)
            continue
        rows = rows.sort("center")
        # points over projection expected at each projection
        scale = np.interp(
            group["projection"].to_numpy(), rows["center"].to_numpy(), rows["factor"].to_numpy()
        )
        out.append(
            group.with_columns((pl.col("projection") * pl.Series(scale)).alias("projection"))
        )
    return pl.concat(out).sort("_row").drop("_row") if out else frame


def tier_of(edges: list[float], projection: float) -> int:
    """0, 1 or 2: the tier of a projection given the two upper edges of tiers 0 and 1."""
    return int(sum(projection > edge for edge in edges))


TRAIN_END = 2023


MIN_MEAN = 0.5


ALL_TIERS = -1  # the tier value for the whole sample


N_TIERS = 3  # projection thirds, by the training seasons' baseline projections


def size_tiers(train_projection: np.ndarray, projection: np.ndarray) -> np.ndarray:
    """0 to N_TIERS - 1: the projection's third, with edges taken from the training seasons."""
    edges = np.quantile(train_projection, np.linspace(0, 1, N_TIERS + 1)[1:-1])
    return np.digitize(projection, edges)


def calibrated(frame: pl.DataFrame, data_dir: Path | None = None) -> pl.DataFrame:
    """`frame` (league_id, position, projection) with the projection calibrated by size, when the
    curves have been estimated; otherwise unchanged. The learned projection is left alone: held
    out, the curves made it slightly worse (RMSE up in 7 of 8 league-seasons, mean error shifted by
    0.1 to 0.3 points), because it is already trained to be unbiased."""
    if store.projection_name(data_dir) == "proj_learned":
        return frame
    try:
        curves = store.read_table("projection_calibration", data_dir=data_dir)
    except FileNotFoundError:
        return frame
    return apply_curves(frame, curves)
