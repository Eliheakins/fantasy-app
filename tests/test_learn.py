import numpy as np
import polars as pl
import pytest

from fantasy.stages import learn

GAME_SCHEMA = {
    "league_id": pl.String,
    "gsis_id": pl.String,
    "season": pl.Int64,
    "week": pl.Int64,
    "position": pl.String,
    "team": pl.String,
    "exp_pts": pl.Float64,
    "points": pl.Float64,
    "tgt": pl.Float64,
    "car": pl.Float64,
    "att": pl.Float64,
    "snap": pl.Float64,
    "tshare": pl.Float64,
    "rec_td_exp": pl.Float64,
    "rush_td_exp": pl.Float64,
}


def games(points: list[float], player: str = "A", season: int = 2025) -> pl.DataFrame:
    rows = [
        ("L", player, season, w, "WR", "KC", p * 0.8, p, 6.0, 0.0, 0.0, 70.0, 0.2, 0.3, 0.0)
        for w, p in enumerate(points, start=1)
    ]
    return pl.DataFrame(rows, schema=GAME_SCHEMA, orient="row")


def targets(player: str, weeks: list[int], season: int = 2025) -> pl.DataFrame:
    rows = [("L", player, season, w, "WR", "KC") for w in weeks]
    return pl.DataFrame(
        rows,
        schema={
            "league_id": pl.String,
            "gsis_id": pl.String,
            "season": pl.Int64,
            "week": pl.Int64,
            "position": pl.String,
            "team": pl.String,
        },
        orient="row",
    )


def test_a_target_games_features_ignore_that_game_and_later_ones() -> None:
    a = games([10.0, 12.0, 8.0, 30.0, 2.0])
    b = games([10.0, 12.0, 8.0, 99.0, 77.0])  # weeks 4 and 5 differ
    feats_a = learn.feature_frame(targets("A", [4]), learn.state_frame(a))
    feats_b = learn.feature_frame(targets("A", [4]), learn.state_frame(b))
    assert feats_a.select(learn.STATE_FEATURES).equals(feats_b.select(learn.STATE_FEATURES))


def test_a_later_horizon_uses_the_state_from_further_back() -> None:
    state = learn.state_frame(games([10.0, 12.0, 8.0, 14.0]))
    now = learn.feature_frame(targets("A", [5]), state, horizon=1)
    later = learn.feature_frame(targets("A", [5]), state, horizon=3)
    assert now["as_of_week"].item() == 4
    assert later["as_of_week"].item() == 2
    assert now["n_games"].item() == 4 and later["n_games"].item() == 2


def test_the_same_state_gives_the_same_features_for_a_past_and_a_future_row() -> None:
    state = learn.state_frame(games([10.0, 12.0, 8.0]))
    past = learn.feature_frame(targets("A", [3]), learn.state_frame(games([10.0, 12.0])))
    future = learn.feature_frame(targets("A", [3]), state.filter(pl.col("as_of_week") <= 2))
    assert past.select(learn.STATE_FEATURES).equals(future.select(learn.STATE_FEATURES))


def test_a_player_with_no_earlier_game_has_empty_features_and_no_history() -> None:
    state = learn.state_frame(games([10.0, 12.0], player="A"))
    out = learn.feature_frame(targets("NEW", [3]), state)
    assert not out["has_history"].item()
    assert out["points_hl4"].item() is None


def test_the_first_games_of_a_season_use_the_previous_seasons_form() -> None:
    state = learn.state_frame(
        pl.concat([games([20.0, 20.0], season=2024), games([5.0], season=2025)])
    )
    out = learn.feature_frame(targets("A", [1], season=2025), state)
    assert out["as_of_season"].item() == 2024 and out["points_last"].item() == pytest.approx(20.0)


def test_each_season_is_scored_by_a_model_that_never_saw_it() -> None:
    assert learn.train_seasons(2024, [2019, 2020, 2021, 2022, 2023, 2024]) == [
        2019,
        2020,
        2021,
        2022,
        2023,
    ]
    assert learn.train_seasons(2021, [2019, 2020, 2021]) == [2019, 2020]
    # the first seasons have too few earlier ones, so they leave one season out of the early block
    assert learn.train_seasons(2019, [2019, 2020, 2021, 2022, 2023]) == [2020, 2021, 2022]
    assert learn.train_seasons(2020, [2019, 2020, 2021, 2022, 2023]) == [2019, 2021, 2022]


def test_the_model_is_deterministic_and_learns_a_simple_signal() -> None:
    rng = np.random.default_rng(0)
    x = rng.uniform(0.0, 10.0, size=(3500, 3))  # points cannot be negative, so neither is y
    y = 3.0 * x[:, 0] + rng.normal(scale=0.3, size=3500)
    first = learn.fit_predict(x[:3000], y[:3000], x[3000:])
    second = learn.fit_predict(x[:3000], y[:3000], x[3000:])
    assert np.array_equal(first, second)
    assert np.corrcoef(first, y[3000:])[0, 1] > 0.9


def test_predictions_never_go_below_zero() -> None:
    x = np.array([[0.0], [1.0], [2.0], [3.0]] * 30)
    y = np.array([0.0, 0.0, 1.0, 2.0] * 30)
    assert (learn.fit_predict(x, y, np.array([[-5.0]])) >= 0).all()


def test_a_missing_value_in_the_latest_game_keeps_the_earlier_weighted_average() -> None:
    g = games([10.0, 12.0, 8.0]).with_columns(
        pl.when(pl.col("week") == 3).then(None).otherwise(pl.col("snap")).alias("snap")
    )
    state = learn.state_frame(g)
    last = state.filter(pl.col("as_of_week") == 3)
    assert last["snap_hl4"].item() == pytest.approx(70.0)  # carried forward, not blanked
    assert last["snap_last"].item() is None  # the last value itself stays missing
