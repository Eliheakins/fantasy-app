"""Rolling-origin rest-of-season check: does the learned model value players better over the
coming weeks, the quantity waiver and trade values are built from?

For an origin week w, every player's forecast for week w + k was made k games ahead from the state
at w (the future path as production runs it: lines only one game ahead, none further). The
forecasts for the next WINDOW weeks are summed over the games the player played and compared with
the points he scored in them, for the size-calibrated baseline (curves fit on earlier seasons), the
learned model, and a 75/25 mix. Reported per league: RMSE of the sums and the Spearman rank
correlation of predicted and actual sums, over players with at least MIN_GAMES games in the window.
Nothing is tuned here: the configuration is fixed before the check.

Run from the repo root after `make refresh`: uv run python research/ros_check.py
"""

import numpy as np
import polars as pl

from fantasy import store
from fantasy.sim.calibration import apply_curves
from fantasy.stages.distributions import estimate_curves, residual_frame
from fantasy.stages.learn import history_forecasts
from fantasy.stages.project import (
    FIRST_PROJECTED_SEASON,
    GROUP,
    build_form,
    expected_frame,
    position_prior,
    project_targets,
)

WINDOW = 6  # weeks ahead summed
MIN_GAMES = 3
SEASONS = (2024, 2025)
ORIGINS = (3, 5, 7, 9, 11)
MIX = 0.75  # weight on the learned model in the mix
KEY = [*GROUP, "season", "week"]


def forecasts() -> pl.DataFrame:
    """One row per league, player, target game and horizon with the baseline (size-calibrated with
    curves from earlier seasons) and the learned projection."""
    leagues = store.read_table("leagues", "raw")
    exp = expected_frame(
        store.read_table("nfl_ff_opportunity", "raw"), store.read_table("player_points"), leagues
    )
    prior = position_prior(exp)
    form = build_form(exp, prior)
    games = store.read_table("team_games")
    points = store.read_table("player_points")
    targets = exp.filter(pl.col("season") >= FIRST_PROJECTED_SEASON).select(
        *GROUP, "season", "week", "position", "team", "points"
    )
    parts = []
    for k in range(1, WINDOW + 1):
        base = project_targets(targets, form, prior, games, k).filter(pl.col("has_history"))
        history = residual_frame(base.drop("points").with_columns(is_future=pl.lit(False)), points)
        calibrated = []
        for season in SEASONS:
            curves = estimate_curves(history.filter(pl.col("season") < season))
            calibrated.append(apply_curves(base.filter(pl.col("season") == season), curves))
        learned = history_forecasts(k).rename({"projection": "learned"})
        parts.append(
            pl.concat(calibrated)
            .join(learned, on=KEY, how="inner")
            .select(*KEY, "position", "points", pl.col("projection").alias("baseline"), "learned")
            .with_columns(pl.lit(k).alias("horizon"))
        )
    return pl.concat(parts)


def ros_sums(rows: pl.DataFrame, league_id: str) -> pl.DataFrame:
    out = []
    league = rows.filter(pl.col("league_id") == league_id)
    for season in SEASONS:
        for origin in ORIGINS:
            window = league.filter(
                (pl.col("season") == season)
                & (pl.col("week") > origin)
                & (pl.col("week") <= origin + WINDOW)
                & (pl.col("horizon") == pl.col("week") - origin)
            ).with_columns((MIX * pl.col("learned") + (1 - MIX) * pl.col("baseline")).alias("mix"))
            sums = window.group_by("gsis_id").agg(
                pl.len().alias("games"),
                pl.col("points").sum().alias("actual"),
                pl.col("baseline").sum(),
                pl.col("learned").sum(),
                pl.col("mix").sum(),
            )
            out.append(
                sums.filter(pl.col("games") >= MIN_GAMES).with_columns(
                    pl.lit(season).alias("season"), pl.lit(origin).alias("origin")
                )
            )
    return pl.concat(out)


def summarize(sums: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for name in ("baseline", "learned", "mix"):
        err = (sums[name] - sums["actual"]).to_numpy()
        rank = np.mean(
            [
                float(g.select(pl.corr(name, "actual", method="spearman")).item())
                for _, g in sums.group_by("season", "origin")
            ]
        )
        rows.append(
            {
                "forecast": name,
                "players": sums.height,
                "rmse_of_sum": round(float(np.sqrt((err**2).mean())), 3),
                "mean_error": round(float(err.mean()), 3),
                "spearman": round(float(rank), 4),
            }
        )
    return pl.DataFrame(rows)


def main() -> None:
    rows = forecasts()
    for league_id in sorted(rows["league_id"].unique().to_list()):
        sums = ros_sums(rows, league_id)
        print(f"\nleague {league_id}: {sums.height} player-windows")
        print(summarize(sums))
        top = sums.filter(pl.col("baseline") > sums["baseline"].quantile(0.6))
        print("top 40% by projected sum:")
        print(summarize(top))


if __name__ == "__main__":
    main()
