"""Component models (idea 4) and the touchdown part of the hurdle (idea 5): does predicting each
scored stat separately and applying each league's scoring beat the direct points model?

Both leagues score linearly with no yardage or reception bonuses (checked on `scoring_settings`:
no `bonus_*` key has points), so expected points are the scoring rule applied to expected
components. One histogram gradient-boosting model per component, walk-forward by season with the
direct model's settings (`learn.fit_predict`): squared error for receptions and yards, Poisson for
receiving, rushing and passing touchdowns. Interceptions, fumbles lost, two-point conversions and
return touchdowns are left as one small direct residual (league points minus the seven modelled
components, squared error), because the two leagues weight interceptions differently and the term
is small. Training rows are the direct model's: every player-game with a scored row (regular season
and playoffs, as `learn.history_targets` keeps both).

Features: the direct model's matrix (`learn.build_features`, `learn.design`) plus the lagged
component stats themselves (`learn.lag_asof`, shift 0 = one game ahead, half-life 4 games). As a
control the direct model is also refit on that wider matrix, so a gain can be told apart from the
new features.

Candidates, scored on the rows of `learn.compare_to_baseline` (2024 on, has history, size-calibrated
baseline above 3): the current learned model (`proj_learned`), the direct model reproduced from
code (must match it), the direct model with the component lags, the component sum, their 50/50
average, and a non-negative weight on [direct, component] fit on 2021 to the season before
(walk-forward; 2019 and 2020 projections are never used to fit).

Run from the repo root: OMP_NUM_THREADS=3 uv run python research/component_check.py
Predictions are cached in research/scratch/component_preds.parquet (delete it to refit).
"""

import json
import sys
from functools import partial
from pathlib import Path

import numpy as np
import polars as pl
from scipy.optimize import nnls
from sklearn.ensemble import HistGradientBoostingRegressor

from fantasy import store
from fantasy.sim.calibration import apply_curves
from fantasy.stages import backtest
from fantasy.stages.distributions import estimate_curves, residual_frame
from fantasy.stages.learn import (
    FIRST_ACCEPTANCE_SEASON,
    MIN_PROJECTION,
    _varies,
    build_features,
    design,
    games_frame,
    lag_asof,
    load_extras,
    state_frame,
    train_seasons,
)
from fantasy.stages.project import (
    FIRST_PROJECTED_SEASON,
    GROUP,
    build_form,
    expected_frame,
    history_targets,
    position_prior,
    project_targets,
)

KEY = [*GROUP, "season", "week"]
SCRATCH = Path(__file__).parent / "scratch"
CACHE = SCRATCH / "component_preds.parquet"
FIRST_WEIGHT_SEASON = 2021  # learned projections before this saw later seasons
STAT_KEY = ["gsis_id", "season", "week"]

# component -> (nfl_player_stats expression, loss, scoring key)
COMPONENTS: dict[str, tuple[pl.Expr, str]] = {
    "rec": (pl.col("receptions"), "squared_error"),
    "rec_yd": (pl.col("receiving_yards"), "squared_error"),
    "rush_yd": (pl.col("rushing_yards"), "squared_error"),
    "pass_yd": (pl.col("passing_yards"), "squared_error"),
    "rec_td": (pl.col("receiving_tds"), "poisson"),
    "rush_td": (pl.col("rushing_tds"), "poisson"),
    "pass_td": (pl.col("passing_tds"), "poisson"),
}
TD = ("rec_td", "rush_td", "pass_td")
LAG_PREFIX = "cmp"
LAG_FEATURES = [f"{LAG_PREFIX}_{c}" for c in COMPONENTS]
# idea 9: opportunity -> the components measured per opportunity
USAGE: dict[str, tuple[str, ...]] = {
    "targets": ("rec", "rec_yd", "rec_td"),
    "carries": ("rush_yd", "rush_td"),
    "attempts": ("pass_yd", "pass_td"),
}
CACHE9 = SCRATCH / "component9_preds.parquet"


def component_table() -> pl.DataFrame:
    stats = store.read_table("nfl_player_stats", "raw")
    return stats.select(
        pl.col("player_id").alias("gsis_id"),
        "season",
        "week",
        *[expr.cast(pl.Float64).fill_null(0.0).alias(name) for name, (expr, _) in COMPONENTS.items()],
        *[pl.col(u).cast(pl.Float64).fill_null(0.0) for u in USAGE],
    ).unique(STAT_KEY, keep="first", maintain_order=True)


def check_lag_has_no_leak(features: pl.DataFrame, comp: pl.DataFrame) -> None:
    """Self-check for the new lagged join: blowing up every stat of one week must not change that
    week's features (they may only use earlier games)."""
    season, week = 2024, 10
    rows = features.filter((pl.col("season") == season) & (pl.col("week") == week)).select(
        *KEY, "position", "team"
    )
    poisoned = comp.with_columns(
        [
            pl.when((pl.col("season") == season) & (pl.col("week") == week))
            .then(pl.lit(1e6))
            .otherwise(pl.col(c))
            .alias(c)
            for c in COMPONENTS
        ]
    )
    clean = lag_asof(rows, comp, "gsis_id", list(COMPONENTS), LAG_PREFIX, 0).sort(KEY)
    dirty = lag_asof(rows, poisoned, "gsis_id", list(COMPONENTS), LAG_PREFIX, 0).sort(KEY)
    assert clean.select(LAG_FEATURES).equals(dirty.select(LAG_FEATURES)), "component lag leaks"
    later = lag_asof(
        features.filter((pl.col("season") == season) & (pl.col("week") == week + 1)).select(
            *KEY, "position", "team"
        ),
        poisoned,
        "gsis_id",
        list(COMPONENTS),
        LAG_PREFIX,
        0,
    )
    assert later[LAG_FEATURES[0]].max() > 1e3, "self-check is vacuous: the next week must see it"  # type: ignore[operator]


def fit_predict(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_test: np.ndarray,
    loss: str,
    weight: np.ndarray | None = None,
    seed: int = 0,
) -> np.ndarray:
    """learn.fit_predict with a choice of loss and no clipping (components may be negative)."""
    usable = [j for j in range(x_train.shape[1]) if _varies(x_train[:, j])]
    model = HistGradientBoostingRegressor(
        loss=loss,  # type: ignore[arg-type]
        max_iter=400,
        learning_rate=0.03,
        max_leaf_nodes=15,
        min_samples_leaf=80,
        l2_regularization=5.0,
        random_state=seed,
    )
    model.fit(x_train[:, usable], y_train, sample_weight=weight)
    return model.predict(x_test[:, usable])


def walk_forward(
    seasons: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    loss: str,
    weight: np.ndarray | None = None,
    seed: int = 0,
) -> np.ndarray:
    """With `weight`, trains on rows of positive weight only, weighted (rates per opportunity)."""
    out = np.full(len(y), np.nan)
    available = sorted(set(seasons.tolist()))
    for season in available:
        train = np.isin(seasons, train_seasons(season, available))
        test = seasons == season
        if weight is None:
            out[test] = fit_predict(x[train], y[train], x[test], loss, seed=seed)
        else:
            train &= weight > 0
            out[test] = fit_predict(x[train], y[train], x[test], loss, weight[train])
    return out


def league_history(
    lid: str, scoring: dict[str, float], data: dict[str, pl.DataFrame], horizon: int = 1
) -> tuple[pl.DataFrame, np.ndarray, np.ndarray]:
    """The direct model's training rows with component targets, and its matrix with and without
    the component lags (as learn.history_forecasts(horizon): no lines beyond one game ahead)."""
    games = data["games_all"].filter(pl.col("league_id") == lid)
    targets = history_targets(data["exp"].filter(pl.col("league_id") == lid))
    features = build_features(targets, state_frame(games), data["lines"], data["extras"], horizon)
    # the row order of learn.history_forecasts: HGB's automatic early stopping (over 10,000 rows)
    # draws its validation split by position, so the order changes the fit
    history = (
        features.join(games.select(*GROUP, "season", "week", "points"), on=[*GROUP, "season", "week"])
        .with_row_index("_row")
        .join(data["comp"], on=STAT_KEY, how="left")
        .pipe(lag_asof, data["comp"], "gsis_id", list(COMPONENTS), LAG_PREFIX, horizon - 1)
        .sort("_row")
    )
    missing = history.filter(pl.col("rec").is_null()).height
    assert missing == 0, f"{missing} history rows have no stat line"
    check_lag_has_no_leak(features, data["comp"])
    linear = sum(pl.col(c) * scoring.get(c, 0.0) for c in COMPONENTS)
    history = history.with_columns((pl.col("points") - linear).alias("misc"))  # type: ignore[operator]
    x_base = design(history, lines=horizon == 1)
    x_wide = np.hstack([x_base, history.select(LAG_FEATURES).cast(pl.Float64).to_numpy()])
    return history, x_base, x_wide


def league_predictions(
    lid: str, scoring: dict[str, float], data: dict[str, pl.DataFrame], horizon: int = 1
) -> pl.DataFrame:
    history, x_base, x_wide = league_history(lid, scoring, data, horizon)
    seasons = history["season"].to_numpy()
    points = history["points"].to_numpy()
    out = history.select(*KEY, "position", "points", *COMPONENTS, "misc")
    preds = {
        "direct": np.clip(walk_forward(seasons, x_base, points, "squared_error"), 0.0, None),
        "direct_wide": np.clip(walk_forward(seasons, x_wide, points, "squared_error"), 0.0, None),
    }
    for name, (_, loss) in COMPONENTS.items():
        preds[f"p_{name}"] = walk_forward(seasons, x_wide, history[name].to_numpy(), loss)
        print(f"  {lid} {name} done")
    preds["p_misc"] = walk_forward(seasons, x_wide, history["misc"].to_numpy(), "squared_error")
    comp_sum = sum(preds[f"p_{c}"] * scoring.get(c, 0.0) for c in COMPONENTS) + preds["p_misc"]
    preds["component"] = np.clip(comp_sum, 0.0, None)
    return out.with_columns([pl.Series(k, v) for k, v in preds.items()])


def league_usage_first(lid: str, scoring: dict[str, float], data: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Idea 9: predict targets, carries and attempts first, then each component per opportunity
    (weighted by the opportunity) with the predicted usage as features; expected component =
    predicted usage x predicted rate. The residual term (p_misc) comes from the component run."""
    history, _, x_wide = league_history(lid, scoring, data)
    seasons = history["season"].to_numpy()
    usage = {
        u: np.clip(walk_forward(seasons, x_wide, history[u].to_numpy(), "squared_error"), 0.0, None)
        for u in USAGE
    }
    x_eff = np.hstack([x_wide, np.column_stack(list(usage.values()))])
    preds = {f"u_{u}": v for u, v in usage.items()}
    for u, comps in USAGE.items():
        n = history[u].to_numpy()
        for c in comps:
            rate = np.divide(history[c].to_numpy(), n, out=np.zeros(len(n)), where=n > 0)
            pred_rate = walk_forward(seasons, x_eff, rate, COMPONENTS[c][1], weight=n)
            preds[f"q_{c}"] = usage[u] * pred_rate
            print(f"  {lid} usage-first {c} done")
    return history.select(*KEY).with_columns([pl.Series(k, v) for k, v in preds.items()])


def league_reorder_control(lid: str, scoring: dict[str, float], data: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Control for the averages: the direct model refit on shuffled rows (only the early-stopping
    split changes). Averaging it with the direct model shows what any two-model average buys."""
    history, x_base, _ = league_history(lid, scoring, data)
    perm = np.random.default_rng(1).permutation(history.height)
    seasons, points = history["season"].to_numpy(), history["points"].to_numpy()
    shuffled = walk_forward(seasons[perm], x_base[perm], points[perm], "squared_error")
    out = np.empty_like(shuffled)
    out[perm] = shuffled
    return history.select(*KEY).with_columns(pl.Series("direct_shuffled", np.clip(out, 0.0, None)))


def league_seed_null(
    lid: str, scoring: dict[str, float], data: dict[str, pl.DataFrame], horizon: int = 1
) -> pl.DataFrame:
    """Null for the averages: a second direct fit with another random_state (early stopping on,
    so its validation split differs), same rows and order."""
    history, x_base, _ = league_history(lid, scoring, data, horizon)
    seasons, points = history["season"].to_numpy(), history["points"].to_numpy()
    pred = walk_forward(seasons, x_base, points, "squared_error", seed=1)
    return history.select(*KEY).with_columns(pl.Series("direct_seed", np.clip(pred, 0.0, None)))


def fit_all(cache: Path = CACHE, fit: object = league_predictions) -> pl.DataFrame:
    if cache.exists():
        return pl.read_parquet(cache)
    leagues = store.read_table("leagues", "raw")
    opp = store.read_table("nfl_ff_opportunity", "raw")
    exp = expected_frame(opp, store.read_table("player_points"), leagues)
    data = {
        "exp": exp,
        "games_all": games_frame(
            exp, opp, store.read_table("nfl_snaps", "raw"), store.read_table("nfl_player_stats", "raw")
        ),
        "lines": store.read_table("team_games"),
        "extras": load_extras(),  # type: ignore[dict-item]
        "comp": component_table(),
    }
    parts = [
        fit(r["league_id"], json.loads(r["scoring_settings"]), data)  # type: ignore[operator]
        for r in leagues.iter_rows(named=True)
    ]
    SCRATCH.mkdir(exist_ok=True)
    out = pl.concat(parts)
    out.write_parquet(cache)
    return out


def eval_keys() -> pl.DataFrame:
    """The rows of learn.compare_to_baseline: 2024 on, has history, calibrated baseline above 3."""
    baseline = store.read_table("proj_baseline").filter(~pl.col("is_future"))
    history = residual_frame(baseline, store.read_table("player_points"))
    parts = []
    for (league_id,), league_base in baseline.group_by("league_id"):
        for season in sorted(s for s in league_base["season"].unique() if s >= FIRST_ACCEPTANCE_SEASON):
            curves = estimate_curves(
                history.filter((pl.col("league_id") == league_id) & (pl.col("season") < season))
            )
            base = apply_curves(league_base.filter(pl.col("season") == season), curves)
            parts.append(
                base.filter(pl.col("has_history") & (pl.col("projection") > MIN_PROJECTION)).select(KEY)
            )
    return pl.concat(parts)


def with_weights(preds: pl.DataFrame, by: list[str], name: str) -> pl.DataFrame:
    """Non-negative weights on [direct, component] per `by` group, fit on 2021 to the season before."""
    parts = []
    for keys, group in preds.group_by(by):
        for season in sorted(s for s in group["season"].unique() if s >= FIRST_ACCEPTANCE_SEASON):
            fit = group.filter(pl.col("season").is_between(FIRST_WEIGHT_SEASON, season - 1))
            w, _ = nnls(fit.select("direct", "component").to_numpy(), fit["points"].to_numpy())
            print(f"  {name} {keys} {season}: direct {w[0]:.3f}, component {w[1]:.3f}")
            parts.append(
                group.filter(pl.col("season") == season).with_columns(
                    (w[0] * pl.col("direct") + w[1] * pl.col("component")).alias(name)
                )
            )
    return pl.concat(parts)


def with_usage_first(preds: pl.DataFrame, leagues: pl.DataFrame) -> pl.DataFrame:
    q = fit_all(CACHE9, league_usage_first)
    parts = []
    for r in leagues.iter_rows(named=True):
        scoring = json.loads(r["scoring_settings"])
        total = sum(pl.col(f"q_{c}") * scoring.get(c, 0.0) for c in COMPONENTS) + pl.col("p_misc")
        parts.append(
            preds.filter(pl.col("league_id") == r["league_id"])
            .join(q, on=KEY, how="left")
            .with_columns(total.clip(lower_bound=0.0).alias("usage_first"))  # type: ignore[union-attr]
        )
    return pl.concat(parts).with_columns(((pl.col("direct") + pl.col("usage_first")) / 2).alias("avg9"))


def summary(data: pl.DataFrame, cand: str, by: list[str]) -> pl.DataFrame:
    err = pl.col(cand) - pl.col("points")
    return data.group_by(by).agg(
        pl.len().alias("n"),
        (err**2).mean().sqrt().round(4).alias("rmse"),
        err.abs().mean().round(4).alias("mae"),
        err.mean().round(3).alias("mean_err"),
    )


def paired(data: pl.DataFrame, cand: str, ref: str = "learned") -> dict[str, object]:
    """Paired per-week t on mean squared-error differences (positive: `cand` better than `ref`)."""
    by_week = data.group_by("season", "week").agg(
        ((pl.col(ref) - pl.col("points")) ** 2).mean().alias("a"),
        ((pl.col(cand) - pl.col("points")) ** 2).mean().alias("b"),
    )
    diff = (by_week["a"] - by_week["b"]).to_numpy()
    t = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff))))
    return {"t": round(t, 2), "weeks_better": f"{int((diff > 0).sum())}/{len(diff)}"}


def td_calibration(data: pl.DataFrame, scoring: dict[str, float]) -> None:
    """Touchdown points (receiving, rushing, passing): Poisson component expectation against the
    direct model's implied touchdown content (direct minus the component non-touchdown points)."""
    td_w = {c: scoring[c] for c in TD}
    actual = sum(pl.col(c) * w for c, w in td_w.items())
    pois = sum(pl.col(f"p_{c}") * w for c, w in td_w.items())
    non_td = sum(pl.col(f"p_{c}") * scoring.get(c, 0.0) for c in COMPONENTS if c not in TD)
    frame = data.with_columns(
        actual.alias("td_actual"),  # type: ignore[union-attr]
        pois.alias("td_poisson"),  # type: ignore[union-attr]
        (pl.col("learned") - non_td - pl.col("p_misc")).alias("td_implied"),  # type: ignore[operator]
    )
    for col in ("td_poisson", "td_implied"):
        err = frame[col] - frame["td_actual"]
        print(f"  {col}: rmse {np.sqrt((err**2).mean()):.4f} mean err {err.mean():+.3f}")
        dec = (
            frame.with_columns(pl.col(col).qcut(10, labels=[str(i) for i in range(1, 11)]).alias("d"))
            .group_by("d")
            .agg(pl.col(col).mean().round(2).alias("pred"), pl.col("td_actual").mean().round(2).alias("act"))
            .sort("pred")
        )
        print("   decile pred/actual: " + "  ".join(f"{p}/{a}" for p, a in zip(dec["pred"], dec["act"], strict=True)))


def with_avgs(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns(
        ((pl.col("direct") + pl.col("component")) / 2).alias("avg"),
        ((pl.col("direct") + pl.col("direct_wide")) / 2).alias("avg_wide"),
        ((pl.col("direct") + pl.col("direct_seed")) / 2).alias("avg_seed"),
    )


def rmse(frame: pl.DataFrame, col: str) -> float:
    return float(np.sqrt(((frame[col] - frame["points"]) ** 2).mean()))  # type: ignore[operator]


def null_table(data: pl.DataFrame, pairs: list[tuple[str, str]], by_season: bool = True) -> None:
    """Pooled and per-season RMSE and paired weekly t of each (candidate, reference) pair."""
    groups = [("all", data)] + (
        [(str(s), data.filter(pl.col("season") == s)) for s in sorted(data["season"].unique())]
        if by_season
        else []
    )
    for cand, ref in pairs:
        cells = []
        for label, g in groups:
            p = paired(g, cand, ref)
            cells.append(f"{label}: {rmse(g, cand):.4f} vs {rmse(g, ref):.4f} t {p['t']} ({p['weeks_better']})")
        print(f"  {cand} vs {ref}: " + " | ".join(cells))


def horizon5_rows(h5: pl.DataFrame) -> pl.DataFrame:
    """The backtest's rows at horizon 5 (baseline with history and a trailing mean) with the
    walk-forward forecasts made five games ahead."""
    leagues = store.read_table("leagues", "raw")
    exp = expected_frame(
        store.read_table("nfl_ff_opportunity", "raw"), store.read_table("player_points"), leagues
    )
    prior = position_prior(exp)
    form = build_form(exp, prior)
    targets = exp.filter(pl.col("season") >= FIRST_PROJECTED_SEASON).select(
        *KEY, "position", "team", "points"
    )
    scored = project_targets(targets, form, prior, store.read_table("team_games"), 5).filter(
        pl.col("has_history") & pl.col("ewma_actual").is_not_null()
    )
    cols = ["direct", "avg", "avg_wide", "avg_seed"]
    return scored.join(with_avgs(h5).select(*KEY, *cols), on=KEY)


def nulls_report() -> None:
    """Review follow-up: the 50/50 average against two nulls (direct + direct_wide, direct + a
    second direct fit with another random_state), per season, at horizon 5, and QB alone."""
    h1 = with_avgs(fit_all().join(fit_all(SCRATCH / "component_seed_h1.parquet", league_seed_null), on=KEY))
    h5 = fit_all(SCRATCH / "component_preds_h5.parquet", partial(league_predictions, horizon=5)).join(
        fit_all(SCRATCH / "component_seed_h5.parquet", partial(league_seed_null, horizon=5)), on=KEY
    )
    data = h1.join(eval_keys(), on=KEY, how="semi")
    rows5 = horizon5_rows(h5)
    backtest.FORECASTERS = {c: c for c in ("direct", "avg", "avg_wide", "avg_seed")}
    m5 = backtest.metrics(rows5, 5).filter(pl.col("tier") == backtest.ALL_TIERS)
    for (lid,), d in data.group_by("league_id"):
        print(f"\n=== {lid}: (a) horizon 1, compare_to_baseline rows ({d.height}) ===")
        null_table(d, [("avg", "direct"), ("avg", "avg_wide"), ("avg", "avg_seed"), ("avg_wide", "direct"), ("avg_seed", "direct")])
        print(" (c) QB only")
        null_table(d.filter(pl.col("position") == "QB"), [("avg", "direct")])
        test5 = rows5.filter((pl.col("league_id") == lid) & (pl.col("season") >= FIRST_ACCEPTANCE_SEASON))
        print(f" (b) horizon 5, backtest rows 2024 on ({test5.height})")
        null_table(test5, [("avg", "direct"), ("avg", "avg_wide"), ("avg", "avg_seed")], by_season=False)
        weighted = (
            m5.filter(pl.col("league_id") == lid)
            .group_by("forecaster")
            .agg(
                ((pl.col("pinball") * pl.col("n")).sum() / pl.col("n").sum()).round(4).alias("pinball"),
                ((pl.col("rmse") * pl.col("n")).sum() / pl.col("n").sum()).round(4).alias("rmse_pos_weighted"),
            )
            .sort("forecaster")
        )
        print(weighted)
    print("\n(b) both leagues, backtest.verdict at horizon 5:")
    print(backtest.verdict(backtest.metrics(rows5, 5)))


def main() -> None:
    if sys.argv[1:] == ["nulls"]:
        nulls_report()
        return
    preds = fit_all()
    learned = store.read_table("proj_learned").filter(~pl.col("is_future")).select(
        *KEY, pl.col("projection").alias("learned")
    )
    check = preds.join(learned, on=KEY, how="inner")
    print(
        f"reproduction: {check.height} of {preds.height} rows matched, max |direct - proj_learned| "
        f"{(check['direct'] - check['learned']).abs().max():.2e}"
    )
    leagues = store.read_table("leagues", "raw")
    by_position = with_weights(preds, ["league_id", "position"], "nnls_pos").select(*KEY, "nnls_pos")
    weighted = with_weights(preds, ["league_id"], "nnls").join(by_position, on=KEY)
    control = fit_all(SCRATCH / "component_control_preds.parquet", league_reorder_control)
    scored = (
        with_usage_first(weighted, leagues)
        .join(control, on=KEY)
        .with_columns(
            ((pl.col("direct") + pl.col("component")) / 2).alias("avg"),
            ((pl.col("direct") + pl.col("direct_shuffled")) / 2).alias("avg_control"),
        )
        .join(eval_keys(), on=KEY, how="semi")
        .join(learned, on=KEY, how="inner")
    )
    cands = ["learned", "direct_wide", "component", "avg", "nnls", "nnls_pos", "usage_first", "avg9"]
    cands += ["direct_shuffled", "avg_control"]
    pl.Config.set_tbl_rows(200)
    pl.Config.set_tbl_width_chars(200)
    for r in leagues.iter_rows(named=True):
        lid, name = r["league_id"], r["name"]
        data = scored.filter(pl.col("league_id") == lid)
        print(f"\n=== {name} ({data.height} rows) ===")
        rows = []
        for c in cands:
            s = summary(data.with_columns(pl.lit(1).alias("all")), c, ["all"]).row(0, named=True)
            base = summary(data.with_columns(pl.lit(1).alias("all")), "learned", ["all"])["rmse"][0]
            rows.append({"cand": c, **s, "gain_pct": round(100 * (base - s["rmse"]) / base, 2), **paired(data, c)})
        print(pl.DataFrame(rows).drop("all"))
        for c in ("avg", "avg9"):
            print(f" {c} against avg_control: {paired(data, c, 'avg_control')}")
        for by in (["season"], ["position"]):
            parts = [summary(data, c, by).select(*by, pl.col("rmse").alias(c)) for c in cands]
            table = parts[0]
            for p in parts[1:]:
                table = table.join(p, on=by)
            print(table.sort(by))
        print(" touchdown points, all eval rows:")
        td_calibration(data, json.loads(r["scoring_settings"]))


if __name__ == "__main__":
    main()
