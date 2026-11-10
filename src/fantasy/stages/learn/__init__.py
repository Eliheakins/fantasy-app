"""Learned projections: a gradient-boosted model on lagged player features.

For a player and a target game the features use only games played BEFORE it (the same
rule as the rolling baseline): weighted averages at half-lives of 2, 4 and 8 games and the last
value of points, expected points, targets, carries, pass attempts, snap share, target share and
expected touchdowns, plus games played, the spread of recent points, position, week and the
game's Vegas lines, and teammate vacancy from the game's injury report (`stages/vacancy.py`).
History and future rows go through the same feature code.

History is projected walk-forward: a season is scored by a model that never saw it (the first
seasons, which have no earlier ones, leave one season out of an early block). Future weeks use a
model trained on everything played so far, with lines where they exist and without where they do
not. Models are retrained in the stage; only predictions are written, to `proj_learned`, which
has the schema of `proj_baseline` so every consumer reads either one.

The model is gradient boosting on squared error, trained on games with a stat line (an
opportunity row), so its projection is the expected points when the player has a stat line, the
same meaning as the baseline's. With `stat_line_model` on (config.toml) every projection is then
multiplied by the chance of a stat line when active (`stages/stat_line.py`), so `proj_learned`
holds the expected points of any game with a `player_points` row, stat-less appearances included.

Run: uv run python -m fantasy.stages.learn
"""

import polars as pl

from fantasy import stat_line_table, store
from fantasy.config import load_config
from fantasy.stages import stat_line
from fantasy.stages.lags import lag_asof, latest_asof, train_seasons
from fantasy.stages.learn.baseline import (
    MIN_GAIN,
    MIN_PROJECTION,
    MIN_T,
    compare_to_baseline,
    hurdle_on_played,
    paired,
)
from fantasy.stages.learn.features import (
    ADVANCED_COLUMNS,
    DEPTH_COLUMNS,
    ECR_COLUMNS,
    EXTRA_FEATURES,
    FIRST_ACCEPTANCE_SEASON,
    HALF_LIVES,
    KEY,
    LAG_COLUMNS,
    LINE_FEATURES,
    PACE_COLUMNS,
    ROLE_COLUMNS,
    SCHEDULE_FEATURES,
    STATE_FEATURES,
    VAC_SET,
    Extras,
    attach_extras,
    build_features,
    design,
    feature_frame,
    games_frame,
    load_extras,
    state_frame,
    with_lines,
    with_schedule,
    with_sleeper_stand_in,
)
from fantasy.stages.learn.model import (
    MAX_ITER,
    NULL_FAIL,
    NULL_WARN,
    _varies,
    check_next_game_nulls,
    fit_predict,
    history_forecasts,
    null_share_excess,
    predict_future,
    walk_forward,
)
from fantasy.stages.learn.projection import (
    Inputs,
    league_projections,
    stat_line_scaled,
    with_context,
)
from fantasy.stages.learn.snapshot import archive_snapshot, snapshot_frame, unplayed
from fantasy.stages.project import GROUP, current_and_rostered, expected_frame, future_targets

__all__ = [
    "ADVANCED_COLUMNS", "DEPTH_COLUMNS", "ECR_COLUMNS", "EXTRA_FEATURES",
    "FIRST_ACCEPTANCE_SEASON", "GROUP", "HALF_LIVES", "KEY", "LAG_COLUMNS", "LINE_FEATURES",
    "MAX_ITER", "MIN_GAIN", "MIN_PROJECTION", "MIN_T", "NULL_FAIL", "NULL_WARN", "PACE_COLUMNS",
    "ROLE_COLUMNS", "SCHEDULE_FEATURES", "STATE_FEATURES", "VAC_SET",
    "Extras", "Inputs", "_varies", "archive_snapshot", "attach_extras", "build_features",
    "check_next_game_nulls", "compare_to_baseline", "design", "feature_frame", "fit_predict",
    "games_frame", "history_forecasts", "hurdle_on_played", "lag_asof", "latest_asof",
    "league_projections", "load_extras", "main", "null_share_excess", "paired",
    "predict_future", "run", "snapshot_frame", "stat_line_scaled", "state_frame",
    "train_seasons", "unplayed", "walk_forward", "with_context", "with_lines", "with_schedule",
    "with_sleeper_stand_in",
]  # fmt: skip


def run() -> dict[str, int]:
    """Project every league's players, past (walk-forward) and future, and archive the next game.

    Reads `leagues`, `nfl_ff_opportunity`, `nfl_snaps`, `nfl_player_stats`, `player_points`,
    `team_games`, `player_form` and the role tables, after `project` (needs `proj_baseline`).
    Writes `proj_learned`, then `stat_line` (synced to the config), then appends the next game's
    projections to `proj_snapshots`. Returns the history and future row counts.
    """
    leagues = store.read_table("leagues", "raw")
    opp = store.read_table("nfl_ff_opportunity", "raw")
    points = store.read_table("player_points")
    snaps = store.read_table("nfl_snaps", "raw")
    stats = store.read_table("nfl_player_stats", "raw")
    exp = expected_frame(opp, points, leagues)
    lines = store.read_table("team_games")
    current, rostered = current_and_rostered()
    current_week = int(leagues["current_week"].max())  # type: ignore[arg-type]
    season = int(leagues["season"].max())  # type: ignore[arg-type]
    extras = load_extras()
    future_all = future_targets(
        store.read_table("player_form"), current, rostered, lines, first_week=current_week
    )
    # the next week with unplayed games, which is later than Sleeper's week once it is all played
    report_week = current_week if future_all.is_empty() else int(future_all["week"].min())  # type: ignore[arg-type]
    teams = future_all.filter(pl.col("week") == report_week)["team"].drop_nulls().unique()
    future_extras = with_sleeper_stand_in(
        extras, lines, season, report_week, sorted(teams.to_list())
    )
    chance, played = None, None
    if load_config().stat_line_model:
        raw = {"opp": opp, "snaps": snaps, "stats": stats, "depth": extras.depth}
        chance = stat_line.chances(exp, points, raw, future_all, current_week)
        played = stat_line.played_rows(points, exp, snaps, opp)
    data = Inputs(
        exp,
        games_frame(exp, opp, snaps, stats),
        lines,
        extras,
        future_all,
        played,
        future_extras,
        report_week,
    )
    keep = [*GROUP, "season", "week", "position", "team", "as_of_season", "as_of_week"]
    keep += ["has_history", "is_future", "projection"]
    out, statless = [], []
    for lid in leagues["league_id"].to_list():
        past, future, extra = league_projections(lid, data, chance)
        out += [past.select(keep), future.select(keep)]
        statless += [] if extra is None else [extra.select(*GROUP, "season", "week")]
    baseline = store.read_table("proj_baseline")
    final = with_context(pl.concat(out), baseline, pl.concat(statless) if statless else None)
    store.write_table("proj_learned", final.select(*store.SCHEMAS["proj_learned"]))
    # after proj_learned, so a table older than it is known to be stale
    stat_line_table.sync(None if chance is None else pl.concat(chance))
    archive_snapshot(final, current_week, lines)
    return {
        "history": final.filter(~pl.col("is_future")).height,
        "future": final.filter(pl.col("is_future")).height,
    }


def main() -> None:
    for name, count in run().items():
        print(f"{name}: {count} rows")
    with pl.Config(tbl_cols=10, tbl_width_chars=160):
        print(compare_to_baseline())
        hurdle = hurdle_on_played()
        if hurdle is not None:
            print("stat-line model on played games, q * E against E:")
            print(hurdle)
