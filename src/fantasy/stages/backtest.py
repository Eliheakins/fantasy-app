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
from fantasy.stages.learn import history_forecasts
from fantasy.stages.project import (
    FIRST_PROJECTED_SEASON,
    GROUP,
    build_form,
    expected_frame,
    position_prior,
    project_targets,
)

HORIZONS = (1, 5)
QUANTILES = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
TRAIN_END = 2023
MIN_MEAN = 0.5
ALL_TIERS = -1  # the tier value for the whole sample
N_TIERS = 3  # projection thirds, by the training seasons' baseline projections
FORECASTERS = {"baseline": "projection", "trailing_mean": "ewma_actual", "learned": "learned"}
MIN_LEARNED_WINS = 6  # of 8 league-positions, one game ahead
MAX_UNMATCHED = 0.02  # share of baseline rows that may lack a learned forecast
COVERAGE_GAP = 0.02  # the learned model's 80% coverage may differ from the baseline's by this


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


def size_tiers(train_projection: np.ndarray, projection: np.ndarray) -> np.ndarray:
    """0 to N_TIERS - 1: the projection's third, with edges taken from the training seasons."""
    edges = np.quantile(train_projection, np.linspace(0, 1, N_TIERS + 1)[1:-1])
    return np.digitize(projection, edges)


def metrics(rows: pl.DataFrame, horizon: int) -> pl.DataFrame:
    """rows: league_id, position, season, points, projection (the baseline), plus one mean column
    per forecaster. Each league and position is scored whole (tier ALL_TIERS) and by projection
    third, the spread fit on the training seasons of the same rows."""
    forecasters = {n: c for n, c in FORECASTERS.items() if c in rows.columns}
    out = []
    for (league_id, position), g in rows.group_by("league_id", "position"):
        is_train = pl.col("season") <= TRAIN_END
        train, test = g.filter(is_train), g.filter(~is_train)
        if train.is_empty() or test.is_empty():
            continue
        train_tier = size_tiers(train["projection"].to_numpy(), train["projection"].to_numpy())
        test_tier = size_tiers(train["projection"].to_numpy(), test["projection"].to_numpy())
        for tier in (ALL_TIERS, *range(N_TIERS)):
            keep_train = np.ones(train.height, bool) if tier == ALL_TIERS else train_tier == tier
            keep_test = np.ones(test.height, bool) if tier == ALL_TIERS else test_tier == tier
            if not keep_train.any() or not keep_test.any():
                print(
                    f"backtest: horizon {horizon} {league_id} {position} tier {tier}: "
                    f"no rows in {'train' if not keep_train.any() else 'test'}, skipped"
                )
                continue
            y_train = train["points"].to_numpy()[keep_train]
            y = test["points"].to_numpy()[keep_test]
            for name, column in forecasters.items():
                mu_train = np.maximum(train[column].to_numpy()[keep_train], MIN_MEAN)
                mu = np.maximum(test[column].to_numpy()[keep_test], MIN_MEAN)
                ratios = fit_ratios(y_train, mu_train)
                out.append(
                    {
                        "league_id": league_id,
                        "position": position,
                        "forecaster": name,
                        "horizon": horizon,
                        "n": len(y),
                        "tier": tier,
                        "rmse": float(np.sqrt(((y - mu) ** 2).mean())),
                        "mae": float(np.abs(y - mu).mean()),
                        "pinball": pinball(y, mu, ratios),
                        "coverage80": coverage80(y, mu, ratios),
                    }
                )
    return pl.DataFrame(out, schema=store.SCHEMAS["backtest_metrics"]).sort(
        "horizon", "league_id", "position", "tier", "forecaster"
    )


def verdict(m: pl.DataFrame) -> pl.DataFrame:
    """Per horizon and forecaster: sample-weighted pinball, RMSE and 80% coverage (whole sample)."""
    weighted = [(pl.col(c) * pl.col("n")).sum() / pl.col("n").sum() for c in ("pinball", "rmse")]
    return (
        m.filter(pl.col("tier") == ALL_TIERS)
        .group_by("horizon", "forecaster")
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
        learned = history_forecasts(horizon).rename({"projection": "learned"})
        scored = project_targets(targets, form, prior, games, horizon).filter(
            pl.col("has_history") & pl.col("ewma_actual").is_not_null()
        )
        rows = scored.join(learned, on=[*GROUP, "season", "week"], how="inner")
        lost = 1 - rows.height / scored.height
        print(
            f"backtest: horizon {horizon}: {rows.height} of {scored.height} rows "
            "have a learned forecast"
        )
        if lost > MAX_UNMATCHED:
            raise ValueError(f"horizon {horizon}: {lost:.1%} of rows have no learned forecast")
        parts.append(metrics(rows, horizon))
    result = pl.concat(parts)
    store.write_table("backtest_metrics", result)
    return result


def main() -> None:
    result = run()
    summary = verdict(result)
    print(summary)
    whole = result.filter(pl.col("tier") == ALL_TIERS)
    for horizon in HORIZONS:
        g = whole.filter(pl.col("horizon") == horizon)
        base = g.filter(pl.col("forecaster") == "baseline")["pinball"].to_numpy()
        naive = g.filter(pl.col("forecaster") == "trailing_mean")["pinball"].to_numpy()
        learned = g.filter(pl.col("forecaster") == "learned")["pinball"].to_numpy()
        beats_naive = int((base < naive).sum())
        print(
            f"horizon {horizon}: baseline beats trailing mean in {beats_naive} of {len(base)} "
            "league-positions"
        )
        wins = int((learned < base).sum())
        need = f", need {MIN_LEARNED_WINS}" if horizon == 1 else ""
        verdict_text = (
            "reported only" if horizon > 1 else ("PASS" if wins >= MIN_LEARNED_WINS else "FAIL")
        )
        print(
            f"horizon {horizon}: learned beats baseline in {wins} of {len(base)} "
            f"league-positions ({verdict_text}{need})"
        )
    tiers = (
        result.filter(pl.col("forecaster").is_in(["baseline", "learned"]))
        .group_by("horizon", "tier", "forecaster")
        .agg((pl.col("coverage80") * pl.col("n")).sum().truediv(pl.col("n").sum()).alias("cov80"))
        .pivot(on="forecaster", index=["horizon", "tier"], values="cov80")
        .sort("horizon", "tier")
    )
    print(tiers)
    # the lowest tier over-covers for every forecaster (the interval method), so the check is that
    # the learned model is no worse calibrated than the baseline, not an absolute range
    gap = float((tiers["learned"] - tiers["baseline"]).abs().max())  # type: ignore[arg-type]
    print(
        f"learned coverage within {COVERAGE_GAP:.0%} of the baseline's in every tier: "
        f"{'PASS' if gap <= COVERAGE_GAP else 'FAIL'} (largest gap {gap:.1%})"
    )


if __name__ == "__main__":
    main()
