import numpy as np
import polars as pl
import pytest

from fantasy.stages import streaming_model as sm


def _rows(points: list[float], unit: str = "A", start_week: int = 1) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "unit": [unit] * len(points),
            "season": [2024] * len(points),
            "week": list(range(start_week, start_week + len(points))),
            "points": points,
        }
    )


def test_trailing_form_excludes_the_game_itself_and_everything_after_it() -> None:
    base = sm.trailing(_rows([4.0, 6.0, 8.0, 10.0]), "unit", ["points"])["points_tr"].to_list()
    changed = sm.trailing(_rows([4.0, 6.0, 99.0, -50.0]), "unit", ["points"])["points_tr"].to_list()

    np.testing.assert_array_equal(base[:3], changed[:3])  # rows 0 to 2 see only earlier games
    assert base[3] != changed[3]


def test_trailing_form_of_a_new_unit_is_the_mean_of_earlier_rows() -> None:
    other = _rows([10.0, 10.0], unit="B")
    first = _rows([2.0], unit="A", start_week=3)

    out = sm.trailing(pl.concat([other, first]), "unit", ["points"])

    assert out.filter(pl.col("unit") == "A")["points_tr"][0] == pytest.approx(10.0)


def test_rows_of_the_same_week_do_not_see_each_other() -> None:
    both = pl.concat([_rows([5.0], unit="A"), _rows([50.0], unit="B")])

    out = sm.trailing(both, "unit", ["points"])

    assert out["points_tr"].is_nan().all() or out["points_tr"].is_null().all()


def test_a_game_with_no_values_does_not_age_the_units_form() -> None:
    played = _rows([8.0, 8.0, 20.0])
    ahead = _rows([float("nan")] * 3, start_week=4)

    out = sm.trailing(pl.concat([played, ahead]), "unit", ["points"])["points_tr"].to_list()

    # one state for all weeks ahead
    assert out[3] == pytest.approx(out[4]) == pytest.approx(out[5])


def test_ridge_recovers_a_linear_relationship_with_an_unpenalized_intercept() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(size=(500, 2))
    y = 12.0 + 3.0 * x[:, 0] - 1.0 * x[:, 1]

    out = sm.ridge_predict(x, y, np.array([[0.0, 0.0], [1.0, 0.0]]))

    assert out[0] == pytest.approx(12.0, abs=0.1)
    assert out[1] == pytest.approx(15.0, abs=0.2)


def _history(n: int, season: int = 2023) -> pl.DataFrame:
    rng = np.random.default_rng(2)
    form = rng.normal(8, 2, n)
    implied = rng.uniform(15, 30, n)
    return pl.DataFrame(
        {
            "unit": ["A"] * n,
            "season": [season] * n,
            "week": [i % 17 + 1 for i in range(n)],
            "form": form,
            "implied": implied,
            "points": 0.5 * form - 0.2 * implied + 6 + rng.normal(0, 0.1, n),
        }
    )


def test_project_predicts_from_the_features_and_none_when_history_is_too_short() -> None:
    upcoming = pl.DataFrame({"form": [8.0], "implied": [20.0]})

    out = sm.project(_history(sm.MIN_FIT_ROWS + 50), upcoming, ["form", "implied"])
    short = sm.project(_history(sm.MIN_FIT_ROWS - 1), upcoming, ["form", "implied"])

    assert out is not None and out["projection"][0] == pytest.approx(6.0, abs=0.2)
    assert short is None


def test_a_missing_feature_in_an_upcoming_row_falls_back_to_the_history_mean() -> None:
    history = _history(sm.MIN_FIT_ROWS + 50)
    form, implied = history["form"].mean(), history["implied"].mean()
    full = pl.DataFrame({"form": [form], "implied": [implied]})
    gap = pl.DataFrame({"form": [form], "implied": [None]}, schema=full.schema)

    a = sm.project(history, full, ["form", "implied"])
    b = sm.project(history, gap, ["form", "implied"])

    assert a is not None and b is not None
    assert b["projection"][0] == pytest.approx(a["projection"][0], abs=1e-6)


def test_backtest_scores_a_week_with_a_fit_on_earlier_games_only() -> None:
    fit_rows = _history(sm.MIN_FIT_ROWS + 50, season=2023)
    scored = _history(5, season=2024).with_columns(week=pl.Series([1, 1, 1, 1, 1]))
    features = ["form", "implied"]

    model, mean = sm.backtest_rmse(pl.concat([fit_rows, scored]), features, scored_from=2024)

    expected = sm.project(fit_rows, scored, features)  # the same-week rows are not in the fit
    assert expected is not None
    errors = scored["points"].to_numpy() - expected["projection"].to_numpy()
    assert model == pytest.approx(float(np.sqrt(np.mean(errors**2))))
    assert mean > 0


def _kicks(weeks: list[int]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "player_id": ["K1"] * len(weeks),
            "position": ["K"] * len(weeks),
            "season": [2024] * len(weeks),
            "week": weeks,
            "fg_att": [2] * len(weeks),
            "pat_att": [3] * len(weeks),
            "fg_made_40_49": [1] * len(weeks),
            "fg_made_50_59": [0] * len(weeks),
            "fg_made_60_": [0] * len(weeks),
            "fg_missed_40_49": [0] * len(weeks),
            "fg_missed_50_59": [0] * len(weeks),
            "fg_missed_60_": [0] * len(weeks),
        }
    )


def test_a_kicker_game_that_is_both_played_and_ahead_gets_one_row_with_pre_game_features() -> None:
    ahead = pl.DataFrame({"gsis_id": ["K1", "K1"], "season": [2024, 2024], "week": [3, 4]})

    out = sm.kicker_trailing(_kicks([1, 2, 3]), ahead)

    assert out.select("gsis_id", "season", "week").is_duplicated().sum() == 0
    assert sorted(out["week"].to_list()) == [1, 2, 3, 4]
    week3 = out.filter(pl.col("week") == 3)["fg_att_tr"][0]
    week4 = out.filter(pl.col("week") == 4)["fg_att_tr"][0]
    assert week3 == pytest.approx(2.0) and week4 == pytest.approx(2.0)  # constant 2 attempts
