import numpy as np
import polars as pl
import pytest

from fantasy import store
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


def test_rows_without_a_stat_line_are_projected_but_never_trained_on(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(learn, "design", lambda frame, lines: frame.select("x").to_numpy())
    monkeypatch.setattr(learn, "fit_predict", lambda xt, yt, xs: np.full(len(xs), float(len(yt))))
    history = pl.DataFrame(
        {"season": [2019, 2020, 2021, 2021], "x": [1.0] * 4, "points": [5.0] * 4}
    )
    extra = pl.DataFrame({"season": [2021], "x": [0.0]})
    out = learn.walk_forward(history, extra=extra)
    assert out.height == 5
    later = out.filter(pl.col("season") == 2021)
    assert later["projection"].to_list() == [2.0, 2.0, 2.0]  # trained on the two earlier rows
    assert later["points"].null_count() == 1


def test_a_stat_less_game_takes_its_team_weeks_context_and_is_not_reported(capsys) -> None:  # type: ignore[no-untyped-def]
    keys = {"league_id": ["L"] * 3, "season": [2025] * 3, "week": [5] * 3}
    rows = pl.DataFrame(keys | {"gsis_id": ["A", "B", "C"], "team": ["KC", "KC", "SF"]})
    baseline = pl.DataFrame(
        {
            "league_id": ["L"],
            "gsis_id": ["A"],
            "season": [2025],
            "week": [5],
            "team": ["KC"],
            "context": [1.05],
        }
    )
    statless = pl.DataFrame(
        {"league_id": ["L", "L"], "gsis_id": ["B", "C"], "season": [2025] * 2, "week": [5, 5]}
    )
    out = learn.with_context(rows, baseline, statless).sort("gsis_id")
    assert out["context"].to_list() == [1.05, 1.05, 1.0]  # SF's team-week has no baseline row
    assert "no proj_baseline row" not in capsys.readouterr().out
    learn.with_context(rows, baseline, None)
    assert "2 projection rows have no proj_baseline row" in capsys.readouterr().out


def test_a_team_weeks_context_is_the_mean_and_rows_without_one_are_counted(capsys) -> None:  # type: ignore[no-untyped-def]
    rows = pl.DataFrame(
        {
            "league_id": ["L"] * 2,
            "gsis_id": ["B", "C"],
            "season": [2025] * 2,
            "week": [5] * 2,
            "team": ["KC", "SF"],
        }
    )
    baseline = pl.DataFrame(
        {
            "league_id": ["L"] * 2,
            "gsis_id": ["A", "D"],
            "season": [2025] * 2,
            "week": [5] * 2,
            "team": ["KC", "KC"],
            "context": [1.0, 1.1],
        }
    )
    out = learn.with_context(rows, baseline, rows.drop("team")).sort("gsis_id")
    assert out["context"].to_list() == [pytest.approx(1.05), 1.0]
    assert "1 stat-less rows have no team-week context" in capsys.readouterr().out
    assert learn.with_context(rows, baseline, None)["context"].to_list() == [1.0, 1.0]


def test_the_stat_line_branch_scales_past_and_future_rows_by_game() -> None:
    frame = pl.DataFrame(
        {"gsis_id": ["A", "A"], "season": [2025, 2026], "week": [3, 8], "projection": [10.0, 10.0]}
    )
    past, future = frame.head(1), frame.tail(1)
    chance = (
        pl.DataFrame({"gsis_id": ["A"], "season": [2025], "week": [3], "q": [0.5]}),
        pl.DataFrame({"gsis_id": ["A"], "season": [2026], "week": [8], "q": [0.9]}),
    )
    out = learn.stat_line_scaled(past, future, chance)
    assert out[0]["projection"].to_list() == [5.0] and out[1]["projection"].to_list() == [9.0]
    assert learn.stat_line_scaled(past, future, None) == (past, future)


def test_the_model_is_deterministic_and_learns_a_simple_signal() -> None:
    rng = np.random.default_rng(0)
    x = rng.uniform(0.0, 10.0, size=(3500, 3))  # points cannot be negative, so neither is y
    y = 3.0 * x[:, 0] + rng.normal(scale=0.3, size=3500)
    first = learn.fit_predict(x[:3000], y[:3000], x[3000:])
    second = learn.fit_predict(x[:3000], y[:3000], x[3000:])
    assert np.array_equal(first, second)
    assert np.corrcoef(first, y[3000:])[0, 1] > 0.9


def test_the_model_does_not_depend_on_the_order_of_the_training_rows() -> None:
    # above 10,000 rows scikit-learn's default early stopping holds out a split that the row
    # order decides, so a refit on the same rows in another order gave another model
    rng = np.random.default_rng(1)
    x = rng.uniform(0.0, 10.0, size=(12_500, 3))
    y = 3.0 * x[:, 0] + rng.normal(scale=3.0, size=12_500)
    order = rng.permutation(12_000)
    first = learn.fit_predict(x[:12_000], y[:12_000], x[12_000:])
    reordered = learn.fit_predict(x[order], y[order], x[12_000:])
    np.testing.assert_allclose(first, reordered, atol=1e-9)


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


def test_lagged_stats_use_only_games_before_the_target_game() -> None:
    table = pl.DataFrame(
        {
            "team": ["KC", "KC", "KC"],
            "season": [2025, 2025, 2025],
            "week": [1, 2, 3],
            "plays": [60.0, 70.0, 100.0],
        }
    )
    target = pl.DataFrame({"team": ["KC", "KC"], "season": [2025, 2025], "week": [3, 4]})
    out = learn.lag_asof(target, table, "team", ["plays"], "pace").sort("week")
    assert 60.0 < out["pace_plays"][0] < 70.0  # week 3 sees weeks 1 and 2, not its own 100
    assert 70.0 < out["pace_plays"][1] < 100.0  # week 4 now includes week 3


def test_a_static_attribute_comes_from_the_latest_row_up_to_the_target_week() -> None:
    table = pl.DataFrame(
        {
            "gsis_id": ["A", "A"],
            "season": [2025, 2025],
            "week": [1, 6],
            "age": [24.0, 25.0],
        }
    )
    target = pl.DataFrame({"gsis_id": ["A", "A", "A"], "season": [2025] * 3, "week": [3, 6, 9]})
    out = learn.latest_asof(target, table, "gsis_id", ["age"]).sort("week")
    assert out["age"].to_list() == [24.0, 25.0, 25.0]  # a future week keeps the last known value


def test_a_column_that_is_empty_or_constant_in_training_does_not_break_the_fit() -> None:
    rng = np.random.default_rng(1)
    x = rng.uniform(0.0, 10.0, size=(3000, 3))
    x[:, 1] = np.nan  # a feature with no data in this fold
    x[:, 2] = 7.0  # and one that never varies
    y = 2.0 * x[:, 0] + rng.normal(scale=0.3, size=3000)
    pred = learn.fit_predict(x[:2500], y[:2500], x[2500:])
    assert np.corrcoef(pred, y[2500:])[0, 1] > 0.9


def test_a_forecast_made_further_ahead_cannot_see_games_after_its_origin() -> None:
    table = pl.DataFrame(
        {
            "team": ["KC"] * 4,
            "season": [2025] * 4,
            "week": [1, 2, 3, 4],
            "plays": [60.0, 70.0, 100.0, 10.0],
        }
    )
    target = pl.DataFrame({"team": ["KC"], "season": [2025], "week": [5]})
    ahead = learn.lag_asof(target, table, "team", ["plays"], "pace", shift=2)
    assert 60.0 < ahead["pace_plays"].item() < 70.0  # weeks 1 and 2 only, as at the origin
    now = learn.lag_asof(target, table, "team", ["plays"], "pace")
    assert now["pace_plays"].item() < 60.0  # one game ahead sees week 4's 10 as well


def test_the_weekly_snapshot_keeps_only_the_next_game_with_both_projections() -> None:
    final = pl.DataFrame(
        {
            "league_id": ["L"] * 3,
            "gsis_id": ["A", "A", "A"],
            "season": [2026] * 3,
            "week": [6, 7, 8],
            "is_future": [False, True, True],
            "projection": [9.0, 11.0, 12.0],
        }
    )
    baseline = final.with_columns((pl.col("projection") - 1.0).alias("projection"))
    out = learn.snapshot_frame(final, baseline, "2026-10-23T12:00:00+00:00", current_week=7)
    assert out.to_dicts() == [
        {
            "league_id": "L",
            "gsis_id": "A",
            "season": 2026,
            "week": 7,
            "fetched_at": "2026-10-23T12:00:00+00:00",
            "learned": 11.0,
            "baseline": 10.0,
        }
    ]


def test_a_lagged_join_across_a_season_boundary_does_not_see_the_current_season() -> None:
    table = pl.DataFrame(
        {
            "team": ["KC"] * 4,
            "season": [2024, 2024, 2025, 2025],
            "week": [17, 18, 1, 2],
            "plays": [60.0, 62.0, 100.0, 100.0],
        }
    )
    target = pl.DataFrame({"team": ["KC"], "season": [2025], "week": [3]})
    ahead = learn.lag_asof(target, table, "team", ["plays"], "pace", shift=4)  # horizon 5
    assert ahead["pace_plays"].item() < 63.0  # only 2024's games, none of 2025's 100s


def test_next_game_nulls_warn_then_fail_against_the_history_share(capsys) -> None:  # type: ignore[no-untyped-def]
    cols = [*learn.DEPTH_COLUMNS, *learn.ECR_COLUMNS]
    history = pl.DataFrame({c: [1.0] * 10 for c in cols})
    future = pl.DataFrame({"week": [7] * 10, **{c: [1.0] * 8 + [None, None] for c in cols}})
    learn.check_next_game_nulls(history, future)  # 20% more nulls: a warning
    assert "WARNING" in capsys.readouterr().out
    broken = pl.DataFrame(
        {"week": [7] * 10, **{c: [None] * 10 for c in cols}},
        schema={"week": pl.Int64, **{c: pl.Float64 for c in cols}},
    )
    with pytest.raises(ValueError, match="missing"):
        learn.check_next_game_nulls(history, broken)


def test_a_played_or_started_game_is_never_archived() -> None:
    final = pl.DataFrame(
        {"season": [2026] * 3, "week": [7] * 3, "team": ["A", "B", "C"], "projection": [1.0] * 3}
    )
    games = pl.DataFrame(
        {
            "season": [2026] * 3,
            "week": [7] * 3,
            "team": ["A", "B", "C"],
            "points_for": [None, 21, None],
            "gameday": ["2026-10-25", "2026-10-22", "2026-10-20"],
        },
        schema_overrides={"points_for": pl.Int64},
    )
    out = learn.unplayed(final, games, "2026-10-23")
    assert out["team"].to_list() == ["A"]


def _empty(name: str) -> pl.DataFrame:
    return pl.DataFrame(schema=store.SCHEMAS[name])


def test_vacancy_comes_from_the_games_report_one_game_ahead_and_nobody_further_ahead() -> None:
    report = pl.DataFrame(
        [("B", 2025, 5, "KC", "WR", "Out", "DNP")],
        schema={"gsis_id": pl.String, "season": pl.Int64, "week": pl.Int64, "team": pl.String,
                "position": pl.String, "status": pl.String, "practice": pl.String},
        orient="row",
    )  # fmt: skip
    usage = pl.DataFrame(
        {"gsis_id": ["B"], "season": [2025], "week": [4], "tgt": [0.3], "car": [0.0], "snap": [0.9]}
    )
    extras = learn.Extras(
        roster=_empty("nfl_rosters_weekly"),
        depth=_empty("nfl_depth"),
        ecr=_empty("nfl_ecr"),
        pace=_empty("nfl_team_pace"),
        advanced=_empty("nfl_advanced"),
        report=report,
        usage=usage,
        sit_weights={None: 0.4},
    )
    schedule = pl.DataFrame(
        {"season": [2025], "week": [5], "team": ["KC"], "rest": [7], "roof": ["outdoors"]}
    )
    target = targets("A", [5])
    now = learn.attach_extras(target, extras, schedule, horizon=1)
    ahead = learn.attach_extras(target, extras, schedule, horizon=2)
    assert now["vac_out_tgt"].item() == pytest.approx(0.3)
    assert ahead["vac_out_tgt"].item() == 0.0  # the week 5 report does not exist two weeks before
