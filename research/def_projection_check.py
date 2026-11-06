"""Where is the DEF projection weakest, and do per-component or opponent features fix it?

The production DEF projection (`streaming_model`, DEF_FEATURES = form and the opponent's implied
total, ridge refit before every week) beat the old method by 2.1% and 2.8% (decisions.md,
2026-10-27). This script, on the corrected scoring (`streaming.defense_play_facts`, 2026-11-06):

  diagnose    held-out error of the production model by scoring component (each component is
              the DEF points under only that component's scoring keys, so they sum to the total)
              and by situation (opponent implied total, spread, home, opponent QB change, roof,
              wind, week of season); per component the held-out R^2 of its own model and the
              split-half reliability of team-season means (is there team signal?)
  candidates  the arms registered in decisions.md before this mode was run, against `current`
  distributions  spread arms (CRPS, 80% coverage) on the current mean
  target      the production model fit on the pre-fix scoring against the corrected scoring

Walk-forward: every week from 2024 on is predicted by a fit on earlier weeks from 2019 on.
Paired t: per league, the per-week mean of the squared-error difference, over weeks.

Run from the repo root: uv run python research/def_projection_check.py <mode>
"""

import json
import sys
from collections.abc import Callable

import numpy as np
import polars as pl

from fantasy import store
from fantasy.stages import streaming
from fantasy.stages import streaming_model as sm

FIT_FROM = 2019
SCORE_FROM = 2024
KEY = ["unit", "season", "week"]
COMPONENT_KEYS = {
    "points_allowed": lambda k: k.startswith("pts_allow"),
    "yards_allowed": lambda k: k.startswith("yds_allow"),
    "sacks": lambda k: k == "sack",
    "interceptions": lambda k: k == "int",
    "fumble_recoveries": lambda k: k in ("fum_rec", "def_st_fum_rec"),
    "forced_fumbles": lambda k: k in ("ff", "def_st_ff"),
    "touchdowns": lambda k: k in ("def_td", "def_st_td"),
    "safeties_blocks_2pt": lambda k: k in ("safe", "blk_kick", "def_2pt"),
}


# ---------- data ----------


def qb_starters() -> pl.DataFrame:
    """Per (team, season, week): the QB with the most pass attempts, and whether he differs from
    the team's starter in its previous game of the season."""
    ps = store.read_table("nfl_player_stats", "raw").filter(
        (pl.col("position") == "QB") & (pl.col("season_type") == "REG")
    )
    top = (
        ps.sort("attempts", descending=True)
        .group_by("team", "season", "week")
        .agg(pl.col("player_id").first().alias("qb"))
        .sort("team", "season", "week")
        .with_columns(prev_qb=pl.col("qb").shift(1).over("team", "season"))
    )
    return top.with_columns(
        qb_change=pl.when(pl.col("prev_qb").is_null())
        .then(None)
        .otherwise((pl.col("qb") != pl.col("prev_qb")).cast(pl.Float64))
    )


def qb_out(starters: pl.DataFrame) -> pl.DataFrame:
    """Per (team, season, week): 1 if the team's starter in its previous game of the season is
    Out or Doubtful on this week's final injury report (known before kickoff), else 0."""
    report = (
        store.read_table("nfl_injuries", "raw")
        .filter(pl.col("report_status").is_in(["Out", "Doubtful"]))
        .select(pl.col("gsis_id").alias("prev_qb"), "season", "week", out=pl.lit(1.0))
        .unique()
    )
    return (
        starters.filter(pl.col("prev_qb").is_not_null())
        .join(report, on=["prev_qb", "season", "week"], how="left")
        .select("team", "season", "week", qb_out=pl.col("out").fill_null(0.0))
    )


def game_context(stats, games, facts) -> pl.DataFrame:
    """Per DEF team-game: offensive points allowed (as the tiers see them) and net yards allowed."""
    st = (
        stats.filter(pl.col("season_type") == "REG")
        .join(facts, on=["team", "season", "week"], how="left")
        .with_columns(pl.col(f).fill_null(0.0) for f in streaming.DEFENSE_FACTS)
    )
    opp = st.select(
        pl.col("team").alias("opponent_team"), "season", "week",
        net_yards=pl.col("passing_yards") + pl.col("rushing_yards") + pl.col("sack_yards"),
        opp_def_tds=pl.col("def_tds") + pl.col("fumble_return_tds"),
    )
    pa = games.with_columns(pl.col("team").replace(streaming.SCHEDULE_TEAM_CODES)).select(
        "team", "season", "week", "points_against"
    )
    return (
        st.select("team", "season", "week", "opponent_team")
        .join(opp, on=["opponent_team", "season", "week"])
        .join(pa, on=["team", "season", "week"])
        .select("team", "season", "week", "net_yards",
                allowed=pl.col("points_against") - 6 * pl.col("opp_def_tds"))
    )


def with_opponent(rows: pl.DataFrame, teams: pl.DataFrame) -> pl.DataFrame:
    """Adds the opponent's trailing team features (`o_*_tr`)."""
    keyed = rows.rename({"unit": "team", "opponent": "opponent_team"})
    out = sm.add_team_features(keyed.drop("spread", "is_home"), teams)
    return out.rename({"team": "unit", "opponent_team": "opponent"}).with_columns(
        pl.col("is_home").cast(pl.Float64)
    )


def league_rows(lg: dict, stats, games, facts, starters, extra: pl.DataFrame) -> pl.DataFrame:
    """One row per played DEF team-game from 2018: points, components, form and situation."""
    scoring = json.loads(lg["scoring_settings"])
    total = streaming.defense_points_frame(stats, games, scoring, lg["league_id"], facts)
    rows = total.select("team", "season", "week", "points", "opp_implied", "team_implied", "roof")
    for name, pick in COMPONENT_KEYS.items():
        part = {k: v for k, v in scoring.items() if pick(k)}
        comp = streaming.defense_points_frame(stats, games, part, lg["league_id"], facts)
        rows = rows.join(comp.select("team", "season", "week", pl.col("points").alias(name)),
                         on=["team", "season", "week"])
    gap = (rows["points"] - rows.select(sum(pl.col(c) for c in COMPONENT_KEYS)).to_series()).abs()
    assert gap.max() < 1e-9, "components do not sum to the total"
    coded = games.with_columns(
        pl.col("team").replace(streaming.SCHEDULE_TEAM_CODES),
        pl.col("opponent").replace(streaming.SCHEDULE_TEAM_CODES),
    ).select("team", "season", "week", "opponent", "spread", "is_home", "temp", "wind", "total_line")
    opp_qb = starters.select(
        pl.col("team").alias("opponent"), "season", "week", opp_qb_change="qb_change"
    ).join(
        qb_out(starters).rename({"team": "opponent", "qb_out": "opp_qb_out"}),
        on=["opponent", "season", "week"], how="left",
    )
    rows = (
        rows.filter(pl.col("season") >= streaming.SCORED_FROM)
        .join(coded, on=["team", "season", "week"], how="left")
        .join(opp_qb, on=["opponent", "season", "week"], how="left")
        .join(extra, on=["team", "season", "week"], how="left")
        .rename({"team": "unit", "opp_implied": "implied"})
    )
    formed, _ = sm.with_form(rows, rows.head(0).select(KEY))
    return sm.trailing(formed, "unit", list(COMPONENT_KEYS))


def load_leagues() -> dict[str, pl.DataFrame]:
    stats = store.read_table("nfl_team_stats", "raw")
    games = store.read_table("team_games")
    last = int(stats["season"].max())
    facts = streaming.load_play_facts(range(streaming.SCORED_FROM, last + 1))
    starters = qb_starters()
    extra = game_context(stats, games, facts)
    coded = games.with_columns(
        pl.col("team").replace(streaming.SCHEDULE_TEAM_CODES),
        pl.col("opponent").replace(streaming.SCHEDULE_TEAM_CODES),
    )
    teams = sm.team_trailing(
        stats,
        store.read_table("nfl_team_efficiency", "raw"),
        store.read_table("nfl_team_pace", "raw"),
        coded,
    )
    leagues = store.read_table("leagues", "raw")
    return {
        lg["league_key"]: with_opponent(
            league_rows(lg, stats, games, facts, starters, extra), teams
        ).with_columns(pl.lit(lg["scoring_settings"]).alias("scoring"))
        for lg in leagues.iter_rows(named=True)
    }


# ---------- walk-forward ----------

Predictor = Callable[[pl.DataFrame, pl.DataFrame], np.ndarray]


def ridge_on(features: list[str], target: str = "points") -> Predictor:
    """Ridge as `streaming_model.project` fits it, on any target column."""

    def predict(fit: pl.DataFrame, new: pl.DataFrame) -> np.ndarray:
        fit = fit.with_columns(pl.col(c).fill_nan(None) for c in features).drop_nulls(
            [*features, target]
        )
        fills = {f: float(fit[f].mean()) for f in features}
        x_new = new.select(pl.col(f).fill_nan(None).fill_null(fills[f]) for f in features)
        return sm.ridge_predict(
            fit.select(features).to_numpy(), fit[target].to_numpy(), x_new.to_numpy()
        )

    return predict


def walk_forward(rows: pl.DataFrame, predictor: Predictor) -> np.ndarray:
    """Predictions for every row from SCORE_FROM on (in `scored(rows)` order)."""
    test = scored(rows)
    out = np.full(test.height, np.nan)
    weeks = test.select("season", "week").unique().sort("season", "week")
    for season, week in weeks.iter_rows():
        before = (pl.col("season") < season) | (
            (pl.col("season") == season) & (pl.col("week") < week)
        )
        fit = rows.filter(before & (pl.col("season") >= FIT_FROM))
        here = ((test["season"] == season) & (test["week"] == week)).to_numpy()
        out[here] = predictor(fit, test.filter(pl.Series(here)))
    return out


def scored(rows: pl.DataFrame) -> pl.DataFrame:
    return rows.filter(pl.col("season") >= SCORE_FROM).sort("season", "week", "unit")


def league_mean(rows: pl.DataFrame, target: str = "points") -> Predictor:
    def predict(fit: pl.DataFrame, new: pl.DataFrame) -> np.ndarray:
        return np.full(new.height, float(fit[target].mean()))

    return predict


def rmse(err: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(err))))


def weekly_t(test: pl.DataFrame, err_a: np.ndarray, err_b: np.ndarray) -> float:
    """Paired t over weeks of the mean squared-error difference (a minus b)."""
    d = test.select("season", "week").with_columns(d=pl.Series(err_a**2 - err_b**2))
    per = d.group_by("season", "week").agg(pl.col("d").mean())["d"].to_numpy()
    return float(per.mean() / (per.std(ddof=1) / np.sqrt(per.size)))


def calibration_slope(actual: np.ndarray, pred: np.ndarray) -> float:
    """Slope of actual on prediction: 1 is calibrated, under 1 over-dispersed predictions."""
    p = pred - pred.mean()
    return float((p * (actual - actual.mean())).sum() / (p * p).sum())


# ---------- diagnose ----------


def split_half(rows: pl.DataFrame, col: str) -> float:
    """Spearman-Brown reliability of a team-season mean from odd vs even weeks, 2019 to 2025."""
    halves = (
        rows.filter(pl.col("season").is_between(FIT_FROM, 2025))
        .group_by("unit", "season", (pl.col("week") % 2).alias("half"))
        .agg(pl.col(col).mean())
        .pivot("half", index=["unit", "season"], values=col)
        .drop_nulls()
    )
    r = float(np.corrcoef(halves["0"].to_numpy(), halves["1"].to_numpy())[0, 1])
    return 2 * r / (1 + r)


def diagnose(name: str, rows: pl.DataFrame) -> None:
    test = scored(rows)
    actual = test["points"].to_numpy()
    model = walk_forward(rows, ridge_on(sm.DEF_FEATURES))
    mean = walk_forward(rows, league_mean(rows))
    e, e0 = actual - model, actual - mean
    print(f"\n=== {name}: {test.height} games, model RMSE {rmse(e):.3f}, league mean {rmse(e0):.3f}"
          f" ({100 * (rmse(e) / rmse(e0) - 1):+.2f}%), bias {e.mean():+.3f}, "
          f"calibration slope {calibration_slope(actual, model):.2f}")
    print(f"{'component':22} {'mean':>6} {'sd':>6} {'MSE share':>9} {'own R2':>7} {'split-half':>10}")
    for c in COMPONENT_KEYS:
        if test[c].abs().sum() == 0:
            continue
        ek = test[c].to_numpy() - walk_forward(rows, ridge_on(sm.DEF_FEATURES, c))
        own = test[c].to_numpy() - walk_forward(rows, ridge_on([f"{c}_tr", "implied"], c))
        base = test[c].to_numpy() - walk_forward(rows, league_mean(rows, c))
        r2 = 1 - np.mean(own**2) / np.mean(base**2)
        print(f"{c:22} {test[c].mean():6.2f} {test[c].std():6.2f} {np.mean(ek * e) / np.mean(e * e):9.1%}"
              f" {r2:7.3f} {split_half(rows, c):10.2f}")
    situations = test.with_columns(
        err=pl.Series(e), err0=pl.Series(e0), pred=pl.Series(model),
        implied_bin=pl.col("implied").cut([18, 21, 24, 27]),
        fav=pl.when(pl.col("spread").is_null()).then(None)
        .otherwise(pl.col("team_implied") - pl.col("implied")).cut([-7, -3, 0, 3, 7]),
        home=pl.col("is_home"),
        opp_qb_change=pl.col("opp_qb_change"),
        roof_kind=pl.col("roof").is_in(streaming.DOMES).replace_strict({True: "dome", False: "open"}),
        wind_bin=pl.col("wind").cut([10, 15]),
        week_bin=pl.col("week").cut([4, 9, 14]),
        pred_bin=pl.Series(model).cut([5, 6.5, 8, 10]),
    )
    for by in ("implied_bin", "fav", "home", "opp_qb_change", "roof_kind", "wind_bin", "week_bin", "pred_bin"):
        table = (
            situations.group_by(by)
            .agg(
                n=pl.len(),
                actual=pl.col("points").mean(),
                bias=pl.col("err").mean(),
                rmse=(pl.col("err") ** 2).mean().sqrt(),
                rmse_mean=(pl.col("err0") ** 2).mean().sqrt(),
            )
            .sort(by)
        )
        print(f"-- by {by}")
        for r in table.iter_rows(named=True):
            print(f"   {str(r[by]):14} n {r['n']:4}  actual {r['actual']:5.2f}  bias {r['bias']:+5.2f}"
                  f"  rmse {r['rmse']:5.2f}  (mean {r['rmse_mean']:5.2f})")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "diagnose"
    data = load_leagues()
    if mode == "diagnose":
        for name, rows in data.items():
            diagnose(name, rows)
    elif mode == "candidates":
        candidates(data)
    elif mode == "distributions":
        distributions(data)
    elif mode == "target":
        target(data)
    else:
        raise SystemExit(f"unknown mode {mode!r}")


# ---------- candidates (registered in decisions.md, 2026-11-06, before this was run) ----------


def tier_np(values: np.ndarray, terms: list[tuple[int, int, float]]) -> np.ndarray:
    """`streaming.tier_expr` on a numpy array of whole numbers."""
    out = np.zeros(values.shape)
    for low, high, weight in terms:
        out = np.where((values >= low) & (values <= high), weight, out)
    return out


def expected_tier(centres: np.ndarray, residuals: np.ndarray, terms) -> np.ndarray:
    """Mean tier points of `centre + residual` over every fit residual, rounded to whole numbers
    (the tiers are integer ranges)."""
    return tier_np(np.rint(centres[:, None] + residuals[None, :]), terms).mean(axis=1)


def add_tiers(fit: pl.DataFrame, new: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Both frames with `exp_pa` and `exp_ya`: expected tier points at the implied total, over the
    fit rows' residuals (allowed minus implied; net yards around a line on the implied total)."""
    scoring = json.loads(fit["scoring"][0])
    pa_terms = streaming.tier_terms(scoring, "pts_allow")
    ya_terms = streaming.tier_terms(scoring, "yds_allow")
    ok = fit.drop_nulls(["allowed", "net_yards", "implied"])
    implied = ok["implied"].to_numpy()
    pa_resid = ok["allowed"].to_numpy() - implied
    slope, intercept = np.polyfit(implied, ok["net_yards"].to_numpy(), 1)
    ya_resid = ok["net_yards"].to_numpy() - (intercept + slope * implied)

    def add(frame: pl.DataFrame) -> pl.DataFrame:
        x = frame["implied"].fill_null(float(implied.mean())).to_numpy()
        return frame.with_columns(
            exp_pa=pl.Series(expected_tier(x, pa_resid, pa_terms)),
            exp_ya=pl.Series(expected_tier(intercept + slope * x, ya_resid, ya_terms)),
        )

    return add(fit), add(new)


def tiered(inner: Predictor) -> Predictor:
    return lambda fit, new: inner(*add_tiers(fit, new))


def summed(parts: list[Predictor]) -> Predictor:
    return lambda fit, new: np.sum([p(fit, new) for p in parts], axis=0)


def drift(features: list[str], weeks: int = 17) -> Predictor:
    """Ridge plus its mean in-sample residual over the fit's last `weeks` weeks."""
    base = ridge_on(features)

    def predict(fit: pl.DataFrame, new: pl.DataFrame) -> np.ndarray:
        last = fit.select("season", "week").unique().sort("season", "week").tail(weeks)
        recent = fit.join(last, on=["season", "week"]).drop_nulls([*features, "points"])
        shift = float((recent["points"].to_numpy() - base(fit, recent)).mean())
        return base(fit, new) + shift

    return predict


def component_arm() -> Predictor:
    rest = ["fumble_recoveries", "forced_fumbles", "touchdowns", "safeties_blocks_2pt"]
    opp_pass = ["o_attempts_tr", "implied"]
    return tiered(summed([
        ridge_on(["exp_pa", "points_allowed_tr"], "points_allowed"),
        ridge_on(["exp_ya", "yards_allowed_tr"], "yards_allowed"),
        ridge_on(["sacks_tr", "o_sacks_suffered_tr", *opp_pass], "sacks"),
        ridge_on(["interceptions_tr", "o_passing_interceptions_tr", *opp_pass], "interceptions"),
        *[ridge_on(["implied"], c) for c in rest],
    ]))


SIGNAL_FORM = ["implied", "sacks_tr", "interceptions_tr", "points_allowed_tr", "yards_allowed_tr"]
ARMS: dict[str, Predictor] = {
    "current": ridge_on(sm.DEF_FEATURES),
    "tier": tiered(ridge_on([*sm.DEF_FEATURES, "exp_pa", "exp_ya"])),
    "qb_out": ridge_on([*sm.DEF_FEATURES, "opp_qb_out"]),
    "signal_form": ridge_on(SIGNAL_FORM),
    "components": component_arm(),
    "drift": drift(sm.DEF_FEATURES),
}
MARGIN, T_MAX, CAL_SLACK = 0.995, -2.0, 0.05


def score_arm(test: pl.DataFrame, pred: np.ndarray) -> dict:
    actual = test["points"].to_numpy()
    e = actual - pred
    return {"rmse": rmse(e), "bias": float(e.mean()), "slope": calibration_slope(actual, pred),
            "err": e, "pred": pred}


def passes(arm: dict, cur: dict) -> bool:
    return (
        arm["rmse"] <= MARGIN * cur["rmse"]
        and arm["t"] <= T_MAX
        and abs(arm["bias"]) <= abs(cur["bias"]) + CAL_SLACK
        and abs(arm["slope"] - 1) <= abs(cur["slope"] - 1) + CAL_SLACK
    )


def run_arms(data: dict[str, pl.DataFrame], arms: dict[str, Predictor]) -> dict:
    results: dict[str, dict[str, dict]] = {}
    for league, rows in data.items():
        test = scored(rows)
        res = {a: score_arm(test, walk_forward(rows, p)) for a, p in arms.items()}
        cur = res["current"]
        print(f"\n=== {league}")
        for a, r in res.items():
            r["t"] = weekly_t(test, r["err"], cur["err"]) if a != "current" else 0.0
            r["pass"] = a != "current" and passes(r, cur)
            print(f"  {a:14} rmse {r['rmse']:.3f} ({100 * (r['rmse'] / cur['rmse'] - 1):+.2f}%)"
                  f"  t {r['t']:+.2f}  bias {r['bias']:+.3f}  slope {r['slope']:.3f}"
                  f"  {'PASS' if r['pass'] else ''}")
        results[league] = res
    return results


Z80 = 1.2815515655446004  # normal quantile of 0.9


def crps_normal(y: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    from scipy.stats import norm

    z = (y - mu) / sd
    return sd * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi))


def crps_sample(y: np.ndarray, mu: np.ndarray, resid: np.ndarray) -> np.ndarray:
    """CRPS of `mu + resid` (an empirical distribution) at each `y`."""
    r = np.sort(resid)
    m = r.size
    spread = 2 * ((2 * np.arange(1, m + 1) - m - 1) * r).sum() / m**2  # E|X - X'|
    return np.array([np.abs(mu_i + r - y_i).mean() for y_i, mu_i in zip(y, mu)]) - spread / 2


def distributions(data: dict[str, pl.DataFrame]) -> None:
    """Spread arms on the current mean: CRPS and 80% coverage, each week fit on earlier weeks."""
    mean = ARMS["current"]
    for league, rows in data.items():
        test = scored(rows)
        out = {k: np.full(test.height, np.nan) for k in ("const", "linear", "empirical")}
        cover = {k: np.zeros(test.height, bool) for k in out}
        for season, week in test.select("season", "week").unique().sort("season", "week").iter_rows():
            before = (pl.col("season") < season) | ((pl.col("season") == season) & (pl.col("week") < week))
            fit = rows.filter(before & (pl.col("season") >= FIT_FROM)).drop_nulls([*sm.DEF_FEATURES, "points"])
            here = ((test["season"] == season) & (test["week"] == week)).to_numpy()
            new = test.filter(pl.Series(here))
            y, mu, mu_fit = new["points"].to_numpy(), mean(fit, new), mean(fit, fit)
            resid = fit["points"].to_numpy() - mu_fit
            sd = np.full(y.size, resid.std(ddof=1))
            b1, b0 = np.polyfit(mu_fit, np.abs(resid), 1)
            sd_lin = np.maximum(b0 + b1 * mu, 0.5) * np.sqrt(np.pi / 2)
            lo, hi = np.quantile(resid, [0.1, 0.9])
            out["const"][here] = crps_normal(y, mu, sd)
            out["linear"][here] = crps_normal(y, mu, sd_lin)
            out["empirical"][here] = crps_sample(y, mu, resid)
            cover["const"][here] = np.abs(y - mu) <= Z80 * sd
            cover["linear"][here] = np.abs(y - mu) <= Z80 * sd_lin
            cover["empirical"][here] = (y >= mu + lo) & (y <= mu + hi)
        base = out["const"]
        print(f"\n=== {league} (distribution arms on the current mean)")
        for k, c in out.items():
            d = test.select("season", "week").with_columns(d=pl.Series(c - base))
            per = d.group_by("season", "week").agg(pl.col("d").mean())["d"].to_numpy()
            t = per.mean() / (per.std(ddof=1) / np.sqrt(per.size)) if k != "const" else 0.0
            print(f"  {k:10} CRPS {c.mean():.4f} ({100 * (c.mean() / base.mean() - 1):+.2f}%)"
                  f"  t {t:+.2f}  80% coverage {cover[k].mean():.1%}")


def target(data: dict[str, pl.DataFrame]) -> None:
    """Does the scoring fix help the projection? The production model fit on the pre-fix points
    (main 50319c2e) against the same model fit on the corrected points, both scored on the
    corrected points."""
    from def_scoring_check import old_scorer

    old = old_scorer()
    streaming.defense_points_frame = lambda st, g, sc, lid, facts: old(st, g, sc, lid)
    old_data = load_leagues()
    for league, rows in data.items():
        test = scored(rows)
        new_pred = walk_forward(rows, ARMS["current"])
        old_rows = old_data[league]
        old_test = scored(old_rows).select(*KEY, old_pred=pl.Series(walk_forward(old_rows, ARMS["current"])))
        joined = test.select(*KEY, "points").with_columns(new_pred=pl.Series(new_pred)).join(old_test, on=KEY)
        y = joined["points"].to_numpy()
        e_new, e_old = y - joined["new_pred"].to_numpy(), y - joined["old_pred"].to_numpy()
        t = weekly_t(joined, e_new, e_old)
        changed = (scored(rows).join(scored(old_rows).select(*KEY, old_points="points"), on=KEY)
                   .filter(pl.col("points") != pl.col("old_points")))
        print(f"{league}: {changed.height} of {test.height} scored games change points "
              f"(mean change {(changed['points'] - changed['old_points']).mean():+.2f}); "
              f"RMSE on corrected points: fit on old {rmse(e_old):.3f}, fit on corrected "
              f"{rmse(e_new):.3f} ({100 * (rmse(e_new) / rmse(e_old) - 1):+.2f}%, t {t:+.2f}); "
              f"bias {e_old.mean():+.3f} -> {e_new.mean():+.3f}")


def candidates(data: dict[str, pl.DataFrame]) -> None:
    results = run_arms(data, ARMS)
    winners = [a for a in ARMS if a != "current" and all(results[lg][a]["pass"] for lg in results)]
    print("\npassing in both leagues:", winners or "none")


if __name__ == "__main__":
    main()
