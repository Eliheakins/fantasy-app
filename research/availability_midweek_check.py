"""Which next-game chance should a designated player get before the final injury report?

The availability classifier is trained on each week's final report, where no game status means
"not designated". Before Friday the current week's report has practice rows only, so a player
Sleeper already calls Out or Doubtful reaches the classifier as status none and reads as healthy.
This scores, on designated players in held-out seasons (fit 2019 to 2023, score 2024 on):

- classifier, mid-week input: the classifier with the game status blanked, as it runs before the
  final report (practice kept at the final-day value, the closest stored stand-in for mid-week);
- injury table by status: the production table's next-game chance for the status, body part and
  no practice (what the simulation uses for a flagged player the classifier does not score);
- classifier, final report: the classifier on the real final report (the shipped comparison).

The status stands in for Sleeper's mid-week call, which is not archived far enough back to test.
The injury table is fit on every season, so it is in sample for the test years; its Out and
Doubtful cells (0.2% and 2%) barely move with the sample.

Run from the repo root after `make refresh`:
    uv run python research/availability_midweek_check.py
"""

import numpy as np
import polars as pl
from sklearn.metrics import brier_score_loss, log_loss

from fantasy import store
from fantasy.config import load_config
from fantasy.sim.injuries import InjuryModel
from fantasy.stages.availability import MAX_P, MIN_P, build_rows, design, fit_predict

TRAIN_END = 2023
DESIGNATED = ("Out", "Doubtful", "Questionable")


def table_chance(model: InjuryModel, status: str, body: str | None) -> float:
    curve = model.curve((status, body, None))
    return curve[0][0] if curve is not None else float("nan")


def main() -> None:
    current = int(store.read_table("leagues", "raw")["current_week"].max())
    rows = build_rows().filter(
        pl.col("season") * 100 + pl.col("week") < load_config().season * 100 + current
    )
    train = rows.filter(pl.col("season") <= TRAIN_END)
    test = rows.filter((pl.col("season") > TRAIN_END) & pl.col("status").is_in(DESIGNATED))
    y = test["played"].to_numpy()
    x_train, y_train = design(train), train["played"].to_numpy()

    final = fit_predict(x_train, y_train, design(test))
    blanked = test.with_columns(pl.lit("none").alias("status"))
    midweek = fit_predict(x_train, y_train, design(blanked))
    model = InjuryModel(store.read_table("injury_effects"))
    table = np.array(
        [table_chance(model, s, b) for s, b in zip(test["status"], test["body"], strict=True)]
    ).clip(MIN_P, MAX_P)

    out = []
    statuses = test["status"].to_numpy()
    for group in (*DESIGNATED, "all designated"):
        mask = np.ones(len(y), bool) if group.startswith("all") else statuses == group
        for name, pred in (
            ("classifier, mid-week input", midweek),
            ("injury table by status", table),
            ("classifier, final report", final),
        ):
            out.append(
                {
                    "status": group,
                    "n": int(mask.sum()),
                    "played": round(float(y[mask].mean()), 3),
                    "model": name,
                    "mean_pred": round(float(pred[mask].mean()), 3),
                    "brier": round(float(brier_score_loss(y[mask], pred[mask])), 4),
                    "log_loss": round(float(log_loss(y[mask], pred[mask], labels=[0, 1])), 4),
                }
            )
    with pl.Config(tbl_rows=20, tbl_width_chars=160):
        print(pl.DataFrame(out))


if __name__ == "__main__":
    main()
