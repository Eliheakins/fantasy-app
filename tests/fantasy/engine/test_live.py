from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

import polars as pl
import pytest

from fantasy import store
from fantasy.sim.availability import GAME_MINUTES, kickoffs, remaining_share
from fantasy.stages import sync_sleeper
from fantasy.stages.simulate import current_state

KICKOFF = datetime(2026, 10, 25, 17, 0, tzinfo=UTC)


def test_remaining_share_before_during_and_after_a_game() -> None:
    assert remaining_share(KICKOFF, KICKOFF - timedelta(minutes=1)) == 1.0
    assert remaining_share(None, KICKOFF) == 1.0
    assert remaining_share(KICKOFF, KICKOFF + timedelta(minutes=GAME_MINUTES / 2)) == 0.5
    assert remaining_share(KICKOFF, KICKOFF + timedelta(minutes=GAME_MINUTES + 30)) == 0.0


def test_kickoffs_are_us_eastern_and_cover_both_teams() -> None:
    schedules = pl.DataFrame(
        {
            "season": [2026],
            "week": [7],
            "gameday": ["2026-10-25"],
            "gametime": ["13:00"],
            "away_team": ["AAA"],
            "home_team": ["BBB"],
        }
    )
    got = kickoffs(schedules, 2026, 7)
    assert got["AAA"] == got["BBB"]
    assert got["AAA"].astimezone(UTC).hour == 17  # 13:00 Eastern daylight time


def _rows() -> pl.DataFrame:
    def row(sid: str, pos: str, points: float | None) -> dict:
        return {
            "roster_id": 1,
            "is_starter": True,
            "sleeper_id": sid,
            "gsis_id": sid,
            "position": pos,
            "points": points,
        }

    return pl.DataFrame(
        [
            row("done", "WR", -2.0),  # game over with a negative score
            row("live", "RB", 6.0),  # game half over
            row("later", "TE", 0.0),  # not started
            row("kick", "K", 3.0),  # kicker, game over
            row("dst", "DEF", 0.0),  # defense, not started
        ]
    )


def test_current_state_counts_partial_games_and_negative_scores() -> None:
    clock = {"done": 0.0, "live": 0.5, "later": 1.0, "kick": 0.0, "dst": 1.0}
    proj = {"done": 12.0, "live": 14.0, "later": 8.0}
    pool = {"done": "WR", "live": "RB", "later": "TE"}
    state = current_state(_rows(), proj, pool, clock)[1]
    assert state.realized == pytest.approx(-2.0 + 6.0 + 3.0)  # everyone whose game has started
    assert {p.id: p.value for p in state.open_players} == {"live": 7.0, "later": 8.0}
    assert state.open_k == 0.0 and state.open_def == 1.0
    assert state.kd_actual == 3.0
    assert state.locked_starters == {"done", "live", "kick"}


def test_current_state_without_a_clock_treats_scoring_as_started() -> None:
    state = current_state(_rows(), {"later": 8.0}, {"later": "TE"})[1]
    assert {p.id for p in state.open_players} == {"later"}


def test_sync_week_replaces_only_that_weeks_rows(tmp_path: Path) -> None:
    leagues = {c: None for c in store.SCHEMAS["leagues"]} | {"league_key": "a", "league_id": "L1"}
    store.write_table(
        "leagues", pl.DataFrame([leagues], schema=store.SCHEMAS["leagues"]), "raw", tmp_path
    )
    old_m = pl.DataFrame(
        [("L1", 6, 1, 1, 90.0), ("L1", 7, 1, 1, 10.0)],
        schema=store.SCHEMAS["matchups"],
        orient="row",
    )
    old_p = pl.DataFrame(
        [("L1", 6, 1, "p", 5.0, False), ("L1", 7, 1, "p", 1.0, False)],
        schema=store.SCHEMAS["matchup_players"],
        orient="row",
    )
    store.write_table("matchups", old_m, "raw", tmp_path)
    store.write_table("matchup_players", old_p, "raw", tmp_path)
    live = [
        {
            "roster_id": 1,
            "matchup_id": 1,
            "points": 33.0,
            "starters": ["p"],
            "players": ["p"],
            "players_points": {"p": 9.0},
        }
    ]
    with mock.patch.object(sync_sleeper, "fetch", return_value=live):
        sync_sleeper.sync_week(7, tmp_path)
    m = store.read_table("matchups", "raw", tmp_path).sort("week")
    p = store.read_table("matchup_players", "raw", tmp_path).sort("week")
    assert m["points"].to_list() == [90.0, 33.0]
    assert p["points"].to_list() == [5.0, 9.0]


def test_missing_kickoffs_names_teams_with_a_game_but_no_time() -> None:
    import polars as pl

    from fantasy.sim.availability import missing_kickoffs

    schedule = pl.DataFrame(
        [(2026, 7, None, "13:00", "A", "B"), (2026, 7, "2026-10-25", "13:00", "C", "D")],
        schema=["season", "week", "gameday", "gametime", "away_team", "home_team"],
        orient="row",
    )
    assert missing_kickoffs(schedule, 2026, 7) == {"A", "B"}
