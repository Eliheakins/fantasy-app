"""Idea 6: stack the learned GBM, ridge and the rolling baseline with non-negative weights.

Learners, each predicted walk-forward (a season is predicted only by models trained on earlier
seasons, as `learn.walk_forward`):
- `learned`: the current GBM (recomputed from code; must match `proj_learned` exactly);
- `ridge`: ridge on the same design matrix (median imputation plus missing indicators,
  standardized), pooled over positions; `ridge_pos`: the same per position. Alpha is chosen on
  the last training season with a model fit on the earlier ones, then refit on all of them;
- `baseline`: proj_baseline size-calibrated with curves from earlier seasons only.

Stack weights are fit walk-forward per league: for season s on the out-of-fold rows of 2021 to
s - 1, scored on s (2024 on). Weights are non-negative; an intercept, where used, is free.
Variants: per position or pooled, with or without intercept. Rows are the compare_to_baseline
population (has_history, calibrated baseline above 3 points). Learned projections of 2019 and
2020 are never fit on.

Run from the repo root: OMP_NUM_THREADS=3 uv run python research/stack_check.py
"""

import sys
from pathlib import Path

import numpy as np
import polars as pl
from scipy.optimize import lsq_linear
from sklearn.linear_model import Ridge

sys.path.insert(0, str(Path(__file__).parent))
import wf_panel as w  # noqa: E402

from fantasy.stages.learn import design  # noqa: E402

FIRST_OOF = 2021  # first season whose out-of-fold rows may fit a stack (2019, 2020 contaminated)
SCORED = [2024, 2025, 2026]
ALPHAS = (0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0)
LEARNERS = ["learned", "ridge", "ridge_pos", "baseline"]
POSITIONS = ("QB", "RB", "WR", "TE")


class Prep:
    """Median imputation, missing indicators and standardization, fit on training rows."""

    def __init__(self, x: np.ndarray) -> None:
        self.keep = np.where(np.isfinite(x).any(axis=0))[0]
        x = x[:, self.keep]
        self.median = np.nanmedian(x, axis=0)
        self.flag = np.where(np.isnan(x).any(axis=0))[0]
        z = self._raw(x)
        self.mean, self.sd = z.mean(axis=0), z.std(axis=0)
        self.sd[self.sd == 0] = 1.0

    def _raw(self, x: np.ndarray) -> np.ndarray:
        miss = np.isnan(x)
        filled = np.where(miss, self.median, x)
        return np.hstack([filled, miss[:, self.flag].astype(float)])

    def __call__(self, x: np.ndarray) -> np.ndarray:
        return (self._raw(x[:, self.keep]) - self.mean) / self.sd


def ridge_fit(x: np.ndarray, y: np.ndarray, alpha: float) -> tuple[Prep, Ridge]:
    prep = Prep(x)
    return prep, Ridge(alpha=alpha).fit(prep(x), y)


def ridge_predict(train: pl.DataFrame, test: pl.DataFrame) -> np.ndarray:
    """Alpha chosen on the last training season (fit on the earlier ones), refit on all."""
    last = max(train["season"].unique().to_list())
    inner, val = train.filter(pl.col("season") < last), train.filter(pl.col("season") == last)
    x_in, x_val = design(inner, True), design(val, True)
    errors = []
    for alpha in ALPHAS:
        prep, model = ridge_fit(x_in, inner["points"].to_numpy(), alpha)
        pred = np.clip(model.predict(prep(x_val)), 0, None)
        errors.append(np.mean((val["points"].to_numpy() - pred) ** 2))
    alpha = ALPHAS[int(np.argmin(errors))]
    prep, model = ridge_fit(design(train, True), train["points"].to_numpy(), alpha)
    return np.clip(model.predict(prep(design(test, True))), 0, None)


def ridge_by_position(train: pl.DataFrame, test: pl.DataFrame) -> np.ndarray:
    out = np.zeros(test.height)
    for p in POSITIONS:
        mask = (test["position"] == p).to_numpy()
        if mask.any():
            out[mask] = ridge_predict(
                train.filter(pl.col("position") == p), test.filter(pl.col("position") == p)
            )
    return out


def oof_frame() -> pl.DataFrame:
    path = w.SCRATCH / "stack_oof.parquet"
    if path.exists():
        return pl.read_parquet(path)
    seasons = list(range(FIRST_OOF, max(SCORED) + 1))
    learned = w.learned_oof()
    parts = []
    for lid in w.league_ids():
        hist = w.panel(lid)
        ridge = w.walk(hist, ridge_predict, seasons).rename({"pred": "ridge"})
        ridge_pos = w.walk(hist, ridge_by_position, seasons).rename({"pred": "ridge_pos"})
        parts.append(ridge.join(ridge_pos, on=w.KEY))
    frame = (
        learned.filter(pl.col("season") >= FIRST_OOF)
        .join(pl.concat(parts), on=w.KEY)
        .pipe(w.scored_rows, w.calibrated_baseline(FIRST_OOF))
    )
    frame.write_parquet(path)
    return frame


def fit_weights(rows: pl.DataFrame, intercept: bool) -> np.ndarray:
    """Non-negative learner weights (and a free intercept last, if asked) by least squares."""
    x = rows.select(LEARNERS).to_numpy()
    lower = np.zeros(len(LEARNERS))
    upper = np.full(len(LEARNERS), np.inf)
    if intercept:
        x = np.hstack([x, np.ones((len(x), 1))])
        lower, upper = np.append(lower, -np.inf), np.append(upper, np.inf)
    return np.asarray(lsq_linear(x, rows["points"].to_numpy(), bounds=(lower, upper)).x)


def apply(rows: pl.DataFrame, coef: np.ndarray) -> np.ndarray:
    pred = rows.select(LEARNERS).to_numpy() @ coef[: len(LEARNERS)]
    if len(coef) > len(LEARNERS):
        pred = pred + coef[-1]
    return np.clip(pred, 0, None)


def stacked(frame: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Scored rows with one column per stack variant, and the weights fit for each season."""
    variants = {
        "stack_pos": (True, False),
        "stack_pos_int": (True, True),
        "stack_pool": (False, False),
        "stack_pool_int": (False, True),
    }
    out, weights = [], []
    for (lid,), league in frame.group_by("league_id", maintain_order=True):
        for season in SCORED:
            fit_rows = league.filter(pl.col("season") < season)
            test = league.filter(pl.col("season") == season)
            cols = {}
            for name, (by_pos, intercept) in variants.items():
                pred = np.zeros(test.height)
                groups = POSITIONS if by_pos else ("all",)
                for g in groups:
                    f = fit_rows if g == "all" else fit_rows.filter(pl.col("position") == g)
                    mask = np.ones(test.height, bool) if g == "all" else (
                        test["position"] == g
                    ).to_numpy()
                    coef = fit_weights(f, intercept)
                    pred[mask] = apply(test.filter(pl.Series(mask)), coef)
                    weights.append(
                        {"league": w.LEAGUE_NAMES[lid], "season": season, "variant": name}
                        | {"group": g}
                        | {k: round(float(v), 3) for k, v in zip([*LEARNERS, "icpt"], coef)}
                    )
                cols[name] = pred
            out.append(test.with_columns(*[pl.Series(k, v) for k, v in cols.items()]))
    return pl.concat(out), pl.DataFrame(weights)


def main() -> None:
    frame = oof_frame()
    w.league_ids()
    scored, weights = stacked(frame)
    cands = ["ridge", "ridge_pos", "baseline", "stack_pos", "stack_pos_int", "stack_pool"]
    cands += ["stack_pool_int"]
    table = w.report(scored, cands)
    with pl.Config(tbl_rows=400, tbl_cols=20, tbl_width_chars=220):
        print(table.filter(pl.col("slice") == "all"))
        print(table.filter(pl.col("cand").str.starts_with("stack") & (pl.col("slice") != "all")))
        print(weights.filter(pl.col("season") == 2026))
        print(weights.filter(pl.col("season") == 2024))
    table.write_csv(w.SCRATCH / "stack_report.csv")
    weights.write_csv(w.SCRATCH / "stack_weights.csv")


if __name__ == "__main__":
    main()
