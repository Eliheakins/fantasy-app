"""Chance of playing the next game, from a classifier on pre-kickoff information.

The universe is every skill player on a team's depth chart for a game week who played in one of his
last three games, so a player who is hurt and does not play is in it. The label is whether he had
any offensive snaps. Features: depth rank, injury report status and practice participation, snap
share in earlier games, weeks since he last played, position and age. Scored on every listed
player, it beat the injury-status table by 6% Brier on report-listed players even though the table
had seen the test seasons (research/availability_check.py), so the simulation uses it for a
flagged player's chance of playing the next game; later games keep the table's curve.

Writes `availability` (gsis_id, season, week, p_play) for the current week.

Run: uv run python -m fantasy.stages.availability
"""

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier

from fantasy import store
from fantasy.config import load_config
from fantasy.stages.learn import KEY, lag_asof, latest_asof
from fantasy.store import SKILL, WEEK_STRIDE, week_index

STATUSES = ["none", "Questionable", "Doubtful", "Out"]
PRACTICES = ["full", "limited", "dnp"]
NUMERIC = ["depth_rank", "av_snap", "weeks_since", "age"]
FIRST_SEASON = 2019  # the lagged snap features need a prior season
REGULAR_WEEKS = 2  # played within this many weeks before the game
WEEKS_PER_SEASON = 18  # to count weeks across a season boundary
MAX_WEEKS_SINCE = 40
MIN_P, MAX_P = 1e-4, 1 - 1e-4


def build_rows() -> pl.DataFrame:
    """One row per regular on the depth chart and game week, with the label `played`. The rows of
    the current week (not yet played) are included, with the label 0."""
    depth = store.read_table("nfl_depth", "raw").unique(KEY, keep="first", maintain_order=True)
    snaps = (
        store.read_table("nfl_snaps", "raw")
        .filter(pl.col("gsis_id").is_not_null())
        .unique(KEY, keep="first", maintain_order=True)
        .select(
            *KEY,
            "position",
            pl.col("offense_snaps").cast(pl.Float64),
            pl.col("offense_pct").alias("snap"),
        )
    )
    inj = (
        store.read_table("nfl_injuries", "raw")
        .filter(pl.col("game_type") == "REG")
        .unique(KEY, keep="first", maintain_order=True)
        .select(
            *KEY,
            pl.col("report_status").fill_null("none").alias("status"),
            pl.col("practice_status").alias("practice_raw"),
            pl.coalesce("report_primary_injury", "practice_primary_injury").alias("body"),
            pl.when(pl.col("practice_status").str.contains("Did Not|DNP"))
            .then(pl.lit("dnp"))
            .when(pl.col("practice_status").str.contains("Limited"))
            .then(pl.lit("limited"))
            .otherwise(pl.lit("full"))
            .alias("practice"),
        )
    )
    played = snaps.filter(pl.col("offense_snaps") > 0).select(
        *KEY,
        pl.lit(1).alias("played_row"),
        (pl.col("season") * WEEKS_PER_SEASON + pl.col("week")).alias("when"),
    )
    rows = depth.join(inj, on=KEY, how="left").with_columns(
        pl.col("status").fill_null("none"), pl.col("practice").fill_null("full")
    )
    rows = latest_asof(rows, snaps.select(*KEY, "position"), "gsis_id", ["position"], shift=1)
    rows = rows.filter(pl.col("position").is_in(SKILL) & (pl.col("season") >= FIRST_SEASON))
    rows = lag_asof(rows, snaps, "gsis_id", ["snap"], "av")
    rows = latest_asof(
        rows, played.select("gsis_id", "season", "week", "when"), "gsis_id", ["when"], shift=1
    )
    roster = (
        store.read_table("nfl_rosters_weekly", "raw")
        .unique(KEY, keep="first", maintain_order=True)
        .select(*KEY, "age")
    )
    rows = latest_asof(rows, roster, "gsis_id", ["age"])
    rows = rows.join(played.select(*KEY, "played_row"), on=KEY, how="left").with_columns(
        pl.col("played_row").fill_null(0).alias("played"),
        (pl.col("season") * WEEKS_PER_SEASON + pl.col("week") - pl.col("when") - 1)
        .clip(0, MAX_WEEKS_SINCE)
        .alias("weeks_since"),
    )
    # the players the simulation projects: they played in one of their last three team games
    return rows.filter((pl.col("weeks_since") <= REGULAR_WEEKS) & pl.col("av_snap").is_not_null())


def design(frame: pl.DataFrame) -> np.ndarray:
    """Numeric features then one-hot status, practice and position, with fixed categories so a
    category a frame lacks (or does not know) is simply all zeros."""
    numeric = [frame[c].cast(pl.Float64).to_numpy() for c in NUMERIC]
    onehot = [
        (frame[column] == value).cast(pl.Float64).to_numpy()
        for column, values in (("status", STATUSES), ("practice", PRACTICES), ("position", SKILL))
        for value in values
    ]
    return np.column_stack(numeric + onehot)


def fit_predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray) -> np.ndarray:
    if x_test.shape[0] == 0:  # nothing on the depth chart yet (preseason, or not yet published)
        return np.empty(0)
    model = HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.05,
        max_leaf_nodes=15,
        min_samples_leaf=80,
        l2_regularization=5.0,
        random_state=0,
    )
    model.fit(x_train, y_train)
    return np.clip(model.predict_proba(x_test)[:, 1], MIN_P, MAX_P)


def has_injury_report(season: int, week: int) -> bool:
    """Whether nflverse has any injury report rows for the week (absent means not yet published,
    not that everyone is healthy)."""
    injuries = store.read_table("nfl_injuries", "raw")
    return injuries.filter((pl.col("season") == season) & (pl.col("week") == week)).height > 0


def run() -> int:
    leagues = store.read_table("leagues", "raw")
    season, week = load_config().season, int(leagues["current_week"].max())  # type: ignore[arg-type]
    rows = build_rows()
    is_now = (pl.col("season") == season) & (pl.col("week") == week)
    train, now = (
        rows.filter(~is_now & (week_index() < season * WEEK_STRIDE + week)),
        rows.filter(is_now),
    )
    if now.is_empty():
        print(
            f"availability: WARNING no depth chart rows for {season} week {week}; the table is "
            "empty and the simulation falls back to the injury table's curve for every player"
        )
    elif not has_injury_report(season, week):
        print(
            f"availability: WARNING no injury report rows for {season} week {week} yet; every "
            "player is scored as status none and full practice, so all look healthy"
        )
    pred = fit_predict(design(train), train["played"].to_numpy(), design(now))
    out = now.select(*KEY).with_columns(pl.Series("p_play", pred))
    store.write_table("availability", out)
    return out.height


def main() -> None:
    print(f"availability: {run()} rows")


if __name__ == "__main__":
    main()
