"""Three variants of the learned model: determinism and bagging (A), Poisson loss (B) and a shrunk
per-player residual correction (C).

Walk-forward by season as `learn.walk_forward` (one model per season, trained on the seasons
`learn.train_seasons` allows), predictions for 2021 on. Choices (A1's iteration count, C's half-life
and k) are made on 2021 to 2023; the report scores 2024, 2025 and 2026 on the compare_to_baseline
rows against the current model (`learned`). Noise: the current model refit on 3 row orders.

(A1) early_stopping=False with max_iter fixed, chosen on 2021-2023 from staged predictions;
(A2) the mean of 5 random seeds with early stopping on (seed 0 is the current model);
(B) loss="poisson" (targets clipped at 0), A-decision settings;
(C) projection + n_eff / (n_eff + k) * the exponentially weighted mean of the player's earlier
    out-of-sample residuals (2021 on; games strictly before the target, earlier weeks of the same
    season included, each scored by its own season's walk-forward model).

Walk-forward predictions per candidate go to $VARIANTS_PREDS (default research/scratch/preds) as
<name>.parquet: league_id, gsis_id, season, week, projection.

Run from the repo root: OMP_NUM_THREADS=3 uv run python research/variants_check.py a|b|c
"""

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).parent))
import wf_panel as w  # noqa: E402

from fantasy.stages.learn import _varies, design, train_seasons  # noqa: E402

SEASONS = [2021, 2022, 2023, 2024, 2025, 2026]
INNER = [2021, 2022, 2023]
OUTER = [2024, 2025, 2026]
PREDS = Path(os.environ.get("VARIANTS_PREDS", w.SCRATCH / "preds"))
BASE = {
    "loss": "squared_error",
    "max_iter": 400,
    "learning_rate": 0.03,
    "max_leaf_nodes": 15,
    "min_samples_leaf": 80,
    "l2_regularization": 5.0,
    "random_state": 0,
}
STAGES = (100, 120, 140, 160, 180, 200, 250, 300)  # A1 grid of fixed iteration counts
SEEDS = 5
REORDERS = 3
# set after experiment A: the settings B and C build on (None keeps the current model)
A_DECISION: dict | None = {"early_stopping": False, "max_iter": 160}  # A1 shipped
HALF_LIVES = (8.0, 16.0, 32.0, float("inf"))  # games, for C's residual average
KS = (2.0, 5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 320.0)
LOG: list[dict] = []  # per fit: league, season, candidate, n_iter, seconds

Fit = Callable[[pl.DataFrame, pl.DataFrame], dict[str, np.ndarray]]


def fit_model(
    train: pl.DataFrame, test: pl.DataFrame, tag: str, order_seed: int | None = None, **params
) -> HistGradientBoostingRegressor | tuple:
    """`learn.fit_predict` with `params` over BASE; `order_seed` shuffles the training rows."""
    if order_seed is not None:
        perm = np.random.default_rng(order_seed).permutation(train.height)
        train = train[perm]
    x_train, x_test = design(train, True), design(test, True)
    usable = [j for j in range(x_train.shape[1]) if _varies(x_train[:, j])]
    y = train["points"].to_numpy()
    if params.get("loss") == "poisson":
        y = np.clip(y, 0.0, None)
    start = time.time()
    model = HistGradientBoostingRegressor(**(BASE | params))
    model.fit(x_train[:, usable], y)
    LOG.append(
        {
            "season": int(test["season"][0]),
            "tag": tag,
            "n_iter": model.n_iter_,
            "seconds": time.time() - start,
            "n_train": train.height,
        }
    )
    return model, x_test[:, usable]


def single(tag: str, order_seed: int | None = None, **params) -> Fit:
    def fit(train: pl.DataFrame, test: pl.DataFrame) -> dict[str, np.ndarray]:
        model, x = fit_model(train, test, tag, order_seed, **params)
        return {tag: np.clip(model.predict(x), 0.0, None)}

    return fit


def staged(tag: str, order_seed: int | None = None, **params) -> Fit:
    """One fit without early stopping, predictions after each iteration count in STAGES."""

    def fit(train: pl.DataFrame, test: pl.DataFrame) -> dict[str, np.ndarray]:
        model, x = fit_model(
            train, test, tag, order_seed, early_stopping=False, max_iter=max(STAGES), **params
        )
        out = {}
        for i, pred in enumerate(model.staged_predict(x), start=1):
            if i in STAGES:
                out[f"{tag}{i}"] = np.clip(pred, 0.0, None)
        return out

    return fit


def bagged(tag: str, seeds: int, **params) -> Fit:
    """Mean of `seeds` random seeds; also returns seed 0 alone (the current model's seed)."""

    def fit(train: pl.DataFrame, test: pl.DataFrame) -> dict[str, np.ndarray]:
        preds = []
        for seed in range(seeds):
            model, x = fit_model(train, test, f"{tag}_s{seed}", random_state=seed, **params)
            preds.append(np.clip(model.predict(x), 0.0, None))
        return {tag: np.mean(preds, axis=0), f"{tag}_seed0": preds[0]}

    return fit


def walk(history: pl.DataFrame, fit: Fit, lid: str) -> pl.DataFrame:
    available = sorted(history["season"].unique().to_list())
    parts = []
    for season in SEASONS:
        train = history.filter(pl.col("season").is_in(train_seasons(season, available)))
        test = history.filter(pl.col("season") == season)
        n = len(LOG)
        cols = fit(train, test)
        for row in LOG[n:]:
            row["league"] = w.LEAGUE_NAMES[lid]
        parts.append(test.select(w.KEY).with_columns(pl.Series(k, v) for k, v in cols.items()))
    return pl.concat(parts)


def run(group: str, fit: Fit) -> pl.DataFrame:
    """KEY + the group's prediction columns for both leagues, cached in research/scratch."""
    path = w.SCRATCH / f"variants_{group}.parquet"
    if path.exists():
        return pl.read_parquet(path)
    parts = []
    for lid in w.league_ids():
        print(f"{group}: {w.LEAGUE_NAMES[lid]}", flush=True)
        parts.append(walk(w.panel(lid), fit, lid))
    out = pl.concat(parts)
    out.write_parquet(path)
    log = pl.DataFrame(LOG).filter(pl.col("tag").str.starts_with(group))
    if log.height:
        log.write_parquet(w.SCRATCH / f"variants_{group}_log.parquet")
    return out


def write_preds(frame: pl.DataFrame, col: str, name: str) -> None:
    PREDS.mkdir(parents=True, exist_ok=True)
    frame.filter(pl.col("season") >= min(SEASONS)).select(
        *w.KEY, pl.col(col).alias("projection")
    ).write_parquet(PREDS / f"{name}.parquet")


def mse(data: pl.DataFrame, cols: list[str]) -> dict[str, float]:
    return {c: float(((data["points"] - data[c]) ** 2).mean()) for c in cols}  # type: ignore[arg-type]


def summary(data: pl.DataFrame, cands: list[str], ref: str = "learned") -> pl.DataFrame:
    """Per league and candidate: overall row plus season t, the ship-rule view."""
    table = w.report(data, cands, ref)
    overall = table.filter(pl.col("slice") == "all").select(
        "league", "cand", "n", "rmse", "rmse_ref", "gain_pct", "mae", "me", "t", "better"
    )
    seasons = (
        table.filter(pl.col("slice").str.starts_with("s20"))
        .select("league", "cand", "slice", pl.format("{} ({})", "gain_pct", "t").alias("v"))
        .pivot(on="slice", index=["league", "cand"], values="v")
    )
    return overall.join(seasons, on=["league", "cand"])


def show(frame: pl.DataFrame) -> None:
    with pl.Config(tbl_rows=400, tbl_cols=30, tbl_width_chars=250, fmt_str_lengths=40):
        print(frame)


def noise_sd(data: pl.DataFrame, cols: list[str]) -> dict[str, float]:
    """Per league, the sd of RMSE (% of the current model's) across `cols` refits."""
    out = {}
    for (lid,), g in data.group_by("league_id"):
        rmse = np.sqrt(np.array(list(mse(g, cols).values())))
        out[w.LEAGUE_NAMES[lid]] = float(100 * rmse.std(ddof=1) / rmse[0])
    return out


def scored(frame: pl.DataFrame, seasons: list[int]) -> pl.DataFrame:
    learned = w.learned_oof()
    base = w.calibrated_baseline(min(seasons))
    data = learned.join(frame, on=w.KEY).filter(pl.col("season").is_in(seasons))
    return w.scored_rows(data, base)


def experiment_a() -> None:
    w.league_ids()
    learned = w.learned_oof()
    write_preds(learned, "learned", "current")
    reorders = run(
        "reorder",
        lambda tr, te: {
            f"reorder{i}": single(f"reorder{i}", order_seed=i)(tr, te)[f"reorder{i}"]
            for i in range(1, REORDERS + 1)
        },
    )
    a2 = run("a2", bagged("a2", SEEDS))
    a1 = run("a1_", staged("a1_"))
    frame = reorders.join(a2, on=w.KEY).join(a1, on=w.KEY)
    print(f"a2 seed 0 vs learned, max abs diff: {_max_diff(frame, learned, 'a2_seed0')}")

    log = pl.read_parquet(w.SCRATCH / "variants_a2_log.parquet")
    stops = log.filter(pl.col("tag") == "a2_s0").select("league", "season", "n_train", "n_iter")
    print("current model's stopping iteration per season (seed 0):")
    show(stops.pivot(on="season", index="league", values="n_iter"))
    print("a2 stopping iterations, all seeds: ", log.group_by("season").agg(
        pl.col("n_iter").min().alias("min"), pl.col("n_iter").max().alias("max")
    ).sort("season").rows())

    inner = scored(frame, INNER)
    stage_cols = [f"a1_{i}" for i in STAGES]
    inner_mse = mse(inner, ["learned", *stage_cols])
    print("inner 2021-2023 RMSE, both leagues:", {k: round(v**0.5, 4) for k, v in inner_mse.items()})
    chosen = min(stage_cols, key=lambda c: inner_mse[c])
    print(f"A1 chosen on 2021-2023: {chosen}")

    det = run("a1det", staged("a1det", order_seed=1))
    det_diff = _max_diff(det, a1, chosen.replace("a1_", "a1det"), chosen)
    print(f"A1 refit on reordered rows, max abs diff: {det_diff}")

    outer = scored(frame, OUTER)
    refits = ["learned", *[f"reorder{i}" for i in range(1, REORDERS + 1)]]
    print(f"refit noise sd of RMSE, % (current + {REORDERS} reorders): {noise_sd(outer, refits)}")
    show(summary(outer, [*refits[1:], chosen, "a2", "a2_seed0"]))
    show(w.report(outer, [chosen, "a2"]).filter(pl.col("slice").is_in(["QB", "RB", "WR", "TE"])))
    for col, name in ((chosen, f"a1_noes{chosen[3:]}"), ("a2", "a2_bag5")):
        write_preds(frame, col, name)
    print("fit seconds per league (all 6 seasons):")
    show(pl.DataFrame(LOG).group_by("league", "tag").agg(pl.col("seconds").sum()) if LOG else log)


def _max_diff(a: pl.DataFrame, b: pl.DataFrame, col_a: str, col_b: str = "learned") -> float:
    both = a.select(*w.KEY, pl.col(col_a).alias("x")).join(
        b.select(*w.KEY, pl.col(col_b).alias("y")), on=w.KEY
    )
    return float((both["x"] - both["y"]).abs().max())  # type: ignore[arg-type]


def decision_params() -> dict:
    return A_DECISION or {}


def experiment_b() -> None:
    w.league_ids()
    params = decision_params()
    ref = run("bref", single("bref", **params))  # the A-decision model (= learned when unchanged)
    a1 = pl.read_parquet(w.SCRATCH / "variants_a1_.parquet")
    print(f"bref vs A1 staged a1_160, max abs diff: {_max_diff(ref, a1, 'bref', 'a1_160')}")
    pois = run("bpois", single("bpois", loss="poisson", **params))
    neg = {
        w.LEAGUE_NAMES[lid]: int((w.panel(lid)["points"] < 0).sum()) for lid in w.league_ids()
    }
    print(f"negative targets clipped to 0 (whole panel, per league): {neg}")
    log = pl.read_parquet(w.SCRATCH / "variants_bpois_log.parquet")
    print("poisson n_iter per season:", log.select("league", "season", "n_iter").rows())
    frame = ref.join(pois, on=w.KEY)
    outer = scored(frame, OUTER)
    show(summary(outer, ["bpois"], ref="bref"))
    show(w.report(outer, ["bpois"], ref="bref").filter(pl.col("slice").is_in(["QB", "RB", "WR", "TE"])))
    write_preds(frame, "bpois", "b_poisson")


def residual_adjust(frame: pl.DataFrame, pred: str, half_life: float, k: float) -> pl.Series:
    """Per row, n_eff / (n_eff + k) * the exponentially weighted mean (half-life in games) of the
    same player's residuals (points - pred) over games strictly before this one. `frame` holds
    only out-of-sample predictions, sorted by league_id, gsis_id, season, week."""
    decay = 0.5 ** (1.0 / half_life)
    gid = frame["league_id"].cast(pl.String) + "|" + frame["gsis_id"]
    resid = (frame["points"] - frame[pred]).to_numpy()
    ids = gid.to_numpy()
    adj = np.zeros(frame.height)
    s = sw = sw2 = 0.0
    for i in range(frame.height):
        if i == 0 or ids[i] != ids[i - 1]:
            s = sw = sw2 = 0.0
        if sw > 0:
            n_eff = sw * sw / sw2
            adj[i] = n_eff / (n_eff + k) * (s / sw)
        s = decay * s + resid[i]
        sw = decay * sw + 1.0
        sw2 = decay * decay * sw2 + 1.0
    return pl.Series("adj", adj)


def check_no_leak(frame: pl.DataFrame, pred: str) -> None:
    """A row's adjustment must not move when its own or a later game's points change."""
    base = residual_adjust(frame, pred, 16.0, 20.0).to_numpy()
    rng = np.random.default_rng(0)
    for i in rng.choice(frame.height, 20, replace=False):
        bumped = frame.with_columns(
            pl.when(pl.int_range(pl.len()) >= i)
            .then(pl.col("points") + 50.0)
            .otherwise(pl.col("points"))
            .alias("points")
        )
        after = residual_adjust(bumped, pred, 16.0, 20.0).to_numpy()
        assert np.array_equal(base[: i + 1], after[: i + 1]), f"leak at row {i}"
    print("leak check: adjustments unchanged when the target and later points move (20 rows)")


def experiment_c() -> None:
    w.league_ids()
    params = decision_params()
    ref = run("bref", single("bref", **params))
    panels = pl.concat(
        [w.panel(lid).select(*w.KEY, "points") for lid in w.league_ids()]
    )
    frame = (
        ref.join(panels, on=w.KEY)
        .filter(pl.col("season") >= min(SEASONS))  # never residuals of 2019-2020 projections
        .sort("league_id", "gsis_id", "season", "week")
    )
    assert frame.select(w.KEY).is_duplicated().sum() == 0
    check_no_leak(frame, "bref")
    cols = {}
    for h in HALF_LIVES:
        for k in KS:
            name = f"c_h{h:g}_k{k:g}"
            adj = residual_adjust(frame, "bref", h, k).to_numpy()
            cols[name] = pl.Series(name, np.clip(frame["bref"].to_numpy() + adj, 0.0, None))
    frame = frame.with_columns(*cols.values()).drop("points")
    inner = scored(frame, INNER)
    inner_mse = mse(inner, ["bref", *cols])
    best = min(cols, key=lambda c: inner_mse[c])
    ref_rmse = inner_mse["bref"] ** 0.5
    grid = sorted((round(100 * (1 - v**0.5 / ref_rmse), 3), c) for c, v in inner_mse.items())
    print("inner 2021-2023 gain % (both leagues), best 8:", grid[-8:][::-1])
    print(f"C chosen on 2021-2023: {best}")
    outer = scored(frame, OUTER)
    show(summary(outer, [best], ref="bref"))
    show(w.report(outer, [best], ref="bref").filter(pl.col("slice").is_in(["QB", "RB", "WR", "TE"])))
    write_preds(frame, best, "c_resid")


if __name__ == "__main__":
    {"a": experiment_a, "b": experiment_b, "c": experiment_c}[sys.argv[1]]()
