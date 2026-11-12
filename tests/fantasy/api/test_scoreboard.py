"""The scoreboard: every matchup of a week from one joint draw."""

from dataclasses import replace
from pathlib import Path

import polars as pl
import pytest
from store_fixture import engine_store
from test_data_api_characterization import NOW

from fantasy import _engine, _scoreboard, data_api

SIMS = 4000


def _rows(path: Path, week: int = 0, team: int | None = None) -> list[dict]:
    return data_api.scoreboard("t", week, SIMS, data_dir=path, team=team).to_dicts()


def test_every_matchup_comes_back_once_with_win_probabilities_that_sum_to_one(
    tmp_path: Path,
) -> None:
    engine_store(tmp_path)
    rows = _rows(tmp_path)
    assert sorted(r["matchup_id"] for r in rows) == [1, 2, 3]
    assert all(r["a_win_prob"] + r["b_win_prob"] == pytest.approx(1.0) for r in rows)
    assert all(r["a_floor"] <= r["a_median"] <= r["a_ceiling"] for r in rows)


def test_my_matchup_comes_first_and_is_marked(tmp_path: Path) -> None:
    engine_store(tmp_path)
    rows = _rows(tmp_path)
    assert [r["a_is_me"] or r["b_is_me"] for r in rows] == [True, False, False]
    assert (rows[0]["a_team_name"], rows[0]["b_team_name"]) == ("Mine", "Theirs")


def test_the_viewed_team_is_the_marked_one(tmp_path: Path) -> None:
    engine_store(tmp_path)
    rows = _rows(tmp_path, team=5)
    assert rows[0]["matchup_id"] == 3
    assert rows[0]["a_is_me"] is True
    assert rows[1]["a_is_me"] is False


def test_my_win_probability_agrees_with_the_lineup_page(tmp_path: Path) -> None:
    engine_store(tmp_path)
    best = data_api.win_probability("t", n_sims=SIMS, now=NOW, data_dir=tmp_path).filter(
        pl.col("option") == "max_points"
    )
    assert _rows(tmp_path)[0]["a_win_prob"] == pytest.approx(best["win_prob"][0], abs=0.06)


def test_a_past_week_shows_final_scores_and_no_probability(tmp_path: Path) -> None:
    engine_store(tmp_path)
    row = _rows(tmp_path, 1)[0]
    assert (row["status"], row["a_points"], row["b_points"]) == ("Final", 100.0, 90.0)
    assert (row["a_projected"], row["a_win_prob"], row["a_share_left"]) == (100.0, None, 0.0)


def test_live_points_and_share_left_set_the_status(tmp_path: Path) -> None:
    engine_store(tmp_path)
    data, mine = _engine._league("t", data_dir=tmp_path)
    live = replace(data, live={"G_QB": (12.0, 0.0), "G_WR": (3.0, 0.5)})
    row = _scoreboard.scoreboard_of(live, mine, 0, SIMS, data_dir=tmp_path).to_dicts()[0]
    assert row["status"] == "Live"
    assert 0.0 < row["a_share_left"] < 1.0
    assert row["b_share_left"] == 1.0


def test_a_week_with_no_game_started_is_not_started(tmp_path: Path) -> None:
    engine_store(tmp_path)
    assert {r["status"] for r in _rows(tmp_path)} == {"Not started"}


def test_a_later_week_is_projected_and_a_placeholder_playoff_week_is_empty(tmp_path: Path) -> None:
    engine_store(tmp_path)
    data, mine = _engine._league("t", data_dir=tmp_path)
    ahead = replace(data, current_week=2)
    row = _scoreboard.scoreboard_of(ahead, mine, 3, SIMS, data_dir=tmp_path).to_dicts()[0]
    assert (row["status"], row["a_points"]) == ("Not started", 0.0)
    assert 0.0 < row["a_win_prob"] < 1.0
    playoffs = replace(ahead, playoff_start=3)
    assert _scoreboard.scoreboard_of(playoffs, mine, 3, SIMS, data_dir=tmp_path).is_empty()


def test_a_week_with_no_pairings_is_empty(tmp_path: Path) -> None:
    engine_store(tmp_path)
    assert data_api.scoreboard("t", 9, SIMS, data_dir=tmp_path).is_empty()


def test_an_unset_lineup_keeps_a_final_player_whose_projection_is_gone(tmp_path: Path) -> None:
    engine_store(tmp_path)
    data, mine = _engine._league("t", data_dir=tmp_path)
    gone = data.projections.filter(pl.col("gsis_id") != "G_OPP")
    live = replace(data, projections=gone, live={"G_OPP": (500.0, 0.0)})
    row = _scoreboard.scoreboard_of(live, mine, 0, SIMS, data_dir=tmp_path).to_dicts()[0]
    assert row["b_projected"] >= 500.0
