import numpy as np
import polars as pl
import pytest

from fantasy import store
from fantasy.stages import backtest as b


def test_ratios_recover_the_shape_of_actual_over_forecast() -> None:
    rng = np.random.default_rng(0)
    mu = np.full(20000, 10.0)
    y = mu * rng.gamma(4.0, 0.25, 20000)  # ratio has mean 1
    ratios = b.fit_ratios(y, mu)
    assert b.predict(0.5, np.array([10.0]), ratios)[0] == pytest.approx(np.median(y), rel=0.02)


def test_pinball_is_lower_when_the_mean_is_right() -> None:
    rng = np.random.default_rng(1)
    truth = rng.uniform(5, 15, 6000)
    y = rng.gamma(4.0, truth / 4.0)
    right = b.fit_ratios(y, truth)
    wrong = b.fit_ratios(y, np.full(6000, 10.0))
    assert b.pinball(y, truth, right) < b.pinball(y, np.full(6000, 10.0), wrong)


def test_interval_is_calibrated_out_of_sample() -> None:
    rng = np.random.default_rng(2)
    mu = rng.uniform(5, 15, 40000)
    y = rng.gamma(2.0, mu / 2.0)
    ratios = b.fit_ratios(y[:20000], mu[:20000])
    assert b.coverage80(y[20000:], mu[20000:], ratios) == pytest.approx(0.8, abs=0.015)


def test_metrics_split_by_season_and_prefer_the_informed_forecaster() -> None:
    rng = np.random.default_rng(3)
    n = 6000
    truth = rng.uniform(5, 15, n)
    rows = pl.DataFrame(
        {
            "league_id": ["L"] * n,
            "position": ["WR"] * n,
            "season": [2022, 2025] * (n // 2),
            "points": rng.gamma(4.0, truth / 4.0),
            "projection": truth,  # knows the true mean
            "ewma_actual": np.full(n, 10.0),  # ignores it
        }
    )
    m = b.metrics(rows, horizon=1)
    store.check_schema("backtest_metrics", m)
    by_name = {r["forecaster"]: r for r in m.filter(pl.col("tier") == b.ALL_TIERS).to_dicts()}
    assert by_name["baseline"]["n"] == n // 2  # only the test season is scored
    assert by_name["baseline"]["pinball"] < by_name["trailing_mean"]["pinball"]
    assert by_name["baseline"]["rmse"] < by_name["trailing_mean"]["rmse"]
    assert set(b.verdict(m)["forecaster"]) == {"baseline", "trailing_mean"}


def sized_rows(n: int = 6000) -> pl.DataFrame:
    rng = np.random.default_rng(4)
    truth = rng.uniform(1, 30, n)
    return pl.DataFrame(
        {
            "league_id": ["L"] * n,
            "position": ["WR"] * n,
            "season": [2022, 2025] * (n // 2),
            "points": rng.gamma(4.0, truth / 4.0),
            "projection": truth,
            "ewma_actual": np.full(n, 10.0),
            "learned": truth * 1.01,
        }
    )


def test_metrics_report_each_size_tier_and_the_whole_sample() -> None:
    m = b.metrics(sized_rows(), horizon=1)
    base = m.filter(pl.col("forecaster") == "baseline")
    assert set(base["tier"].to_list()) == {b.ALL_TIERS, 0, 1, 2}
    whole = base.filter(pl.col("tier") == b.ALL_TIERS)["n"].item()
    assert base.filter(pl.col("tier") >= 0)["n"].sum() == whole


def test_a_learned_column_adds_a_learned_forecaster() -> None:
    m = b.metrics(sized_rows(), horizon=1)
    assert set(m["forecaster"]) == {"baseline", "trailing_mean", "learned"}
    assert set(b.verdict(m)["forecaster"]) == {"baseline", "trailing_mean", "learned"}


def test_tier_edges_come_from_the_training_seasons() -> None:
    rows = sized_rows().with_columns(
        pl.when(pl.col("season") == 2025)
        .then(pl.col("projection") + 100.0)  # every test projection is above every training one
        .otherwise(pl.col("projection"))
        .alias("projection")
    )
    m = b.metrics(rows, horizon=1).filter(pl.col("forecaster") == "baseline")
    assert (
        m.filter(pl.col("tier") == 2)["n"].item()
        == m.filter(pl.col("tier") == b.ALL_TIERS)["n"].item()
    )


def test_coverage_by_tier_is_near_the_nominal_level() -> None:
    m = b.metrics(sized_rows(60000), horizon=1).filter(pl.col("forecaster") == "learned")
    assert all(0.74 < c < 0.86 for c in m["coverage80"].to_list())
