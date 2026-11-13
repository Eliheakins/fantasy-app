"""Held-out checks of the learned model: against the size-calibrated baseline, and the stat-line
hurdle on every played game."""

import numpy as np
import polars as pl

from fantasy import stat_line_table, store
from fantasy.sim.calibration import apply_curves
from fantasy.stages.distributions import estimate_curves, residual_frame
from fantasy.stages.learn.features import FIRST_ACCEPTANCE_SEASON, KEY
from fantasy.stages.project import GROUP

MIN_GAIN = 0.01  # the learned model must beat the calibrated baseline by this share of RMSE
MIN_T = 2.0
MIN_PROJECTION = 3.0  # as in the other held-out checks


def compare_to_baseline() -> pl.DataFrame:
    """Held-out check on the seasons from FIRST_ACCEPTANCE_SEASON: the learned projection against
    the baseline calibrated by size with curves fit on earlier seasons only, where the calibrated
    baseline is above MIN_PROJECTION. Paired per-week t on the squared error. With the stat-line
    model on, q is taken back out, so both sides are points given a stat line (like for like);
    `hurdle_on_played` scores the two-part projection."""
    baseline = store.read_table("proj_baseline").filter(~pl.col("is_future"))
    learned = store.read_table("proj_learned").filter(~pl.col("is_future"))
    chance = stat_line_table.stored()
    if chance is not None:
        learned = stat_line_table.divide(learned, chance, KEY)
    points = store.read_table("player_points")
    history = residual_frame(baseline, points)
    learned_view = learned.select(*GROUP, "season", "week", pl.col("projection").alias("learned"))
    points_view = points.select(*GROUP, "season", "week", "points")
    rows = []
    for (league_id,), league_base in baseline.group_by("league_id"):
        seasons = sorted(
            s for s in league_base["season"].unique().to_list() if s >= FIRST_ACCEPTANCE_SEASON
        )
        parts = []
        for season in seasons:
            curves = estimate_curves(
                history.filter((pl.col("league_id") == league_id) & (pl.col("season") < season))
            )
            base = apply_curves(league_base.filter(pl.col("season") == season), curves)
            scored = (
                base.filter(pl.col("has_history") & (pl.col("projection") > MIN_PROJECTION))
                .join(learned_view, on=[*GROUP, "season", "week"])
                .join(points_view, on=[*GROUP, "season", "week"])
            )
            parts.append(
                scored.with_columns(
                    ((pl.col("points") - pl.col("projection")) ** 2).alias("se_base"),
                    ((pl.col("points") - pl.col("learned")) ** 2).alias("se_learned"),
                )
            )
        data = pl.concat(parts)
        by_week = data.group_by("season", "week").agg(
            pl.col("se_base").mean().alias("a"), pl.col("se_learned").mean().alias("b")
        )
        t_stat, won = paired(by_week)
        rmse_base = float(np.sqrt(data["se_base"].to_numpy().mean()))
        rmse_learned = float(np.sqrt(data["se_learned"].to_numpy().mean()))
        gain = (rmse_base - rmse_learned) / rmse_base
        rows.append(
            {
                "league_id": league_id,
                "n": data.height,
                "rmse_baseline": round(rmse_base, 4),
                "rmse_learned": round(rmse_learned, 4),
                "gain_pct": round(100 * gain, 2),
                "paired_t": round(t_stat, 2),
                "weeks_better": f"{won}/{by_week.height}",
                "passes": gain >= MIN_GAIN and t_stat >= MIN_T,
            }
        )
    return pl.DataFrame(rows)


def paired(by_week: pl.DataFrame) -> tuple[float, int]:
    """Paired per-week t of `a` minus `b` (mean squared errors per week), and weeks `b` won."""
    diff = (by_week["a"] - by_week["b"]).to_numpy()
    return float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))), int((diff > 0).sum())


def hurdle_on_played() -> pl.DataFrame | None:
    """Held-out check of the stat-line model from FIRST_ACCEPTANCE_SEASON on every played game (a
    played game with no `player_points` row scores 0): q * E against E. None when it is off."""
    chance = stat_line_table.stored()
    if chance is None:
        return None
    hurdle = store.read_table("proj_learned").filter(
        ~pl.col("is_future") & (pl.col("season") >= FIRST_ACCEPTANCE_SEASON)
    )
    points = store.read_table("player_points").select(*GROUP, "season", "week", "points")
    rows = (
        stat_line_table.divide(hurdle, chance, KEY)
        .select(*GROUP, "season", "week", pl.col("projection").alias("e"))
        .join(
            hurdle.select(*GROUP, "season", "week", pl.col("projection").alias("qe")),
            on=[*GROUP, "season", "week"],
        )
        .join(points, on=[*GROUP, "season", "week"], how="left")
        .with_columns(pl.col("points").fill_null(0.0))
    )
    out = []
    for (league_id,), g in rows.group_by("league_id"):
        by_week = g.group_by("season", "week").agg(
            ((pl.col("e") - pl.col("points")) ** 2).mean().alias("a"),
            ((pl.col("qe") - pl.col("points")) ** 2).mean().alias("b"),
        )
        t_stat, won = paired(by_week)
        rmse_e = float(np.sqrt(((g["e"] - g["points"]) ** 2).to_numpy().mean()))
        rmse_qe = float(np.sqrt(((g["qe"] - g["points"]) ** 2).to_numpy().mean()))
        out.append(
            {
                "league_id": league_id,
                "n": g.height,
                "rmse_e": round(rmse_e, 4),
                "rmse_q_e": round(rmse_qe, 4),
                "gain_pct": round(100 * (rmse_e - rmse_qe) / rmse_e, 2),
                "paired_t": round(t_stat, 2),
                "weeks_better": f"{won}/{by_week.height}",
            }
        )
    return pl.DataFrame(out)
