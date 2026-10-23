import math

import numpy as np
import polars as pl
import pytest

from fantasy import store
from fantasy.stages import distributions as d

RES_SCHEMA = {
    "league_id": pl.String,
    "gsis_id": pl.String,
    "season": pl.Int64,
    "week": pl.Int64,
    "position": pl.String,
    "team": pl.String,
    "projection": pl.Float64,
    "points": pl.Float64,
    "resid": pl.Float64,
}


def res(rows: list[tuple[str, str, int, int, str, str, float, float]]) -> pl.DataFrame:
    """rows: league, player, season, week, position, team, projection, resid."""
    data = [(*r[:7], r[6] + r[7], r[7]) for r in rows]
    return pl.DataFrame(data, schema=RES_SCHEMA, orient="row")


def test_gaussian_rho_endpoints_and_middle() -> None:
    assert d.gaussian_rho(0.0) == 0.0
    assert d.gaussian_rho(1.0) == pytest.approx(1.0)
    assert d.gaussian_rho(0.5) == pytest.approx(2 * math.sin(math.pi / 12))


def test_marginals_are_quantiles_of_actual_over_projection() -> None:
    # actual = 1.5 x projection for every row, so every ratio quantile is 1.5
    rows = [("L", f"p{i}", 2025, 1, "WR", "KC", 10.0, 5.0) for i in range(50)]
    out = d.estimate_marginals(res(rows))
    store.check_schema("marginals", out)
    assert out.height == 99
    assert out["ratio"].to_list() == pytest.approx([1.5] * 99)
    assert out["n"].unique().to_list() == [50]


def test_marginals_capture_a_heavy_lower_tail() -> None:
    rng = np.random.default_rng(0)
    actual = np.where(rng.random(2000) < 0.2, 0.05, 1.2)  # one game in five is a dud
    rows = [
        ("L", f"p{i}", 2025, 1, "RB", "KC", 10.0, a * 10.0 - 10.0) for i, a in enumerate(actual)
    ]
    out = d.estimate_marginals(res(rows))
    low = out.filter(pl.col("tau") == 0.1)["ratio"].item()
    high = out.filter(pl.col("tau") == 0.9)["ratio"].item()
    assert low < 0.1 and high == pytest.approx(1.2)


def test_roles_rank_by_projection_within_team_and_position() -> None:
    frame = res(
        [
            ("L", "q1", 2025, 1, "QB", "KC", 20.0, 0.0),
            ("L", "q2", 2025, 1, "QB", "KC", 5.0, 0.0),
            ("L", "w1", 2025, 1, "WR", "KC", 12.0, 0.0),
            ("L", "w2", 2025, 1, "WR", "KC", 9.0, 0.0),
        ]
    )
    roles = dict(d.with_roles(frame).select("gsis_id", "role").iter_rows())
    assert roles == {"q1": "QB1", "w1": "WR1", "w2": "WR2"}  # the backup QB is dropped


def test_same_team_pairs_recover_a_perfect_rank_correlation() -> None:
    rows = []
    for i in range(250):  # 250 distinct teams in one week
        rows.append(("L", f"q{i}", 2025, 1, "QB", f"T{i}", 20.0, float(i)))
        rows.append(("L", f"w{i}", 2025, 1, "WR", f"T{i}", 12.0, float(i) * 2))
    games = pl.DataFrame(
        {"season": [2025], "week": [1], "team": ["T0"], "opponent": ["X"]},
        schema={"season": pl.Int64, "week": pl.Int64, "team": pl.String, "opponent": pl.String},
    )
    out = d.estimate_pairs(d.with_roles(res(rows)), games)
    row = out.filter(pl.col("relation") == "same_team").to_dicts()[0]
    assert (row["role_a"], row["role_b"], row["n"]) == ("QB1", "WR1", 250)
    assert row["rho"] == pytest.approx(1.0)


def test_pairs_below_the_minimum_sample_are_dropped() -> None:
    rows = [
        ("L", "q", 2025, 1, "QB", "KC", 20.0, 1.0),
        ("L", "w", 2025, 1, "WR", "KC", 12.0, 2.0),
    ]
    games = pl.DataFrame(
        {"season": [2025], "week": [1], "team": ["KC"], "opponent": ["X"]},
        schema={"season": pl.Int64, "week": pl.Int64, "team": pl.String, "opponent": pl.String},
    )
    assert d.estimate_pairs(d.with_roles(res(rows)), games).is_empty()
