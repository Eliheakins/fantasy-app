import numpy as np
import polars as pl
import pytest

from fantasy.sim.injuries import InjuryModel, injury_projections
from fantasy.stages import availability as a


def frame(**columns: list) -> pl.DataFrame:
    base = {
        "depth_rank": [1.0],
        "av_snap": [70.0],
        "weeks_since": [0],
        "age": [25.0],
        "status": ["none"],
        "practice": ["full"],
        "position": ["WR"],
    }
    return pl.DataFrame({**base, **columns})


def test_the_design_matrix_has_the_same_columns_whatever_categories_a_frame_holds() -> None:
    one = a.design(frame())
    other = a.design(
        frame(
            status=["Out", "Doubtful"],
            position=["QB", "TE"],
            depth_rank=[1.0, 2.0],
            av_snap=[1.0, 2.0],
            weeks_since=[1, 2],
            age=[1.0, 2.0],
            practice=["dnp", "limited"],
        )
    )
    assert one.shape[1] == other.shape[1]
    assert np.isfinite(one[:, 4:]).all()  # the category columns are always 0 or 1


def test_an_unknown_category_is_all_zeros_not_an_error() -> None:
    row = a.design(frame(status=["Suspended"]))
    status_columns = row[:, len(a.NUMERIC) : len(a.NUMERIC) + len(a.STATUSES)]
    assert status_columns.sum() == 0


def test_a_flagged_players_first_game_chance_can_be_replaced() -> None:
    effects = pl.DataFrame(
        {
            "status": ["Questionable"],
            "practice": ["any"],
            "body": ["any"],
            "n": [100],
            "p0": [0.7],
            "p1": [0.9],
            "p2": [0.95],
            "p3": [1.0],
            "perf": [1.0],
        }
    )
    projections = pl.DataFrame(
        {"gsis_id": ["A", "A", "B", "B"], "week": [7, 8, 7, 8], "projection": [10.0] * 4}
    )
    flagged = {"A": ("Questionable", None, None)}
    base = injury_projections(projections, flagged, InjuryModel(effects), 7)
    over = injury_projections(
        projections, flagged, InjuryModel(effects), 7, first_game_chance={"A": 0.4}
    )

    def chance(frame: pl.DataFrame, player: str, week: int) -> float:
        rows = frame.filter((pl.col("gsis_id") == player) & (pl.col("week") == week))
        return float(rows["play_prob"].item())

    assert chance(base, "A", 7) == pytest.approx(0.7)
    assert chance(over, "A", 7) == pytest.approx(0.4)  # replaced
    assert chance(over, "A", 8) == pytest.approx(0.9)  # the later games keep the table's curve
    assert chance(over, "B", 7) == 1.0  # an unflagged player is untouched


def test_no_rows_to_predict_gives_no_predictions_not_an_error() -> None:
    rng = np.random.default_rng(0)
    x = rng.uniform(0.0, 10.0, size=(400, 3))
    y = (x[:, 0] > 5).astype(int)
    assert a.fit_predict(x, y, np.empty((0, 3))).shape == (0,)
