import math

import polars as pl
import pytest
from test_odds import toy_league

from fantasy.stages import calibration as c


def test_standardized_miss_uses_the_projection_mean_and_spread() -> None:
    data = toy_league()
    starters = pl.DataFrame(
        {"roster_id": [1], "week": [3], "gsis_id": ["t1_wr1"], "position": ["WR"]},
        schema={
            "roster_id": pl.Int64,
            "week": pl.Int64,
            "gsis_id": pl.String,
            "position": pl.String,
        },
    )
    projections = {("t1_wr1", 3): 10.0}
    out = c.team_week_scores(data, starters, projections, {(1, 3): 17.0})
    row = out.row(0, named=True)
    assert row["mean"] == pytest.approx(10.0)
    # one WR: sd = 10 * 0.7 = 7, plus 2 points of team drift
    assert row["sd"] == pytest.approx(math.sqrt(49 + 4))
    assert row["z"] == pytest.approx(7 / math.sqrt(53))
    assert row["missing"] == 0


def test_a_starter_without_a_projection_is_counted_not_guessed() -> None:
    data = toy_league()
    starters = pl.DataFrame(
        {
            "roster_id": [1, 1],
            "week": [3, 3],
            "gsis_id": ["t1_wr1", None],
            "position": ["WR", "RB"],
        },
        schema={
            "roster_id": pl.Int64,
            "week": pl.Int64,
            "gsis_id": pl.String,
            "position": pl.String,
        },
    )
    out = c.team_week_scores(data, starters, {("t1_wr1", 3): 10.0}, {(1, 3): 10.0})
    assert out["missing"].item() == 1 and out["mean"].item() == pytest.approx(10.0)


def test_summary_counts_standard_normal_coverage() -> None:
    z = [0.0, 0.3, -0.5, 1.0, -1.1, 1.5, -2.0, 0.1, -0.2, 0.9]
    s = c.summarize(pl.DataFrame({"z": z}))
    assert s["n"] == 10
    assert s["coverage80"] == pytest.approx(0.8)  # |z| <= 1.28 for 8 of 10
    assert s["coverage50"] == pytest.approx(0.5)  # |z| <= 0.67 for 5 of 10
