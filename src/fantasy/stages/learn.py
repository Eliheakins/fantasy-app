"""Learned projections: a gradient-boosted model on lagged player features.

For a player and a target game the features use only games played BEFORE it (the same
rule as the rolling baseline): weighted averages at half-lives of 2, 4 and 8 games and the last
value of points, expected points, targets, carries, pass attempts, snap share, target share and
expected touchdowns, plus games played, the spread of recent points, position, week and the
game's Vegas lines. History and future rows go through the same feature code.

History is projected walk-forward: a season is scored by a model that never saw it (the first
seasons, which have no earlier ones, leave one season out of an early block). Future weeks use a
model trained on everything played so far, with lines where they exist and without where they do
not. Models are retrained in the stage; only predictions are written, to `proj_learned`, which
has the schema of `proj_baseline` so every consumer reads either one.

The model is gradient boosting on squared error, so its projection is the expected points when
the player plays, the same meaning as the baseline's.

Run: uv run python -m fantasy.stages.learn
"""

from dataclasses import dataclass

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingRegressor

from fantasy import store
from fantasy.sim.calibration import apply_curves
from fantasy.stages.distributions import estimate_curves, residual_frame
from fantasy.stages.project import (
    GROUP,
    current_and_rostered,
    expected_frame,
    future_targets,
    history_targets,
)

LAG_COLUMNS = (
    "points",
    "exp_pts",
    "tgt",
    "car",
    "att",
    "snap",
    "tshare",
    "rec_td_exp",
    "rush_td_exp",
)
HALF_LIVES = (2, 4, 8)
STATE_FEATURES = [f"{c}_hl{h}" for c in LAG_COLUMNS for h in HALF_LIVES]
STATE_FEATURES += [f"{c}_last" for c in LAG_COLUMNS] + ["n_games", "pts_sd8"]
LINE_FEATURES = ["team_implied", "total_line", "is_home", "spread"]
SCHEDULE_FEATURES = ["rest", "indoor"]
ROLE_COLUMNS = ["age", "years_exp", "draft_pick"]  # static: the latest roster row up to the game
DEPTH_COLUMNS = ["depth_rank"]  # the chart for the game (the origin's chart when further ahead)
ECR_COLUMNS = ["ecr_pos", "ecr_pos_sd", "ecr_pos_range", "ecr_all", "ecr_all_sd", "ecr_all_range"]
PACE_COLUMNS = ["plays", "dropbacks", "pass_oe", "team_epa"]  # lagged team pace
KEY = ["gsis_id", "season", "week"]
ADVANCED_COLUMNS = [c for c in store.SCHEMAS["nfl_advanced"] if c not in KEY]  # lagged
EXTRA_FEATURES = (
    ROLE_COLUMNS
    + DEPTH_COLUMNS
    + ECR_COLUMNS
    + [f"pace_{c}" for c in PACE_COLUMNS]
    + [f"adv_{c}" for c in ADVANCED_COLUMNS]
    + SCHEDULE_FEATURES
)
EXTRA_HALF_LIFE = 4.0  # games, for the lagged team and advanced stats
MIN_TRAIN_SEASONS = 2  # a season with fewer earlier seasons is scored by leave-one-season-out
EARLY_BLOCK = 4  # seasons in that early block
FIRST_ACCEPTANCE_SEASON = 2024
MIN_GAIN = 0.01  # the learned model must beat the calibrated baseline by this share of RMSE
MIN_T = 2.0
MIN_PROJECTION = 3.0  # as in the other held-out checks


def games_frame(
    exp: pl.DataFrame, opp: pl.DataFrame, snaps: pl.DataFrame, stats: pl.DataFrame
) -> pl.DataFrame:
    """Per league and player-game: points, expected points and the usage columns that get lagged."""
    volume = opp.select(
        pl.col("player_id").alias("gsis_id"),
        "season",
        "week",
        pl.col("rec_attempt").cast(pl.Float64).alias("tgt"),
        pl.col("rush_attempt").cast(pl.Float64).alias("car"),
        pl.col("pass_attempt").cast(pl.Float64).alias("att"),
        pl.col("rec_touchdown_exp").cast(pl.Float64).alias("rec_td_exp"),
        pl.col("rush_touchdown_exp").cast(pl.Float64).alias("rush_td_exp"),
    ).unique(KEY)
    snap = (
        snaps.filter(pl.col("gsis_id").is_not_null())
        .select(*KEY, pl.col("offense_pct").cast(pl.Float64).alias("snap"))
        .unique(KEY)
    )
    share = (
        stats.filter(pl.col("season_type") == "REG")
        .select(
            pl.col("player_id").alias("gsis_id"),
            "season",
            "week",
            pl.col("target_share").cast(pl.Float64).alias("tshare"),
        )
        .unique(KEY)
    )
    return (
        exp.join(volume, on=KEY, how="left")
        .join(snap, on=KEY, how="left")
        .join(share, on=KEY, how="left")
    )


def state_frame(games: pl.DataFrame) -> pl.DataFrame:
    """Each player's state AFTER each game: weighted averages, last values, games played."""
    ordered = games.sort(*GROUP, "season", "week")
    lag = []
    for column in LAG_COLUMNS:
        for half_life in HALF_LIVES:
            # a value missing in the latest game carries the earlier one forward
            lag.append(
                pl.col(column)
                .forward_fill()
                .ewm_mean(half_life=half_life)
                .over(GROUP)
                .alias(f"{column}_hl{half_life}")
            )
        lag.append(pl.col(column).alias(f"{column}_last"))
    return ordered.with_columns(
        *lag,
        pl.int_range(1, pl.len() + 1).over(GROUP).alias("n_games"),
        pl.col("points").rolling_std(8, min_samples=3).over(GROUP).alias("pts_sd8"),
    ).select(
        *GROUP,
        (pl.col("season") * 100 + pl.col("week")).alias("t"),
        pl.col("season").alias("as_of_season"),
        pl.col("week").alias("as_of_week"),
        *STATE_FEATURES,
    )


def feature_frame(targets: pl.DataFrame, state: pl.DataFrame, horizon: int = 1) -> pl.DataFrame:
    """targets: league_id, gsis_id, season, week, position, team. Joins the state from the last
    game strictly before the target (a larger horizon looks that many weeks further back)."""
    index = pl.col("season") * 100 + pl.col("week")
    joined = (
        targets.with_columns((index - (horizon - 1)).alias("t"))
        .sort("t")
        .join_asof(
            state.sort("t"), on="t", by=GROUP, strategy="backward", allow_exact_matches=False
        )
    )
    return joined.with_columns(has_history=pl.col("n_games").is_not_null()).drop("t")


def with_lines(frame: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    """Adds the game's Vegas lines where they exist (later weeks have none)."""
    lines = games.select("season", "week", "team", *LINE_FEATURES).unique(
        ["season", "week", "team"]
    )
    return frame.join(lines, on=["season", "week", "team"], how="left")


@dataclass(frozen=True)
class Extras:
    """Role and context tables from `ingest_role`."""

    roster: pl.DataFrame
    depth: pl.DataFrame
    ecr: pl.DataFrame
    pace: pl.DataFrame
    advanced: pl.DataFrame


def load_extras() -> Extras:
    read = {
        n: store.read_table(f"nfl_{n}", "raw") for n in ("depth", "ecr", "team_pace", "advanced")
    }
    return Extras(
        roster=store.read_table("nfl_rosters_weekly", "raw"),
        depth=read["depth"],
        ecr=read["ecr"],
        pace=read["team_pace"],
        advanced=read["advanced"],
    )


def _index() -> pl.Expr:
    return pl.col("season") * 100 + pl.col("week")


def lag_asof(
    target: pl.DataFrame,
    table: pl.DataFrame,
    by: str,
    cols: list[str],
    prefix: str,
    shift: int = 0,
) -> pl.DataFrame:
    """Each column's weighted average over the rows of `table` strictly before the target game
    (`shift` weeks earlier, for a forecast made further ahead), as `<prefix>_<column>`. A value
    missing in the latest row carries the earlier one forward."""
    lagged = [f"{prefix}_{c}" for c in cols]
    state = (
        table.sort(by, "season", "week")
        .with_columns(
            *[
                pl.col(c)
                .forward_fill()
                .ewm_mean(half_life=EXTRA_HALF_LIFE)
                .over(by)
                .alias(f"{prefix}_{c}")
                for c in cols
            ],
            _index().alias("t"),
        )
        .select(by, "t", *lagged)
        .sort("t")
    )
    left = target.with_columns((_index() - shift).alias("t")).sort("t")
    return left.join_asof(
        state, on="t", by=by, strategy="backward", allow_exact_matches=False
    ).drop("t")


def latest_asof(
    target: pl.DataFrame, table: pl.DataFrame, by: str, cols: list[str], shift: int = 0
) -> pl.DataFrame:
    """For attributes that hold until they change (age, draft pick, a depth chart): the latest
    row of `table` at or before the target game, `shift` weeks earlier. A game beyond the
    table's last week keeps the last known value."""
    right = table.select(by, _index().alias("t"), *cols).sort("t")
    left = target.with_columns((_index() - shift).alias("t")).sort("t")
    return left.join_asof(right, on="t", by=by, strategy="backward").drop("t")


def with_schedule(frame: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    """Rest days and an indoor flag for the game: both are known when the schedule is."""
    sched = games.select(
        "season",
        "week",
        "team",
        pl.col("rest").cast(pl.Float64),
        pl.col("roof").is_in(["dome", "closed"]).cast(pl.Float64).alias("indoor"),
    ).unique(["season", "week", "team"])
    return frame.join(sched, on=["season", "week", "team"], how="left")


def attach_extras(
    frame: pl.DataFrame, extras: Extras, games: pl.DataFrame, horizon: int = 1
) -> pl.DataFrame:
    """Adds the role and context features. One game ahead the depth chart and expert ranking are
    the game's own; further ahead the chart is the origin's and no ranking exists, as for the
    later weeks of a live projection."""
    out = with_schedule(frame, games)
    if horizon == 1:
        out = out.join(extras.depth.unique(KEY), on=KEY, how="left").join(
            extras.ecr.unique(KEY), on=KEY, how="left"
        )
    else:
        out = latest_asof(out, extras.depth.unique(KEY), "gsis_id", DEPTH_COLUMNS, horizon - 1)
        out = out.with_columns([pl.lit(None, dtype=pl.Float64).alias(c) for c in ECR_COLUMNS])
    out = latest_asof(out, extras.roster.unique(KEY), "gsis_id", ROLE_COLUMNS)
    out = lag_asof(out, extras.pace, "team", PACE_COLUMNS, "pace", horizon - 1)
    return lag_asof(
        out, extras.advanced.unique(KEY), "gsis_id", ADVANCED_COLUMNS, "adv", horizon - 1
    )


def build_features(
    targets: pl.DataFrame,
    state: pl.DataFrame,
    games: pl.DataFrame,
    extras: Extras,
    horizon: int = 1,
) -> pl.DataFrame:
    """State, lines (one game ahead only) and role features for the target rows."""
    features = attach_extras(feature_frame(targets, state, horizon), extras, games, horizon)
    return with_lines(features, games) if horizon == 1 else features


def design(frame: pl.DataFrame, lines: bool) -> np.ndarray:
    columns = [*STATE_FEATURES, "week", "is_qb", "is_rb", "is_wr"] + (
        LINE_FEATURES if lines else []
    )
    columns += EXTRA_FEATURES
    out = frame.with_columns(
        *[
            (pl.col("position") == p).cast(pl.Float64).alias(f"is_{p.lower()}")
            for p in ("QB", "RB", "WR")
        ]
    )
    return out.select([pl.col(c).cast(pl.Float64) for c in columns]).to_numpy()


def train_seasons(season: int, available: list[int]) -> list[int]:
    """The seasons a model scoring `season` may train on: earlier ones, or for the first
    seasons (too few earlier ones) the other seasons of the early block."""
    ordered = sorted(available)
    prior = [s for s in ordered if s < season]
    if len(prior) >= MIN_TRAIN_SEASONS:
        return prior
    return [s for s in ordered[:EARLY_BLOCK] if s != season]


def _varies(column: np.ndarray) -> bool:
    finite = column[np.isfinite(column)]
    return len(np.unique(finite)) > 1


def fit_predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray) -> np.ndarray:
    # a column that is empty or constant in training carries nothing and breaks the binning
    usable = [j for j in range(x_train.shape[1]) if _varies(x_train[:, j])]
    x_train, x_test = x_train[:, usable], x_test[:, usable]
    model = HistGradientBoostingRegressor(
        loss="squared_error",
        max_iter=400,
        learning_rate=0.03,
        max_leaf_nodes=15,
        min_samples_leaf=80,
        l2_regularization=5.0,
        random_state=0,
    )
    model.fit(x_train, y_train)
    return np.clip(model.predict(x_test), 0.0, None)


def walk_forward(history: pl.DataFrame, lines: bool = True) -> pl.DataFrame:
    """history: feature rows with `points`. A projection for every row from a model that did not
    see that row's season."""
    seasons = sorted(history["season"].unique().to_list())
    parts = []
    for season in seasons:
        train = history.filter(pl.col("season").is_in(train_seasons(season, seasons)))
        test = history.filter(pl.col("season") == season)
        pred = fit_predict(design(train, lines), train["points"].to_numpy(), design(test, lines))
        parts.append(test.with_columns(pl.Series("projection", pred)))
    return pl.concat(parts)


def predict_future(history: pl.DataFrame, future: pl.DataFrame) -> pl.DataFrame:
    """Future rows from a model trained on all history: with lines where the game has them, the
    version without lines elsewhere."""
    has_line = pl.col("team_implied").is_not_null() & pl.col("total_line").is_not_null()
    parts = []
    for lines, rows in ((True, future.filter(has_line)), (False, future.filter(~has_line))):
        if rows.is_empty():
            continue
        pred = fit_predict(
            design(history, lines), history["points"].to_numpy(), design(rows, lines)
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
            walk_forward(history, lines=horizon == 1).select(*GROUP, "season", "week", "projection")
        )
    return pl.concat(parts)


def run() -> dict[str, int]:
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
    current, rostered = current_and_rostered()
    future_all = future_targets(store.read_table("player_form"), current, rostered, lines)
    context = store.read_table("proj_baseline").select(*GROUP, "season", "week", "context")
    keep = [*GROUP, "season", "week", "position", "team", "as_of_season", "as_of_week"]
    keep += ["has_history", "is_future", "projection"]
    out = []
    for lid in leagues["league_id"].to_list():
        games = games_all.filter(pl.col("league_id") == lid)
        state = state_frame(games)
        targets = history_targets(exp.filter(pl.col("league_id") == lid))
        history = build_features(targets, state, lines, extras).join(
            games.select(*GROUP, "season", "week", "points"), on=[*GROUP, "season", "week"]
        )
        past = walk_forward(history).with_columns(is_future=pl.lit(False))
        future_features = build_features(
            future_all.filter(pl.col("league_id") == lid), state, lines, extras
        )
        future = predict_future(history, future_features).with_columns(is_future=pl.lit(True))
        out += [past.select(keep), future.select(keep)]
    final = (
        pl.concat(out)
        .join(context, on=[*GROUP, "season", "week"], how="left")
        .with_columns(pl.col("context").fill_null(1.0))
    )
    store.write_table("proj_learned", final.select(*store.SCHEMAS["proj_learned"]))
    return {
        "history": final.filter(~pl.col("is_future")).height,
        "future": final.filter(pl.col("is_future")).height,
    }


def compare_to_baseline() -> pl.DataFrame:
    """Held-out check on the seasons from FIRST_ACCEPTANCE_SEASON: the learned projection against
    the baseline calibrated by size with curves fit on earlier seasons only, where the calibrated
    baseline is above MIN_PROJECTION. Paired per-week t on the squared error."""
    baseline = store.read_table("proj_baseline").filter(~pl.col("is_future"))
    learned = store.read_table("proj_learned").filter(~pl.col("is_future"))
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
            pl.col("se_base").mean(), pl.col("se_learned").mean()
        )
        diff = (by_week["se_base"] - by_week["se_learned"]).to_numpy()
        rmse_base = float(np.sqrt(data["se_base"].to_numpy().mean()))
        rmse_learned = float(np.sqrt(data["se_learned"].to_numpy().mean()))
        t_stat = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff))))
        gain = (rmse_base - rmse_learned) / rmse_base
        rows.append(
            {
                "league_id": league_id,
                "n": data.height,
                "rmse_baseline": round(rmse_base, 4),
                "rmse_learned": round(rmse_learned, 4),
                "gain_pct": round(100 * gain, 2),
                "paired_t": round(t_stat, 2),
                "weeks_better": f"{int((diff > 0).sum())}/{len(diff)}",
                "passes": gain >= MIN_GAIN and t_stat >= MIN_T,
            }
        )
    return pl.DataFrame(rows)


def main() -> None:
    for name, count in run().items():
        print(f"{name}: {count} rows")
    with pl.Config(tbl_cols=10, tbl_width_chars=160):
        print(compare_to_baseline())


if __name__ == "__main__":
    main()
