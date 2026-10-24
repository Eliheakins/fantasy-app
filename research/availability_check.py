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
from fantasy.sim.injuries import InjuryModel
from fantasy.stages.availability import build_rows
from fantasy.stages.injuries import PRACTICE, body_group

TRAIN_END = 2023
FIRST_SEASON = 2019  # lagged snap features need a prior season
SKILL = ["QB", "RB", "WR", "TE"]
STATUS_KEYS = ["status", "practice", "position"]


def main() -> None:
    d = build_rows().filter(pl.col("season") * 100 + pl.col("week") <= 202618)
    train, test = d.filter(pl.col("season") <= TRAIN_END), d.filter(pl.col("season") > TRAIN_END)
    print(
        f"depth-chart player-weeks: train {train.height}, test {test.height}; played share {float(test['played'].mean()):.3f}"
    )

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
        max_iter=300,
        learning_rate=0.05,
        max_leaf_nodes=15,
        min_samples_leaf=80,
        l2_regularization=5.0,
        random_state=0,
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
    flagged = test["status"].to_numpy() != "none"
    rows = []
    for label, mask in (
        ("all listed", everyone),
        ("report-listed", flagged),
        ("no report entry", ~flagged),
    ):
        for name, pred in (("status table", table_pred), ("classifier", gbm_pred)):
            rows.append({"group": label, **line(name, pred, mask)})
    with pl.Config(tbl_rows=12, tbl_width_chars=140):
        print(pl.DataFrame(rows))
    # the production injury table (fit on every season, so in-sample for the test years) against
    # the classifier (out of sample), on the players the table covers
    model_table = InjuryModel(store.read_table("injury_effects"))
    prod = np.full(len(y), np.nan)
    for i, (status, body, raw) in enumerate(
        zip(
            test["status"].to_list(),
            test["body"].to_list(),
            test["practice_raw"].to_list(),
            strict=True,
        )
    ):
        if status in ("Out", "Doubtful", "Questionable"):
            curve = model_table.curve((status, body_group(body), PRACTICE.get(raw or "")))
            if curve is not None:
                prod[i] = curve[0][0]
    covered = np.isfinite(prod)
    prod = np.clip(prod, 1e-4, 1 - 1e-4)
    print(
        "production injury table (in sample) vs classifier (out of sample), report-listed n=%d: "
        "Brier %.5f vs %.5f, log loss %.5f vs %.5f"
        % (
            covered.sum(),
            brier_score_loss(y[covered], prod[covered]),
            brier_score_loss(y[covered], gbm_pred[covered]),
            log_loss(y[covered], prod[covered]),
            log_loss(y[covered], gbm_pred[covered]),
        )
    )
    questionable = test["status"].to_numpy() == "Questionable"
    print(
        "Questionable only (n=%d): Brier status table %.5f, classifier %.5f"
        % (
            questionable.sum(),
            brier_score_loss(y[questionable], table_pred[questionable]),
            brier_score_loss(y[questionable], gbm_pred[questionable]),
        )
    )


if __name__ == "__main__":
    main()
