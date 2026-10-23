import math

import polars as pl
import pytest

from fantasy.stages import distributions as d

RES_SCHEMA = {
    "league_id": pl.String,
    "gsis_id": pl.String,
    "season": pl.Int64,
    "week": pl.Int64,
    "position": pl.String,
    "team": pl.String,
    "projection": pl.Float64,
    "resid": pl.Float64,
}


def res(rows: list[tuple[str, str, int, int, str, str, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=RES_SCHEMA, orient="row")


def test_gaussian_rho_endpoints_and_middle() -> None:
    assert d.gaussian_rho(0.0) == 0.0
    assert d.gaussian_rho(1.0) == pytest.approx(1.0)
    assert d.gaussian_rho(0.5) == pytest.approx(2 * math.sin(math.pi / 12))


def test_cv_is_root_of_squared_residuals_over_squared_projections() -> None:
    # projections 10 and 20, residuals +5 and -10: sqrt((25 + 100) / (100 + 400)) = 0.5
    frame = res(
        [
            ("L", "a", 2025, 1, "WR", "KC", 10.0, 5.0),
            ("L", "b", 2025, 1, "WR", "KC", 20.0, -10.0),
        ]
    )
    out = d.estimate_cv(frame)
    assert out["cv"].item() == pytest.approx(0.5) and out["n"].item() == 2


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
