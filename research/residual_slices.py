"""Where is the learned projection weak? Held-out residuals sliced by segment (2024 on).

The stored walk-forward projections (`proj_learned`, past games, each season scored by a model
trained on earlier ones) against points for QB, RB, WR and TE, on the rows `learn` scores: a
history and a projection above MIN_PROJECTION. For each slice and league: n, mean projection,
mean points, bias (projection minus points), RMSE, share of all squared error, and the rate of
games with no points. Slices: position, projection tier, week of season, season, rookie, last
injury-report status, home or away, game total and team implied total.

Read-only diagnosis: no model is fit. Bias z ignores that a player's games are not independent,
so a z under about 3 is not evidence.

Run from the repo root: uv run python research/residual_slices.py
"""

import numpy as np
import polars as pl

from fantasy import store
from fantasy.stages.learn.baseline import MIN_PROJECTION

FIRST_SEASON = 2024
POSITIONS = ["QB", "RB", "WR", "TE"]
KEY = ["league_id", "gsis_id", "season", "week"]
TIER_EDGES = [6.0, 10.0, 15.0, 20.0]
TIER_LABELS = ["a 3-6", "b 6-10", "c 10-15", "d 15-20", "e 20+"]
WEEK_EDGES = [3.0, 9.0, 14.0]
WEEK_LABELS = ["a wk 1-3", "b wk 4-9", "c wk 10-14", "d wk 15-18"]
TOTAL_EDGES = [41.0, 45.0, 49.0]
TOTAL_LABELS = ["a <41", "b 41-45", "c 45-49", "d 49+"]
IMPLIED_EDGES = [19.0, 22.0, 25.0]
IMPLIED_LABELS = ["a <19", "b 19-22", "c 22-25", "d 25+"]
SLICES = ["position", "tier", "week_of_season", "season_s", "rookie_s", "report", "home", "total", "implied"]


def bucket(column: str, edges: list[float], labels: list[str]) -> pl.Expr:
    return pl.col(column).cut(edges, labels=labels).cast(pl.Utf8)


def build_frame() -> pl.DataFrame:
    """KEY + position, projection, points, err (projection minus points) and the slice columns."""
    proj = store.projection_table().filter(~pl.col("is_future") & (pl.col("season") >= FIRST_SEASON))
    points = store.read_table("player_points").select(*KEY, "points", "team_implied", "total_line", "is_home")
    injuries = (
        store.read_table("nfl_injuries", "raw")
        .group_by("gsis_id", "season", "week")
        .agg(pl.col("report_status").drop_nulls().last().alias("report_status"))
    )
    rookies = (
        store.read_table("nfl_rosters_weekly", "raw")
        .group_by("gsis_id", "season")
        .agg((pl.col("years_exp").min() == 0).alias("rookie"))
    )
    frame = (
        proj.filter(pl.col("has_history") & (pl.col("projection") > MIN_PROJECTION))
        .filter(pl.col("position").is_in(POSITIONS))
        .select(*KEY, "position", "projection")
        .join(points, on=KEY, how="inner")
        .join(injuries, on=["gsis_id", "season", "week"], how="left")
        .join(rookies, on=["gsis_id", "season"], how="left")
    )
    return frame.with_columns(
        bucket("projection", TIER_EDGES, TIER_LABELS).alias("tier"),
        bucket("week", WEEK_EDGES, WEEK_LABELS).alias("week_of_season"),
        pl.col("season").cast(pl.Utf8).alias("season_s"),
        pl.col("rookie").fill_null(False).cast(pl.Utf8).alias("rookie_s"),
        pl.col("report_status").fill_null("none").alias("report"),
        pl.col("is_home").cast(pl.Utf8).alias("home"),
        bucket("total_line", TOTAL_EDGES, TOTAL_LABELS).alias("total"),
        bucket("team_implied", IMPLIED_EDGES, IMPLIED_LABELS).alias("implied"),
        (pl.col("points") <= 0).alias("zero"),
        (pl.col("projection") - pl.col("points")).alias("err"),
    )


def slice_table(frame: pl.DataFrame, column: str) -> pl.DataFrame:
    total_sse = (frame["err"] ** 2).sum()
    return (
        frame.drop_nulls(column)
        .group_by(column)
        .agg(
            pl.len().alias("n"),
            pl.col("projection").mean().round(2).alias("proj"),
            pl.col("points").mean().round(2).alias("pts"),
            pl.col("err").mean().round(2).alias("bias"),
            (pl.col("err").mean() / (pl.col("err").std() / pl.len().sqrt())).round(1).alias("bias_z"),
            (pl.col("err") ** 2).mean().sqrt().round(2).alias("rmse"),
            ((pl.col("err") ** 2).sum() / total_sse * 100).round(1).alias("sse_pct"),
            (pl.col("zero").mean() * 100).round(1).alias("zero_pct"),
        )
        .sort(column)
    )


def main() -> None:
    frame = build_frame()
    leagues = store.read_table("leagues", "raw")
    names = dict(zip(leagues["league_id"].to_list(), leagues["league_key"].to_list(), strict=True))
    pl.Config.set_tbl_rows(40)
    pl.Config.set_tbl_cols(12)
    for (league_id,), part in frame.group_by("league_id", maintain_order=True):
        rmse = np.sqrt((part["err"] ** 2).mean())
        print(f"\n===== {names[league_id]}: n {part.height}, RMSE {rmse:.3f}, bias {part['err'].mean():.3f}")
        for column in SLICES:
            print(f"\n-- {column}")
            print(slice_table(part, column))
        print("\n-- position x tier")
        print(
            part.group_by("position", "tier")
            .agg(
                pl.len().alias("n"),
                pl.col("err").mean().round(2).alias("bias"),
                (pl.col("err") ** 2).mean().sqrt().round(2).alias("rmse"),
            )
            .sort("position", "tier")
        )


if __name__ == "__main__":
    main()
