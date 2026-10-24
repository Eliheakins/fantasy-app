"""Do the projection layers help on seasons their effects never saw?

The learned projection is the base. For each held-out season the outlook effects (return from an
absence, teammate vacancy) and the environment effects (opposing corner out, offense efficiency)
are estimated on the seasons before it, with the production estimators and the production rule
(an environment effect counts only if |t| is at least MIN_T), and applied to that season's
player-games. Reported: the change in RMSE of points over projection, overall and on the games a
layer touches. A layer that makes held-out error worse by more than TOLERANCE is a candidate to
switch off.

Run from the repo root after `make refresh`: uv run python research/layers_check.py
"""

import numpy as np
import polars as pl

from fantasy import store
from fantasy.sim.scoring_scale import reference_league
from fantasy.stages import environment as env
from fantasy.stages import outlook as out

FIRST_HELD_OUT = 2023  # at least two earlier seasons to estimate from
TOLERANCE = 0.001  # a layer may worsen held-out RMSE by this share before it is flagged


def outlook_prediction(frame: pl.DataFrame, effects: pl.DataFrame) -> pl.DataFrame:
    """Projection adjusted the way the outlook layer does: a ratio in the first and second game
    back, otherwise the vacancy slopes."""
    value = {(r["position"], r["kind"]): r["value"] for r in effects.iter_rows(named=True)}
    rows = []
    for r in frame.iter_rows(named=True):
        p = r["position"]
        if r["first_back"]:
            kind = "first_back_injury" if r["injured_gap"] else "first_back_other"
            pred = r["projection"] * value.get((p, kind), 1.0)
        elif r["second_back"]:
            kind = "second_back_injury" if r["prev_injured"] else "second_back_other"
            pred = r["projection"] * value.get((p, kind), 1.0)
        else:
            pred = (
                r["projection"]
                + value.get((p, "vac_target"), 0.0) * r["vac_target"]
                + value.get((p, "vac_carry"), 0.0) * r["vac_carry"]
            )
        rows.append(max(pred, 0.0))
    return frame.with_columns(pl.Series("outlook_pred", rows))


def environment_prediction(frame: pl.DataFrame, effects: pl.DataFrame) -> pl.DataFrame:
    """Projection plus the clear environment effects (|t| of at least MIN_T) times the features."""
    clear = effects.filter(pl.col("t").abs() >= env.MIN_T)
    kind_to_feature = {v: k for k, v in env.KINDS.items()}
    adjustment = pl.lit(0.0)
    for r in clear.iter_rows(named=True):
        feature = kind_to_feature[r["kind"]]
        adjustment = adjustment + pl.when(pl.col("position") == r["position"]).then(
            r["value"] * pl.col(feature).fill_null(0.0)
        ).otherwise(0.0)
    return frame.with_columns((pl.col("projection") + adjustment).clip(lower_bound=0.0).alias("env_pred"))


def rmse(frame: pl.DataFrame, column: str) -> float:
    return float(np.sqrt(((frame["points"] - frame[column]) ** 2).mean()))  # type: ignore[operator]


def main() -> None:
    leagues = store.read_table("leagues", "raw")
    league_id = reference_league(leagues)
    season = int(leagues["season"].to_numpy().max())
    panel = env.history_panel(league_id, season)
    outlook_panel = out.history_panel(league_id, season)  # the effects estimator wants booleans
    rows = []
    for held_out in sorted(s for s in panel["season"].unique().to_list() if s >= FIRST_HELD_OUT):
        train, test = panel.filter(pl.col("season") < held_out), panel.filter(pl.col("season") == held_out)
        o_train = outlook_panel.filter(pl.col("season") < held_out)
        o_test = outlook_prediction(
            outlook_panel.filter(pl.col("season") == held_out), out.estimate(o_train)
        ).select("gsis_id", "season", "week", "outlook_pred")
        test = environment_prediction(
            test.join(o_test, on=["gsis_id", "season", "week"], how="left"), env.estimate(train)
        ).with_columns(pl.col("outlook_pred").fill_null(pl.col("projection")))
        test = test.with_columns(
            (pl.col("projection") + (pl.col("outlook_pred") - pl.col("projection")) + (pl.col("env_pred") - pl.col("projection"))).clip(lower_bound=0.0).alias("both_pred")
        )
        touched_outlook = test.filter(
            (pl.col("first_back") > 0) | (pl.col("second_back") > 0) | (pl.col("vac_target") > 0) | (pl.col("vac_carry") > 0)
        )
        touched_env = test.filter(pl.col("cb_out") > 0)
        for layer, column, touched in (
            ("outlook", "outlook_pred", touched_outlook),
            ("environment", "env_pred", touched_env),
            ("both", "both_pred", test),
        ):
            base_all, new_all = rmse(test, "projection"), rmse(test, column)
            base_touch, new_touch = rmse(touched, "projection"), rmse(touched, column)
            rows.append(
                {
                    "held_out": held_out,
                    "layer": layer,
                    "rmse_change_pct": round(100 * (new_all - base_all) / base_all, 3),
                    "games_touched": touched.height,
                    "rmse_change_on_touched_pct": round(100 * (new_touch - base_touch) / base_touch, 3),
                }
            )
    result = pl.DataFrame(rows)
    with pl.Config(tbl_rows=20, tbl_width_chars=140):
        print(result.sort("layer", "held_out"))
        summary = result.group_by("layer").agg(
            pl.col("rmse_change_pct").mean().round(3).alias("mean_change_pct"),
            pl.col("rmse_change_on_touched_pct").mean().round(3).alias("mean_on_touched_pct"),
        )
        print(summary)
        for layer, change in zip(summary["layer"], summary["mean_change_pct"], strict=True):
            verdict = "FLAG (worse)" if change > 100 * TOLERANCE else "ok"
            print(f"{layer}: {verdict}")


if __name__ == "__main__":
    main()
