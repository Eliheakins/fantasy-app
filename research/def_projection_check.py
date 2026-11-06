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

Walk-forward: every week from 2024 on is predicted by a fit on earlier weeks from 2019 on.
Paired t: per league, the per-week mean of the squared-error difference, over weeks.

Run from the repo root: uv run python research/def_projection_check.py diagnose|candidates
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


def league_rows(lg: dict, stats, games, facts, starters) -> pl.DataFrame:
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
    )
    rows = (
        rows.filter(pl.col("season") >= streaming.SCORED_FROM)
        .join(coded, on=["team", "season", "week"], how="left")
        .join(opp_qb, on=["opponent", "season", "week"], how="left")
        .rename({"team": "unit", "opp_implied": "implied"})
    )
    formed, _ = sm.with_form(rows, rows.head(0).select(KEY))
    trailed = sm.trailing(formed, "unit", list(COMPONENT_KEYS))
    return trailed.with_columns(pl.col("is_home").cast(pl.Float64))


def load_leagues() -> dict[str, pl.DataFrame]:
    stats = store.read_table("nfl_team_stats", "raw")
    games = store.read_table("team_games")
    last = int(stats["season"].max())
    facts = streaming.load_play_facts(range(streaming.SCORED_FROM, last + 1))
    starters = qb_starters()
    leagues = store.read_table("leagues", "raw")
    return {
        lg["league_key"]: league_rows(lg, stats, games, facts, starters)
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
    else:
        raise SystemExit(f"unknown mode {mode!r}")


def candidates(data: dict[str, pl.DataFrame]) -> None:
    raise SystemExit("register the candidates in docs/decisions.md first")


if __name__ == "__main__":
    main()
