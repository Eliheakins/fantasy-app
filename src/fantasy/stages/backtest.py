"""Walk-forward backtest: does the baseline beat a trailing average, 1 and 5 weeks ahead?

Each forecaster gives a mean. The distribution around it is the empirical quantiles of
actual / forecast, fitted on seasons up to TRAIN_END and scored on later seasons, so pinball
loss and interval coverage are out of sample. Fitting each forecaster's own spread keeps the
comparison about the means, not about who happened to guess a better spread.

Run: uv run python -m fantasy.stages.backtest
"""

import numpy as np
import polars as pl

from fantasy import store
from fantasy.stages.distributions import LEVELS
from fantasy.stages.project import (
    FIRST_PROJECTED_SEASON,
    build_form,
    expected_frame,
    position_prior,
    project_targets,
)

HORIZONS = (1, 5)
QUANTILES = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
TRAIN_END = 2023
MIN_MEAN = 0.5
FORECASTERS = {"baseline": "projection", "trailing_mean": "ewma_actual"}


def fit_ratios(y: np.ndarray, mu: np.ndarray) -> np.ndarray:
    """Quantiles (at LEVELS) of actual / forecast."""
    return np.quantile(y / mu, LEVELS)


def predict(tau: float, mu: np.ndarray, ratios: np.ndarray) -> np.ndarray:
    return np.asarray(mu * np.interp(tau, LEVELS, ratios))


def pinball(y: np.ndarray, mu: np.ndarray, ratios: np.ndarray) -> float:
    """Pinball loss of the forecast distribution, averaged over QUANTILES."""
    losses = []
    for q in QUANTILES:
        d = y - predict(q, mu, ratios)
        losses.append(np.maximum(q * d, (q - 1) * d).mean())
    return float(np.mean(losses))


def coverage80(y: np.ndarray, mu: np.ndarray, ratios: np.ndarray) -> float:
    inside = (y >= predict(0.1, mu, ratios)) & (y <= predict(0.9, mu, ratios))
    return float(inside.mean())


def metrics(rows: pl.DataFrame, horizon: int) -> pl.DataFrame:
    """rows: league_id, position, season, points, plus one mean column per forecaster."""
    out = []
    for (league_id, position), g in rows.group_by("league_id", "position"):
        is_train = pl.col("season") <= TRAIN_END
        train, test = g.filter(is_train), g.filter(~is_train)
        if train.is_empty() or test.is_empty():
            continue
        for name, column in FORECASTERS.items():
            mu_train = np.maximum(train[column].to_numpy(), MIN_MEAN)
            mu = np.maximum(test[column].to_numpy(), MIN_MEAN)
            y = test["points"].to_numpy()
            ratios = fit_ratios(train["points"].to_numpy(), mu_train)
            out.append(
                {
                    "league_id": league_id,
                    "position": position,
                    "forecaster": name,
                    "horizon": horizon,
                    "n": len(y),
                    "rmse": float(np.sqrt(((y - mu) ** 2).mean())),
                    "mae": float(np.abs(y - mu).mean()),
                    "pinball": pinball(y, mu, ratios),
                    "coverage80": coverage80(y, mu, ratios),
                }
            )
    return pl.DataFrame(out, schema=store.SCHEMAS["backtest_metrics"]).sort(
        "horizon", "league_id", "position", "forecaster"
    )


def verdict(m: pl.DataFrame) -> pl.DataFrame:
    """Per horizon and forecaster: sample-weighted pinball, RMSE and 80% coverage."""
    weighted = [(pl.col(c) * pl.col("n")).sum() / pl.col("n").sum() for c in ("pinball", "rmse")]
    return (
        m.group_by("horizon", "forecaster")
        .agg(
            weighted[0].alias("pinball"),
            weighted[1].alias("rmse"),
            (pl.col("coverage80") * pl.col("n")).sum().truediv(pl.col("n").sum()).alias("cov80"),
            pl.col("n").sum(),
        )
        .sort("horizon", "forecaster")
    )


def run() -> pl.DataFrame:
    leagues = store.read_table("leagues", "raw")
    exp = expected_frame(
        store.read_table("nfl_ff_opportunity", "raw"), store.read_table("player_points"), leagues
    )
    prior = position_prior(exp)
    form = build_form(exp, prior)
    games = store.read_table("team_games")
    targets = exp.filter(pl.col("season") >= FIRST_PROJECTED_SEASON).select(
        "league_id", "gsis_id", "season", "week", "position", "team", "points"
    )
    parts = []
    for horizon in HORIZONS:
        rows = project_targets(targets, form, prior, games, horizon).filter(
            pl.col("has_history") & pl.col("ewma_actual").is_not_null()
        )
        parts.append(metrics(rows, horizon))
    result = pl.concat(parts)
    store.write_table("backtest_metrics", result)
    return result


def main() -> None:
    result = run()
    summary = verdict(result)
    print(summary)
    for horizon in HORIZONS:
        g = result.filter(pl.col("horizon") == horizon)
        base = g.filter(pl.col("forecaster") == "baseline")["pinball"].to_numpy()
        naive = g.filter(pl.col("forecaster") == "trailing_mean")["pinball"].to_numpy()
        wins = int((base < naive).sum())
        print(f"horizon {horizon}: baseline wins {wins} of {len(base)} league-positions")


if __name__ == "__main__":
    main()
