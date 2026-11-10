"""Fit and predict: the gradient-boosted regressor, walk-forward history, the future rows, and the
next-game null check that runs before anything is written."""

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingRegressor

from fantasy import store
from fantasy.stages.lags import train_seasons
from fantasy.stages.learn.features import (
    DEPTH_COLUMNS,
    ECR_COLUMNS,
    build_features,
    design,
    games_frame,
    load_extras,
    state_frame,
)
from fantasy.stages.project import GROUP, expected_frame, history_targets

NULL_WARN = 0.10  # next-game rows may lack depth or ranking this much more often than history
NULL_FAIL = 0.30  # beyond this the model would be scoring features it was not trained on
MAX_ITER = 160  # fixed, chosen on 2021 to 2023 (early stopping had stopped near 125 to 170)


def _varies(column: np.ndarray) -> bool:
    finite = column[np.isfinite(column)]
    return len(np.unique(finite)) > 1


def fit_predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray) -> np.ndarray:
    # a column that is empty or constant in training carries nothing and breaks the binning
    usable = [j for j in range(x_train.shape[1]) if _varies(x_train[:, j])]
    x_train, x_test = x_train[:, usable], x_test[:, usable]
    model = HistGradientBoostingRegressor(
        loss="squared_error",
        max_iter=MAX_ITER,
        early_stopping=False,  # its validation split depends on the row order
        learning_rate=0.03,
        max_leaf_nodes=15,
        min_samples_leaf=80,
        l2_regularization=5.0,
        random_state=0,
    )
    model.fit(x_train, y_train)
    return np.clip(model.predict(x_test), 0.0, None)


def walk_forward(
    history: pl.DataFrame,
    lines: bool = True,
    extra: pl.DataFrame | None = None,
    vacancy: bool = True,
) -> pl.DataFrame:
    """history: feature rows with `points`. A projection for every row from a model that did not
    see that row's season. `extra` rows (stat-less games) are projected by the same models but
    never trained on."""
    seasons = sorted(history["season"].unique().to_list())
    parts = []
    for season in seasons:
        train = history.filter(pl.col("season").is_in(train_seasons(season, seasons)))
        test = history.filter(pl.col("season") == season)
        if extra is not None:
            test = pl.concat(
                [test, extra.filter(pl.col("season") == season)], how="diagonal_relaxed"
            )
        pred = fit_predict(
            design(train, lines, vacancy), train["points"].to_numpy(), design(test, lines, vacancy)
        )
        parts.append(test.with_columns(pl.Series("projection", pred)))
    return pl.concat(parts)


def predict_future(history: pl.DataFrame, future: pl.DataFrame, report_week: int) -> pl.DataFrame:
    """Future rows from a model trained on all history: with lines where the game has them, the
    version without lines elsewhere; with the vacancy columns in `report_week` (the next week,
    which has a report or Sleeper's stand-in), without them later (with no report an all-zero
    vacancy would read as a fully healthy team, which is not the average state)."""
    has_line = pl.col("team_implied").is_not_null() & pl.col("total_line").is_not_null()
    has_report = pl.col("week") == report_week
    parts = []
    for lines, vac in ((True, True), (True, False), (False, True), (False, False)):
        rows = future.filter(
            (has_line if lines else ~has_line) & (has_report if vac else ~has_report)
        )
        if rows.is_empty():
            continue
        pred = fit_predict(
            design(history, lines, vac), history["points"].to_numpy(), design(rows, lines, vac)
        )
        parts.append(rows.with_columns(pl.Series("projection", pred)))
    return pl.concat(parts) if parts else future.with_columns(pl.lit(0.0).alias("projection"))


def history_forecasts(horizon: int = 1) -> pl.DataFrame:
    """Walk-forward projections for past games made `horizon` games ahead. One game ahead uses the
    game's lines; further ahead no lines exist, so none are used (the future path in `run`)."""
    leagues = store.read_table("leagues", "raw")
    opp = store.read_table("nfl_ff_opportunity", "raw")
    exp = expected_frame(opp, store.read_table("player_points"), leagues)
    games_all = games_frame(
        exp,
        opp,
        store.read_table("nfl_snaps", "raw"),
        store.read_table("nfl_player_stats", "raw"),
    )
    lines = store.read_table("team_games")
    extras = load_extras()
    parts = []
    for lid in leagues["league_id"].to_list():
        games = games_all.filter(pl.col("league_id") == lid)
        targets = history_targets(exp.filter(pl.col("league_id") == lid))
        features = build_features(targets, state_frame(games), lines, extras, horizon)
        history = features.join(
            games.select(*GROUP, "season", "week", "points"), on=[*GROUP, "season", "week"]
        )
        parts.append(
            walk_forward(history, lines=horizon == 1, vacancy=horizon == 1).select(
                *GROUP, "season", "week", "projection"
            )
        )
    return pl.concat(parts)


def null_share_excess(history: pl.DataFrame, nxt: pl.DataFrame) -> dict[str, float]:
    """Per depth and ranking column, the share of next-game rows that are null minus the share in
    history. The columns are joined on the exact week, so a chart or ranking not yet published
    leaves nulls the model was trained to see only as often as history had them."""
    columns = [*DEPTH_COLUMNS, *ECR_COLUMNS]
    return {
        c: nxt[c].null_count() / nxt.height - history[c].null_count() / history.height
        for c in columns
    }


def check_next_game_nulls(history: pl.DataFrame, future: pl.DataFrame) -> None:
    """Warn, or raise before anything is written, when next-game rows are missing depth or
    ranking features far more often than the training rows."""
    if future.is_empty():
        print("learn: WARNING no future rows to check for missing depth or ranking")
        return
    # the next week with rows, which is not Sleeper's current week once that week has been played
    nxt = future.filter(pl.col("week") == future["week"].min())
    excess = null_share_excess(history, nxt)
    print(
        "learn: next-game null share above history: "
        + ", ".join(f"{c} {v:+.0%}" for c, v in excess.items())
    )
    worst_column, worst = max(excess.items(), key=lambda kv: kv[1])
    if worst > NULL_FAIL:
        raise ValueError(
            f"{worst:.0%} more next-game rows than history lack {worst_column}: "
            "the depth chart or ranking for the week is missing"
        )
    if worst > NULL_WARN:
        print(f"learn: WARNING next-game rows lack {worst_column} {worst:.0%} more than history")
