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

import numpy as np
import polars as pl

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
