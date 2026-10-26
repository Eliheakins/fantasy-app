"""Idea 3: does a distributional model beat the tier marginals for the spread around the mean?

Rows: the backtest's one-game-ahead rows (has history, a trailing mean, a learned forecast),
mean floored at 0.5. Scored walk-forward on 2024, 2025 and 2026, each league separately.

Spreads compared (quantiles at the backtest's levels 0.05 to 0.95):
  tiers      the reference: learned mean times ratio quantiles (actual / mean) per league,
             position and size tier, fit on 2021 to 2023 (never on learned 2019 or 2020)
  prod       as `distributions.run` builds them: ratios against the size-calibrated learned mean,
             applied to the raw learned mean (as the simulation does)
  tiers_wf   (c) the reference refit walk-forward: ratios from 2021 to the season before
  qgbm       (a) HistGradientBoosting, loss quantile, one model per level, learn's features and
             settings, trained on every season before the scored one; quantiles sorted per row
  cqr        (b) qgbm plus a per league, position and level additive offset: the level's quantile
             of (actual - prediction) on the season before, predicted by a model that did not see it
  cqr_split  (b) the textbook split: the model trained two seasons back, offset from the season
             between

Size tiers for fitting and reporting are the backtest's: thirds of the baseline projection with
edges from seasons up to 2023. Run: OMP_NUM_THREADS=3 uv run python research/quantile_check.py
(the quantile fits are cached in research/scratch; pass --refit to redo them).
"""

import sys
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingRegressor

from fantasy import store
from fantasy.sim.calibration import apply_curves
from fantasy.stages import learn
from fantasy.stages.backtest import MIN_MEAN, QUANTILES, TRAIN_END, size_tiers
from fantasy.stages.distributions import LEVELS, estimate_curves
from fantasy.stages.project import (
    FIRST_PROJECTED_SEASON,
    GROUP,
    build_form,
    expected_frame,
    history_targets,
    position_prior,
    project_targets,
)

SCORED = (2024, 2025, 2026)
FIRST_FIT = 2021  # learned projections before this came from models that saw later seasons
FIT_ENDS = (2022, 2023, 2024, 2025)  # quantile models trained on seasons up to each
CORE = (0.1, 0.25, 0.5, 0.75, 0.9)
KEYS = [*GROUP, "season", "week"]
ORDER = ["season", *GROUP, "week"]  # scored rows, season blocks stacked in this order
QCOLS = [f"q{int(round(q * 100)):02d}" for q in QUANTILES]
CACHE = Path(__file__).parent / "scratch" / "quantile_preds.parquet"
METHODS = ("tiers", "prod", "tiers_wf", "qgbm", "cqr", "cqr_split")
LEAGUE_NAME = {"1394105943137992704": "Colgate", "1385108353306361856": "YinzBurgh"}


def features_by_league() -> dict[str, pl.DataFrame]:
    """learn.history_forecasts(1) up to the walk-forward, keeping the feature rows."""
    leagues = store.read_table("leagues", "raw")
    opp = store.read_table("nfl_ff_opportunity", "raw")
    exp = expected_frame(opp, store.read_table("player_points"), leagues)
    games_all = learn.games_frame(
        exp, opp, store.read_table("nfl_snaps", "raw"), store.read_table("nfl_player_stats", "raw")
    )
    lines = store.read_table("team_games")
    extras = learn.load_extras()
    out = {}
    for lid in leagues["league_id"].to_list():
        games = games_all.filter(pl.col("league_id") == lid)
        targets = history_targets(exp.filter(pl.col("league_id") == lid))
        feats = learn.build_features(targets, learn.state_frame(games), lines, extras, 1)
        out[lid] = feats.join(games.select(*KEYS, "points"), on=KEYS)
    return out


def fit_quantiles(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray) -> np.ndarray:
    """(n_test, len(QUANTILES)), learn.fit_predict's settings with the quantile loss."""
    usable = [j for j in range(x_train.shape[1]) if learn._varies(x_train[:, j])]
    x_train, x_test = x_train[:, usable], x_test[:, usable]
    cols = []
    for q in QUANTILES:
        model = HistGradientBoostingRegressor(
            loss="quantile",
            quantile=q,
            max_iter=400,
            learning_rate=0.03,
            max_leaf_nodes=15,
            min_samples_leaf=80,
            l2_regularization=5.0,
            random_state=0,
        )
        model.fit(x_train, y_train)
        cols.append(model.predict(x_test))
    return np.clip(np.column_stack(cols), 0.0, None)


def quantile_predictions(feats: dict[str, pl.DataFrame]) -> pl.DataFrame:
    parts = []
    for lid, history in feats.items():
        for fit_end in FIT_ENDS:
            train = history.filter(pl.col("season") <= fit_end)
            test = history.filter(pl.col("season") > fit_end)
            pred = fit_quantiles(
                learn.design(train, True), train["points"].to_numpy(), learn.design(test, True)
            )
            print(f"qgbm {LEAGUE_NAME[lid]} fit to {fit_end}: {train.height} train rows")
            parts.append(
                test.select(KEYS)
                .with_columns(pl.lit(fit_end).alias("fit_end"))
                .hstack(pl.DataFrame(pred, schema=QCOLS))
            )
    return pl.concat(parts)


def scored_rows(feats: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """The backtest's horizon-1 rows with the learned mean (learn.walk_forward on the same
    features as history_forecasts(1))."""
    leagues = store.read_table("leagues", "raw")
    exp = expected_frame(
        store.read_table("nfl_ff_opportunity", "raw"), store.read_table("player_points"), leagues
    )
    prior = position_prior(exp)
    form = build_form(exp, prior)
    targets = exp.filter(pl.col("season") >= FIRST_PROJECTED_SEASON).select(
        "league_id", "gsis_id", "season", "week", "position", "team", "points"
    )
    scored = project_targets(targets, form, prior, store.read_table("team_games"), 1).filter(
        pl.col("has_history") & pl.col("ewma_actual").is_not_null()
    )
    learned = pl.concat(
        learn.walk_forward(h).select(*KEYS, pl.col("projection").alias("learned"))
        for h in feats.values()
    )
    rows = scored.join(learned, on=KEYS, how="inner")
    assert rows.select(KEYS).is_duplicated().sum() == 0
    print(f"rows: {rows.height} of {scored.height} backtest rows have a learned forecast")
    return rows.select(*KEYS, "position", "points", "projection", "learned")


def with_tiers(rows: pl.DataFrame) -> pl.DataFrame:
    """The backtest's tier per row: baseline-projection thirds, edges from seasons <= 2023."""
    parts = []
    for _, g in rows.group_by("league_id", "position"):
        train = g.filter(pl.col("season") <= TRAIN_END)["projection"].to_numpy()
        parts.append(g.with_columns(pl.Series("tier", size_tiers(train, g["projection"].to_numpy()))))
    return pl.concat(parts)


def ratio_quantiles(fit: pl.DataFrame, apply: pl.DataFrame, mean_col: str) -> np.ndarray:
    """(apply rows, QUANTILES): learned mean times ratio quantiles per league, position, tier,
    the ratios measured against `mean_col` on `fit`."""
    out = np.full((apply.height, len(QUANTILES)), np.nan)
    idx = apply.with_row_index("_i")
    for (lid, pos, tier), g in idx.group_by("league_id", "position", "tier"):
        f = fit.filter(
            (pl.col("league_id") == lid) & (pl.col("position") == pos) & (pl.col("tier") == tier)
        )
        ratios = np.quantile(f["points"].to_numpy() / np.maximum(f[mean_col].to_numpy(), MIN_MEAN), LEVELS)
        mu = np.maximum(g["learned"].to_numpy(), MIN_MEAN)
        out[g["_i"].to_numpy()] = mu[:, None] * np.interp(QUANTILES, LEVELS, ratios)[None, :]
    return out


def calibrated_learned(fit: pl.DataFrame) -> pl.DataFrame:
    """`fit` with `cal`: the learned mean calibrated by size with curves fit on `fit` itself, as
    distributions.run does before it measures the ratios."""
    frame = fit.with_columns(pl.col("learned").alias("projection"))
    curves = estimate_curves(frame)
    return fit.with_columns(apply_curves(frame, curves)["projection"].alias("cal"))


def conformal(pred: pl.DataFrame, calib: pl.DataFrame) -> np.ndarray:
    """pred's quantiles plus, per league, position and level, the level's quantile of
    (actual - predicted) on `calib`."""
    out = pred.select(QCOLS).to_numpy().copy()
    idx = pred.with_row_index("_i")
    for (lid, pos), g in idx.group_by("league_id", "position"):
        c = calib.filter((pl.col("league_id") == lid) & (pl.col("position") == pos))
        y = c["points"].to_numpy()
        offsets = [np.quantile(y - c[col].to_numpy(), q) for col, q in zip(QCOLS, QUANTILES)]
        out[g["_i"].to_numpy()] += np.array(offsets)[None, :]
    return np.clip(out, 0.0, None)


def sorted_q(frame: pl.DataFrame) -> np.ndarray:
    return np.sort(frame.select(QCOLS).to_numpy(), axis=1)


def predictions(rows: pl.DataFrame, qp: pl.DataFrame) -> dict[str, np.ndarray]:
    """Per method, (rows, QUANTILES) for the scored seasons; rows sorted by KEYS."""
    test = rows.filter(pl.col("season").is_in(SCORED)).sort(ORDER)
    out: dict[str, list[np.ndarray]] = {m: [] for m in METHODS}
    ref_fit = rows.filter(pl.col("season").is_between(FIRST_FIT, TRAIN_END))
    prod_fit = calibrated_learned(ref_fit)
    for season in SCORED:
        t = test.filter(pl.col("season") == season)
        out["tiers"].append(ratio_quantiles(ref_fit, t, "learned"))
        out["prod"].append(ratio_quantiles(prod_fit, t, "cal"))
        wf_fit = rows.filter(pl.col("season").is_between(FIRST_FIT, season - 1))
        out["tiers_wf"].append(ratio_quantiles(wf_fit, t, "learned"))
        base = t.select(*KEYS, "position")
        now = base.join(qp.filter(pl.col("fit_end") == season - 1), on=KEYS, how="left", maintain_order="left")
        back = base.join(qp.filter(pl.col("fit_end") == season - 2), on=KEYS, how="left", maintain_order="left")
        calib = (
            rows.filter(pl.col("season") == season - 1)
            .join(qp.filter(pl.col("fit_end") == season - 2), on=KEYS)
        )
        assert now[QCOLS[0]].null_count() == 0 and back[QCOLS[0]].null_count() == 0
        out["qgbm"].append(sorted_q(now))
        out["cqr"].append(np.sort(conformal(now, calib), axis=1))
        out["cqr_split"].append(np.sort(conformal(back, calib), axis=1))
    return {m: np.vstack(v) for m, v in out.items()}


def row_pinball(y: np.ndarray, q: np.ndarray, levels: tuple[float, ...]) -> np.ndarray:
    cols = [QUANTILES.index(lv) for lv in levels]
    d = y[:, None] - q[:, cols]
    lv = np.array(levels)[None, :]
    return np.maximum(lv * d, (lv - 1) * d).mean(axis=1)


def score_frame(rows: pl.DataFrame, preds: dict[str, np.ndarray]) -> pl.DataFrame:
    test = rows.filter(pl.col("season").is_in(SCORED)).sort(ORDER)
    y = test["points"].to_numpy()
    cols = {}
    for m, q in preds.items():
        cols[f"pb7_{m}"] = row_pinball(y, q, QUANTILES)
        cols[f"pb5_{m}"] = row_pinball(y, q, CORE)
        lo, hi = q[:, QUANTILES.index(0.1)], q[:, QUANTILES.index(0.9)]
        cols[f"cov_{m}"] = ((y >= lo) & (y <= hi)).astype(float)
    med = preds["qgbm"][:, QUANTILES.index(0.5)]
    cols["ae_median"] = np.abs(y - med)
    cols["ae_learned"] = np.abs(y - np.maximum(test["learned"].to_numpy(), MIN_MEAN))
    return test.with_columns(**{k: pl.Series(v) for k, v in cols.items()}).with_columns(
        pl.col("league_id").replace_strict(LEAGUE_NAME).alias("league")
    )


def summary(s: pl.DataFrame, by: list[str]) -> pl.DataFrame:
    aggs = [pl.len().alias("n")]
    for m in METHODS:
        aggs += [pl.col(f"pb7_{m}").mean().round(4).alias(m)]
    for m in METHODS:
        aggs += [pl.col(f"cov_{m}").mean().round(3).alias(f"c80_{m}")]
    return s.group_by(by).agg(aggs).sort(by)


def paired(s: pl.DataFrame, by: list[str], col: str = "pb7") -> pl.DataFrame:
    """Per group, each candidate against tiers: gain %, per-week paired t, weeks better."""
    out = []
    for key, g in s.group_by(by):
        wk = g.group_by("season", "week").agg([pl.col(f"{col}_{m}").mean() for m in METHODS])
        ref = wk[f"{col}_tiers"].to_numpy()
        for m in METHODS[1:]:
            d = ref - wk[f"{col}_{m}"].to_numpy()
            gain = 100 * (g[f"{col}_tiers"].mean() - g[f"{col}_{m}"].mean()) / g[f"{col}_tiers"].mean()
            t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d))) if len(d) > 1 else float("nan")
            out.append(
                dict(zip(by, key))
                | {"method": m, "gain_pct": round(gain, 2), "t": round(float(t), 2),
                   "weeks_better": f"{int((d > 0).sum())}/{len(d)}"}
            )
    return pl.DataFrame(out).sort([*by, "method"])


def main() -> None:
    feats = features_by_league()
    if CACHE.exists() and "--refit" not in sys.argv:
        qp = pl.read_parquet(CACHE)
    else:
        qp = quantile_predictions(feats)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        qp.write_parquet(CACHE)
    rows = with_tiers(scored_rows(feats))
    s = score_frame(rows, predictions(rows, qp))
    with pl.Config(tbl_rows=200, tbl_cols=30, tbl_width_chars=250):
        print("\npinball over backtest levels (0.05..0.95) and 80% coverage")
        print(summary(s, ["league"]))
        print(summary(s, ["league", "season"]))
        print(summary(s, ["league", "position"]))
        print(summary(s, ["league", "tier"]))
        print("\npinball over 0.1/0.25/0.5/0.75/0.9")
        print(s.group_by("league").agg([pl.col(f"pb5_{m}").mean().round(4).alias(m) for m in METHODS]).sort("league"))
        print("\nagainst tiers, pinball over backtest levels: per-week paired t")
        print(paired(s, ["league"]))
        print(paired(s, ["league", "season"]))
        print("\nagainst tiers, pinball over the five core levels")
        print(paired(s, ["league"], "pb5"))
        print("\nside note: MAE of the qgbm median against the learned mean")
        print(s.group_by("league").agg(pl.col("ae_median").mean().round(4), pl.col("ae_learned").mean().round(4)).sort("league"))


if __name__ == "__main__":
    main()
