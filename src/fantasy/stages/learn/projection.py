"""One league's learned projections: past rows walk-forward, future rows from the full history,
then the stat-line scaling and the baseline's context."""

from dataclasses import dataclass

import polars as pl

from fantasy import stat_line_table
from fantasy.stages import stat_line
from fantasy.stages.learn.features import KEY, Extras, build_features, state_frame
from fantasy.stages.learn.model import check_next_game_nulls, predict_future, walk_forward
from fantasy.stages.project import GROUP, history_targets


def with_context(
    rows: pl.DataFrame, baseline: pl.DataFrame, statless: pl.DataFrame | None
) -> pl.DataFrame:
    """`rows` with proj_baseline's context: the row's own, or for a played game without a stat
    line (`statless`: league_id, gsis_id, season, week), which has no baseline row, the mean of
    his team-week's. 1.0 where neither exists. Rows other than stat-less ones without a baseline
    row are reported, and so, separately, are stat-less rows with no team-week context."""
    keys = [*GROUP, "season", "week"]
    team_keys = ["league_id", "season", "week", "team"]
    team = (
        baseline.drop_nulls("team").group_by(team_keys).agg(pl.col("context").mean().alias("_team"))
    )
    joined = rows.join(baseline.select(*keys, "context"), on=keys, how="left")
    if statless is None:
        joined = joined.with_columns(pl.lit(None, pl.Boolean).alias("_statless"))
    else:
        flagged = statless.select(keys).unique().with_columns(pl.lit(True).alias("_statless"))
        joined = (
            joined.join(flagged, on=keys, how="left")
            .join(team, on=team_keys, how="left")
            .with_columns(
                pl.when(pl.col("_statless"))
                .then(pl.coalesce("context", "_team"))
                .otherwise(pl.col("context"))
                .alias("context")
            )
            .drop("_team")
        )
    missing = joined.filter(pl.col("context").is_null())
    unmatched = missing.filter(pl.col("_statless").is_null()).height
    if unmatched:
        print(f"learn: {unmatched} projection rows have no proj_baseline row; context set to 1.0")
    no_team = missing.height - unmatched
    if no_team:
        print(f"learn: {no_team} stat-less rows have no team-week context; context set to 1.0")
    return joined.with_columns(pl.col("context").fill_null(1.0)).drop("_statless")


def stat_line_scaled(
    past: pl.DataFrame,
    future: pl.DataFrame,
    chance: tuple[pl.DataFrame, pl.DataFrame] | None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """With the stat-line model on (`chance`: past and future q by game), E[points | stat line]
    becomes E[points | played]; otherwise both frames are returned unchanged."""
    if chance is None:
        return past, future
    return stat_line_table.scale(past, chance[0], KEY), stat_line_table.scale(
        future, chance[1], KEY
    )


@dataclass(frozen=True)
class Inputs:
    """The tables one `run` projects from."""

    exp: pl.DataFrame
    games: pl.DataFrame
    lines: pl.DataFrame
    extras: Extras
    future: pl.DataFrame
    played: pl.DataFrame | None  # every played game, when the stat-line model is on
    future_extras: Extras  # with Sleeper's stand-in for the next week; history never sees it
    report_week: int  # the first week with unplayed games


def league_projections(
    lid: str, data: Inputs, chance: tuple[pl.DataFrame, pl.DataFrame] | None
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame | None]:
    """Past and future projection rows for one league, and its stat-less targets (or None)."""
    games = data.games.filter(pl.col("league_id") == lid)
    state = state_frame(games)
    targets = history_targets(data.exp.filter(pl.col("league_id") == lid))
    history = build_features(targets, state, data.lines, data.extras).join(
        games.select(*GROUP, "season", "week", "points"), on=[*GROUP, "season", "week"]
    )
    statless, extra = None, None  # stat-less games get a projection too, so the shapes see them
    if data.played is not None:
        statless = stat_line.statless_targets(data.played, lid)
        extra = build_features(statless, state, data.lines, data.extras)
    past = walk_forward(history, extra=extra).with_columns(is_future=pl.lit(False))
    future_features = build_features(
        data.future.filter(pl.col("league_id") == lid), state, data.lines, data.future_extras
    )
    check_next_game_nulls(history, future_features)
    future = predict_future(history, future_features, data.report_week).with_columns(
        is_future=pl.lit(True)
    )
    past, future = stat_line_scaled(past, future, chance)
    return past, future, statless
