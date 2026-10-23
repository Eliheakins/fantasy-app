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
    by_name = {r["forecaster"]: r for r in m.to_dicts()}
    assert by_name["baseline"]["n"] == n // 2  # only the test season is scored
    assert by_name["baseline"]["pinball"] < by_name["trailing_mean"]["pinball"]
    assert by_name["baseline"]["rmse"] < by_name["trailing_mean"]["rmse"]
    assert set(b.verdict(m)["forecaster"]) == {"baseline", "trailing_mean"}
