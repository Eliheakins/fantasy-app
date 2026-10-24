"""Does a chance-of-playing model beat the injury-status table, scored on every listed player?

The universe is every skill player on a team's depth chart for a game week who played in one of his
last three games (the players the simulation projects; a player who is hurt and does not play is in
it). The label is whether he had any offensive snaps. Features are known
before kickoff: depth rank, injury report status and practice participation, his snap share in
earlier games, how many weeks since he last played, position and age. The comparison is the
simple status table the injury layer is built on (mean played by report status, practice
participation and position, fit on the training seasons) against a gradient-boosted classifier
trained on the same seasons. Train 2019 to 2023, score 2024 to 2025 (Brier score and log loss).

Run from the repo root after `make refresh`:
    uv run python research/availability_check.py
"""

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss

from fantasy import store
from fantasy.stages.learn import KEY, lag_asof, latest_asof

TRAIN_END = 2023
FIRST_SEASON = 2019  # lagged snap features need a prior season
SKILL = ["QB", "RB", "WR", "TE"]
STATUS_KEYS = ["status", "practice", "position"]
REGULAR_WEEKS = 2  # played within this many weeks before the game


def build() -> pl.DataFrame:
    depth = store.read_table("nfl_depth", "raw").unique(KEY)
    snaps = (
        store.read_table("nfl_snaps", "raw")
        .filter(pl.col("gsis_id").is_not_null())
        .unique(KEY)
        .select(*KEY, "position", pl.col("offense_snaps").cast(pl.Float64), pl.col("offense_pct").alias("snap"))
    )
    inj = (
        store.read_table("nfl_injuries", "raw")
        .filter(pl.col("game_type") == "REG")
        .unique(KEY, keep="first")
        .select(
            *KEY,
            pl.col("report_status").fill_null("none").alias("status"),
            pl.when(pl.col("practice_status").str.contains("Did Not|DNP"))
            .then(pl.lit("dnp"))
            .when(pl.col("practice_status").str.contains("Limited"))
            .then(pl.lit("limited"))
            .otherwise(pl.lit("full"))
            .alias("practice"),
        )
    )
    played = snaps.filter(pl.col("offense_snaps") > 0).select(*KEY, pl.lit(1).alias("played_row"))
    rows = depth.join(inj, on=KEY, how="left").with_columns(
        pl.col("status").fill_null("none"), pl.col("practice").fill_null("full")
    )
    rows = latest_asof(rows, snaps.select(*KEY, "position"), "gsis_id", ["position"], shift=1)
    rows = rows.filter(pl.col("position").is_in(SKILL) & (pl.col("season") >= FIRST_SEASON))
    rows = lag_asof(rows.with_columns(pl.col("depth_rank").alias("depth")), snaps, "gsis_id", ["snap"], "av")
    last_played = played.with_columns((pl.col("season") * 18 + pl.col("week")).alias("when"))
    rows = latest_asof(
        rows.with_columns(pl.lit(0).alias("marker")),
        last_played.select("gsis_id", "season", "week", "when"),
        "gsis_id",
        ["when"],
        shift=1,
    )
    roster = store.read_table("nfl_rosters_weekly", "raw").unique(KEY).select(*KEY, "age")
    rows = rows.join(roster, on=KEY, how="left")
    rows = rows.join(played, on=KEY, how="left").with_columns(
        pl.col("played_row").fill_null(0).alias("played"),
        (pl.col("season") * 18 + pl.col("week") - pl.col("when") - 1).clip(0, 40).alias("weeks_since"),
    )
    # the players the simulation projects: they played in one of their last three team games
    return rows.filter((pl.col("weeks_since") <= REGULAR_WEEKS) & pl.col("av_snap").is_not_null())


def main() -> None:
    d = build()
    train, test = d.filter(pl.col("season") <= TRAIN_END), d.filter(pl.col("season") > TRAIN_END)
    print(f"depth-chart player-weeks: train {train.height}, test {test.height}; played share {float(test['played'].mean()):.3f}")

    # the status table: mean played by report status, practice and position, shrunk to the status
    table = train.group_by(STATUS_KEYS).agg(pl.col("played").mean().alias("p"), pl.len().alias("n"))
    parent = train.group_by("status").agg(pl.col("played").mean().alias("p_status"))
    prior = float(train["played"].mean())
    table_pred = (
        test.join(table, on=STATUS_KEYS, how="left")
        .join(parent, on="status", how="left")
        .with_columns(pl.coalesce("p", "p_status", pl.lit(prior)).alias("pred"))["pred"]
        .to_numpy()
    )
    y = test["played"].to_numpy()

    feats = ["depth_rank", "av_snap", "weeks_since", "age"]
    cats = ["status", "practice", "position"]

    def matrix(frame: pl.DataFrame) -> np.ndarray:
        dummies = []
        for c in cats:
            for v in sorted(train[c].unique().to_list()):
                dummies.append((frame[c] == v).cast(pl.Float64).to_numpy())
        return np.column_stack([frame[f].cast(pl.Float64).to_numpy() for f in feats] + dummies)

    model = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=80, l2_regularization=5.0, random_state=0
    )
    model.fit(matrix(train), train["played"].to_numpy())
    gbm_pred = np.clip(model.predict_proba(matrix(test))[:, 1], 1e-4, 1 - 1e-4)
    table_pred = np.clip(table_pred, 1e-4, 1 - 1e-4)

    def line(name: str, pred: np.ndarray, mask: np.ndarray) -> dict:
        return {
            "model": name,
            "n": int(mask.sum()),
            "brier": round(float(brier_score_loss(y[mask], pred[mask])), 5),
            "log_loss": round(float(log_loss(y[mask], pred[mask])), 5),
        }

    everyone = np.ones(len(y), bool)
    flagged = (test["status"].to_numpy() != "none")
    rows = []
    for label, mask in (("all listed", everyone), ("report-listed", flagged), ("no report entry", ~flagged)):
        for name, pred in (("status table", table_pred), ("classifier", gbm_pred)):
            rows.append({"group": label, **line(name, pred, mask)})
    with pl.Config(tbl_rows=12, tbl_width_chars=140):
        print(pl.DataFrame(rows))
    questionable = (test["status"].to_numpy() == "Questionable")
    print(
        "Questionable only (n=%d): Brier status table %.5f, classifier %.5f"
        % (questionable.sum(), brier_score_loss(y[questionable], table_pred[questionable]), brier_score_loss(y[questionable], gbm_pred[questionable]))
    )


if __name__ == "__main__":
    main()
