"""Idea 7: per-position models, a small settings grid and monotone constraints for the GBM.

Nested time split. Inner: score 2022 and 2023 with models trained on earlier seasons and choose
settings there (lowest squared error over both leagues, compare_to_baseline rows). Outer: score
2024, 2025 and 2026 with the choice fixed, against the current model. Nothing is chosen on 2024 on.

Candidates
(i) per-position models against the pooled model with position dummies (current settings);
(ii) max_leaf_nodes 15/31 x min_samples_leaf 40/80/200 x (learning_rate, max_iter) (0.03, 400) /
    (0.06, 200), pooled (one setting) and per position (a setting per position);
(iii) monotone constraints, pooled, current settings: increasing in lagged points, expected
    points, implied total, snap share and target share; decreasing in depth rank.
The current settings are kept unless the outer gain is at least 0.5% of RMSE with |t| >= 2.

Run from the repo root: OMP_NUM_THREADS=3 uv run python research/settings_check.py
"""

import itertools
import sys
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).parent))
import wf_panel as w  # noqa: E402

from fantasy.stages.learn import (  # noqa: E402
    EXTRA_FEATURES,
    LINE_FEATURES,
    STATE_FEATURES,
    _varies,
    design,
)

INNER = [2022, 2023]
OUTER = [2024, 2025, 2026]
POSITIONS = ("QB", "RB", "WR", "TE")
CURRENT = (15, 80, 0.03, 400)  # max_leaf_nodes, min_samples_leaf, learning_rate, max_iter
GRID = [
    (leaves, leaf, lr, it)
    for leaves, leaf, (lr, it) in itertools.product(
        (15, 31), (40, 80, 200), ((0.03, 400), (0.06, 200))
    )
]
COLUMNS = [*STATE_FEATURES, "week", "is_qb", "is_rb", "is_wr", *LINE_FEATURES, *EXTRA_FEATURES]
INCREASING = ("points_hl", "points_last", "exp_pts_", "snap_", "tshare_", "team_implied")
MIN_GAIN = 0.005


def monotone() -> np.ndarray:
    cst = np.zeros(len(COLUMNS), dtype=int)
    for j, c in enumerate(COLUMNS):
        if c.startswith(INCREASING):
            cst[j] = 1
        elif c == "depth_rank":
            cst[j] = -1
    return cst


def fit(
    train: pl.DataFrame, test: pl.DataFrame, cfg: tuple, mono: bool = False
) -> np.ndarray:
    """`learn.fit_predict` with the settings in `cfg` (identical to it at CURRENT)."""
    x_train, x_test = design(train, True), design(test, True)
    assert x_train.shape[1] == len(COLUMNS)
    usable = [j for j in range(x_train.shape[1]) if _varies(x_train[:, j])]
    leaves, leaf, lr, it = cfg
    model = HistGradientBoostingRegressor(
        loss="squared_error",
        max_iter=it,
        learning_rate=lr,
        max_leaf_nodes=leaves,
        min_samples_leaf=leaf,
        l2_regularization=5.0,
        random_state=0,
        monotonic_cst=monotone()[usable] if mono else None,
    )
    model.fit(x_train[:, usable], train["points"].to_numpy())
    return np.clip(model.predict(x_test[:, usable]), 0.0, None)


def fit_by_position(train: pl.DataFrame, test: pl.DataFrame, cfgs: dict[str, tuple]) -> np.ndarray:
    out = np.zeros(test.height)
    for p in POSITIONS:
        mask = (test["position"] == p).to_numpy()
        if mask.any():
            out[mask] = fit(
                train.filter(pl.col("position") == p), test.filter(pl.col("position") == p), cfgs[p]
            )
    return out


def run_candidates(cands: dict, seasons: list[int], tag: str) -> pl.DataFrame:
    """KEY + one prediction column per candidate, cached per tag."""
    path = w.SCRATCH / f"settings_{tag}.parquet"
    done = pl.read_parquet(path) if path.exists() else None
    todo = {k: f for k, f in cands.items() if done is None or k not in done.columns}
    if todo:
        parts = []
        for lid in w.league_ids():
            hist = w.panel(lid)
            league = None
            for name, f in todo.items():
                print(f"{tag}: {w.LEAGUE_NAMES[lid]} {name}", flush=True)
                pred = w.walk(hist, f, seasons).rename({"pred": name})
                league = pred if league is None else league.join(pred, on=w.KEY)
            parts.append(league)
        new = pl.concat(parts)
        done = new if done is None else done.join(new, on=w.KEY)
        done.write_parquet(path)
    return done


def name(cfg: tuple) -> str:
    return "g_" + "_".join(str(v) for v in cfg)


def mse_by(frame: pl.DataFrame, cols: list[str], by: str | None) -> pl.DataFrame:
    exprs = [((pl.col("points") - pl.col(c)) ** 2).mean().alias(c) for c in cols]
    return frame.group_by(by).agg(exprs) if by else frame.select(exprs)


def main() -> None:
    w.league_ids()
    learned = w.learned_oof()
    base = w.calibrated_baseline(min(INNER))

    # inner: every candidate on 2022 and 2023
    inner_cands = {name(c): (lambda tr, te, c=c: fit(tr, te, c)) for c in GRID}
    inner_cands |= {
        "pos_" + name(c): (lambda tr, te, c=c: fit_by_position(tr, te, dict.fromkeys(POSITIONS, c)))
        for c in GRID
    }
    inner_cands["mono"] = lambda tr, te: fit(tr, te, CURRENT, mono=True)
    inner = run_candidates(inner_cands, INNER, "inner")
    inner = w.scored_rows(
        learned.join(inner, on=w.KEY), base
    )
    current = name(CURRENT)
    check = float((inner[current] - inner["learned"]).abs().max())
    print(f"inner: grid at current settings vs learned, max abs diff {check}")
    pooled_cols = [name(c) for c in GRID]
    pos_cols = ["pos_" + n for n in pooled_cols]
    overall = mse_by(inner, [*pooled_cols, *pos_cols, "mono"], None).transpose(
        include_header=True, header_name="cand", column_names=["mse"]
    )
    overall = overall.with_columns(
        rmse=pl.col("mse").sqrt(),
        gain_pct=100 * (1 - pl.col("mse").sqrt() / np.sqrt(overall.filter(
            pl.col("cand") == current)["mse"][0])),
    ).sort("mse")
    with pl.Config(tbl_rows=60):
        print("inner (2022-2023, both leagues):")
        print(overall)
    best_pool = min(GRID, key=lambda c: overall.filter(pl.col("cand") == name(c))["mse"][0])
    by_pos = mse_by(inner, pos_cols, "position")
    best_pos = {}
    for p in POSITIONS:
        row = by_pos.filter(pl.col("position") == p).drop("position").row(0, named=True)
        best = min(row, key=lambda k: row[k])
        best_pos[p] = GRID[pos_cols.index(best)]
    print(f"chosen pooled setting {best_pool}; per position {best_pos}")
    pooled_by_pos = mse_by(inner, [current, f"pos_{current}"], "position")
    print("inner by position, pooled vs per-position at current settings (MSE):")
    print(pooled_by_pos)

    # outer: the fixed choices on 2024 on
    outer_cands = {
        "pos_current": lambda tr, te: fit_by_position(tr, te, dict.fromkeys(POSITIONS, CURRENT)),
        "pos_chosen": lambda tr, te: fit_by_position(tr, te, best_pos),
        "mono": lambda tr, te: fit(tr, te, CURRENT, mono=True),
    }
    if best_pool != CURRENT:
        outer_cands["pool_chosen"] = lambda tr, te: fit(tr, te, best_pool)
    outer = run_candidates(outer_cands, OUTER, "outer")
    outer = w.scored_rows(learned.join(outer, on=w.KEY), w.calibrated_baseline(min(OUTER)))
    table = w.report(outer, list(outer_cands))
    with pl.Config(tbl_rows=400, tbl_cols=20, tbl_width_chars=220):
        print(table)
    table.write_csv(w.SCRATCH / "settings_report.csv")
    print(f"ship floor: gain >= {100 * MIN_GAIN}% of RMSE in both leagues with t >= 2")


if __name__ == "__main__":
    main()
