from datetime import UTC, datetime

import polars as pl
import pytest

from fantasy.sim.availability import EASTERN, locked_teams, rate, scale_projections
from fantasy.sim.lineup import Player, lineup_with_locks


def test_rate_applies_game_day_status_to_the_current_week_only():
    assert rate("Out", week=7, current_week=7) == 0.0
    assert rate("Questionable", week=7, current_week=7) == 0.76
    assert rate("Questionable", week=8, current_week=7) == 1.0
    assert rate(None, week=7, current_week=7) == 1.0


def test_rate_keeps_long_term_players_out_for_four_weeks():
    assert [rate("IR", w, 7) for w in range(7, 12)] == [0.0, 0.0, 0.0, 0.0, 1.0]


def test_scale_projections_multiplies_only_flagged_players():
    frame = pl.DataFrame(
        {"gsis_id": ["a", "a", "b"], "week": [7, 8, 7], "projection": [10.0, 10.0, 10.0]}
    )
    out = scale_projections(frame, {"a": "Questionable"}, current_week=7)
    assert out["projection"].to_list() == [7.6, 10.0, 10.0]


def test_locked_teams_are_those_whose_game_has_kicked_off():
    schedules = pl.DataFrame(
        {
            "season": [2026, 2026, 2026],
            "week": [7, 7, 7],
            "gameday": ["2026-10-25", "2026-10-25", "2026-10-26"],
            "gametime": ["13:00", "20:20", "20:15"],
            "away_team": ["A", "C", "E"],
            "home_team": ["B", "D", "F"],
        }
    )
    now = datetime(2026, 10, 25, 14, 0, tzinfo=EASTERN).astimezone(UTC)
    assert locked_teams(schedules, 2026, 7, now) == {"A", "B"}


def test_lineup_with_locks_keeps_locked_starter_and_bans_locked_bench():
    players = [
        Player("qb", "QB", 20.0),
        Player("rb_locked_start", "RB", 5.0),
        Player("rb_locked_bench", "RB", 30.0),
        Player("rb_open", "RB", 8.0),
    ]
    lineup = lineup_with_locks(
        players,
        ["QB", "RB", "RB"],
        {"rb_locked_start", "rb_locked_bench"},
        {"qb", "rb_locked_start"},
    )
    assert lineup.players == {"qb", "rb_locked_start", "rb_open"}
    assert lineup.total == 33.0


def test_lineup_with_locks_matches_auto_lineup_when_nothing_is_locked():
    players = [Player("a", "RB", 9.0), Player("b", "WR", 7.0), Player("c", "WR", 6.0)]
    lineup = lineup_with_locks(players, ["RB", "WR", "FLEX"], set(), set())
    assert lineup.players == {"a", "b", "c"}


def test_an_unrecognised_status_warns_and_counts_as_healthy():
    with pytest.warns(UserWarning, match="COV"):
        assert rate("COV", week=7, current_week=7) == 1.0
