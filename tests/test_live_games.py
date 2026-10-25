"""Everything that depends on which games are under way or over during an NFL week.

`LeagueData.live` is {gsis_id: (points so far, share of game left)}: 1.0 not started, between
0 and 1 in progress, 0 final. The fixture league is in week 3; I am roster 1 and play roster 2.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from store_fixture import write_rows
from test_data_api_characterization import NOW, _engine_store
from test_simulate_load import LEAGUE, build_store

from fantasy import _engine, _lineup, data_api
from fantasy.sim import moves
from fantasy.sim.availability import (
    EASTERN,
    GAME_MINUTES,
    locked_teams,
    remaining_share,
)
from fantasy.sim.lineup import Player, lineup_slots, lineup_with_locks
from fantasy.stages import simulate as sim

KICKOFF = datetime(2026, 10, 25, 13, 0, tzinfo=EASTERN)
N_SIMS = 2000
WEEK = 3
HUGE = 1000.0  # a score no lineup of the fixture league can reach


def _with(monkeypatch: pytest.MonkeyPatch, **changes: object) -> None:
    """Replace LeagueData fields for everything `_lineup` loads."""
    from dataclasses import replace

    real = _engine._league

    def patched(league_key: str):  # type: ignore[no-untyped-def]
        data, mine = real(league_key)
        return replace(data, **changes), mine

    monkeypatch.setattr(_lineup, "_league", patched)


def _loaded(live: dict[str, tuple[float, float]]):  # type: ignore[no-untyped-def]
    from dataclasses import replace

    data, mine = _engine._league("t")
    return replace(data, live=live), mine


def _row(frame: pl.DataFrame, gsis_id: str) -> dict:
    return frame.filter(pl.col("gsis_id") == gsis_id).row(0, named=True)


def _set_starters(tmp_path: Path, rows: list[tuple[int, str]]) -> None:
    """Starters set in Sleeper for week 3: (roster id, sleeper id)."""
    write_rows(
        tmp_path,
        "matchup_players",
        [
            {"league_id": "L1", "week": WEEK, "roster_id": r, "sleeper_id": s, "is_starter": True}
            | {"points": 0.0}
            for r, s in rows
        ],
    )


def _kickoff_schedule(tmp_path: Path, kickoff: datetime) -> None:
    """KC (every fixture player's team) plays week 3 at `kickoff`."""
    eastern = kickoff.astimezone(EASTERN)
    write_rows(
        tmp_path,
        "nfl_schedules",
        [
            {
                "season": 2026,
                "week": WEEK,
                "gameday": eastern.strftime("%Y-%m-%d"),
                "gametime": eastern.strftime("%H:%M"),
                "away_team": "KC",
                "home_team": "BUF",
            }
        ],
    )


# --- (3) remaining_share ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("minutes_after_kickoff", "expected"),
    [
        (-30, 1.0),
        (0, 1.0),  # at kickoff nothing has been played
        (GAME_MINUTES / 4, 0.75),
        (GAME_MINUTES / 2, 0.5),
        (GAME_MINUTES - 1, 1 / GAME_MINUTES),
        (GAME_MINUTES, 0.0),  # exactly at game end
        (GAME_MINUTES + 1, 0.0),
        (GAME_MINUTES * 10, 0.0),  # never negative
    ],
)
def test_remaining_share_at_kickoff_mid_game_at_the_end_and_past_it(
    minutes_after_kickoff: float, expected: float
) -> None:
    now = KICKOFF + timedelta(minutes=minutes_after_kickoff)
    assert remaining_share(KICKOFF, now) == pytest.approx(expected)


def test_remaining_share_is_not_started_without_a_kickoff_time() -> None:
    assert remaining_share(None, KICKOFF + timedelta(hours=9)) == 1.0


# --- (4) locked_teams ---------------------------------------------------------------------


def _schedule(day: str, time: str) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2026],
            "week": [7],
            "gameday": [day],
            "gametime": [time],
            "away_team": ["A"],
            "home_team": ["B"],
        }
    )


def test_a_team_is_locked_at_the_second_of_kickoff_and_not_a_second_before() -> None:
    schedules = _schedule("2026-10-25", "13:00")
    one_second = timedelta(seconds=1)
    assert locked_teams(schedules, 2026, 7, KICKOFF - one_second) == set()
    assert locked_teams(schedules, 2026, 7, KICKOFF) == {"A", "B"}
    assert locked_teams(schedules, 2026, 7, KICKOFF + one_second) == {"A", "B"}


def test_a_team_stays_locked_after_its_game_is_over() -> None:
    schedules = _schedule("2026-10-25", "13:00")
    later = KICKOFF + timedelta(minutes=GAME_MINUTES + 600)
    assert locked_teams(schedules, 2026, 7, later) == {"A", "B"}


def test_locked_teams_only_sees_the_asked_for_week() -> None:
    assert locked_teams(_schedule("2026-10-25", "13:00"), 2026, 8, KICKOFF) == set()


def test_a_team_with_no_kickoff_time_is_not_locked_and_warns() -> None:
    schedules = pl.DataFrame(
        [(2026, 7, None, None, "A", "B")],
        schema=["season", "week", "gameday", "gametime", "away_team", "home_team"],
        orient="row",
    )
    with pytest.warns(UserWarning, match="no kickoff time"):
        assert locked_teams(schedules, 2026, 7, KICKOFF) == set()


# --- (5) locks in the lineup ---------------------------------------------------------------

SLOTS = ["QB", "RB", "RB"]


def test_a_locked_bench_player_is_never_moved_into_a_slot() -> None:
    players = [
        Player("qb", "QB", 20.0),
        Player("rb_locked_bench", "RB", 99.0),
        Player("rb_a", "RB", 8.0),
        Player("rb_b", "RB", 6.0),
    ]
    best = lineup_with_locks(players, SLOTS, {"rb_locked_bench"}, {"qb"})
    assert "rb_locked_bench" not in best.players
    assert best.players == {"qb", "rb_a", "rb_b"}


def test_a_locked_starter_is_never_benched_for_a_better_player() -> None:
    players = [
        Player("qb", "QB", 20.0),
        Player("rb_locked_start", "RB", 1.0),
        Player("rb_a", "RB", 8.0),
        Player("rb_b", "RB", 6.0),
    ]
    best = lineup_with_locks(players, SLOTS, {"rb_locked_start"}, {"qb", "rb_locked_start"})
    assert "rb_locked_start" in best.players
    assert best.players == {"qb", "rb_locked_start", "rb_a"}  # rb_b loses the open slot


def test_a_locked_starter_keeps_his_slot_even_when_two_locked_players_compete() -> None:
    players = [
        Player("rb_one", "RB", 5.0),
        Player("rb_two", "RB", 4.0),
        Player("rb_open", "RB", 9.0),
    ]
    best = lineup_with_locks(players, ["RB", "RB"], {"rb_one", "rb_two"}, {"rb_one", "rb_two"})
    assert best.players == {"rb_one", "rb_two"}


def test_with_every_player_locked_and_none_starting_nobody_is_slotted() -> None:
    players = [Player("qb", "QB", 20.0), Player("rb", "RB", 5.0)]
    best = lineup_with_locks(players, SLOTS, {"qb", "rb"}, set())
    assert best.players == frozenset() and best.total == 0.0


def test_the_lineup_never_slots_a_locked_bench_player_and_keeps_a_locked_starter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _kickoff_schedule(tmp_path, KICKOFF)
    # Sleeper has the 0.2-point G_DL at WR; G_WR (7.6) sits on the bench. Everyone has kicked off.
    _set_starters(tmp_path, [(1, "qb"), (1, "dl")])
    out = data_api.lineup("t", now=KICKOFF + timedelta(minutes=1))
    assert set(out.filter(pl.col("recommended"))["gsis_id"]) == {"G_QB", "G_DL"}
    assert _row(out, "G_DL")["slot"] == "WR"
    assert _row(out, "G_WR")["slot"] == "BN" and _row(out, "G_WR")["locked"]


def test_before_kickoff_nobody_is_locked_and_the_better_wr_is_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _kickoff_schedule(tmp_path, KICKOFF)
    _set_starters(tmp_path, [(1, "qb"), (1, "dl")])
    out = data_api.lineup("t", now=KICKOFF - timedelta(seconds=1))
    assert not out["locked"].any()
    assert _row(out, "G_WR")["slot"] == "WR" and _row(out, "G_DL")["slot"] == "BN"


def test_an_out_player_set_as_a_locked_starter_is_still_not_slotted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _kickoff_schedule(tmp_path, KICKOFF)
    _set_starters(tmp_path, [(1, "qb"), (1, "rb")])  # G_RB is Out in the fixture
    out = data_api.lineup("t", now=KICKOFF + timedelta(minutes=1))
    row = _row(out, "G_RB")
    assert (row["slot"], row["recommended"], row["p10"], row["p90"]) == ("BN", False, 0.0, 0.0)


def test_a_long_term_injured_player_is_never_slotted_even_with_the_top_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    data, _ = _engine._league("t")
    boosted = data.projections.with_columns(
        pl.when(pl.col("gsis_id") == "G_TE")
        .then(99.0)
        .otherwise(pl.col("projection"))
        .alias("projection")
    )
    _with(
        monkeypatch, projections=boosted, injuries={"G_TE": ("IR", "", ""), "G_WR": ("Out", "", "")}
    )
    out = data_api.lineup("t", now=NOW)
    assert not _row(out, "G_WR")["recommended"] and not _row(out, "G_TE")["recommended"]


# --- (6) a week that is not the current one ignores live data ------------------------------


def test_lineup_for_a_later_week_ignores_live_points_and_game_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    plain = data_api.lineup("t", 4, now=NOW)
    _with(monkeypatch, live={"G_QB": (25.0, 0.0), "G_WR": (6.0, 0.4)})
    live = data_api.lineup("t", 4, now=NOW)
    assert live.drop("full_name").equals(plain.drop("full_name"))
    qb = _row(live, "G_QB")
    assert (qb["projection"], qb["actual"], qb["game"]) == (10.0, 0.0, "Not started")


def test_week_values_in_a_later_week_do_not_take_final_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    data, _ = _loaded({"G_QB": (25.0, 0.0)})
    positions = moves.position_of(data)
    assert _engine._week_values(data, 4, positions)["G_QB"] == 10.0
    assert _engine._week_values(data, WEEK, positions)["G_QB"] == 25.0


def test_a_player_not_yet_started_shows_no_points_even_if_sleeper_reports_some(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _with(monkeypatch, live={"G_QB": (3.0, 1.0)})
    qb = _row(data_api.lineup("t", now=NOW), "G_QB")
    assert (qb["actual"], qb["game"]) == (0.0, "Not started")


def test_a_game_in_progress_is_labelled_with_its_share_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _with(monkeypatch, live={"G_QB": (8.0, 0.25)})
    qb = _row(data_api.lineup("t", now=NOW), "G_QB")
    assert (qb["actual"], qb["game"]) == (8.0, "Live, 25% left")


# --- (7) K and DEF live data -----------------------------------------------------------------


def test_kicker_and_defense_live_data_do_not_create_skill_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    plain = data_api.lineup("t", now=NOW)
    kd_live = {"G_K": (9.0, 0.0), "G_FREEK": (4.0, 0.5), "KC": (12.0, 0.0), "G_THEIRK": (3.0, 0.0)}
    _with(monkeypatch, live=kd_live)
    out = data_api.lineup("t", now=NOW)
    assert out.equals(plain)
    assert not {"G_K", "G_FREEK", "KC", "G_THEIRK"} & set(out["gsis_id"])


def test_week_values_ignore_final_kickers_and_defenses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    plain, _ = _loaded({})
    data, _ = _loaded({"G_K": (9.0, 0.0), "KC": (12.0, 0.0)})
    positions = moves.position_of(data)
    assert _engine._week_values(data, WEEK, positions) == _engine._week_values(
        plain, WEEK, positions
    )


def test_win_probability_is_unchanged_by_kicker_only_live_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    plain = data_api.win_probability("t", n_sims=N_SIMS, now=NOW)
    _with(monkeypatch, live={"G_K": (9.0, 0.0)})
    assert data_api.win_probability("t", n_sims=N_SIMS, now=NOW).equals(plain)


# --- (1) win probability with finished and in-progress starters ------------------------------


def _draws(live: dict[str, tuple[float, float]], ids: list[str], n: int = N_SIMS):  # type: ignore[no-untyped-def]
    data, _ = _loaded(live)
    positions = moves.position_of(data)
    values = _engine._week_values(data, WEEK, positions)
    return _engine._week_points(data, ids, positions, values, WEEK, n)


def test_a_final_starter_contributes_exactly_his_points_with_no_variance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    ids = ["G_QB", "G_WR"]
    points, column = _draws({"G_QB": (20.0, 0.0)}, ids)
    assert np.array_equal(points[:, column["G_QB"]], np.full(N_SIMS, 20.0))
    assert points[:, column["G_WR"]].std() > 0  # the player still to play keeps his spread


def test_a_final_starter_with_a_negative_score_counts_it_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    points, column = _draws({"G_QB": (-2.5, 0.0)}, ["G_QB"])
    assert np.array_equal(points[:, column["G_QB"]], np.full(N_SIMS, -2.5))


def test_a_starter_in_progress_is_his_actual_points_plus_a_scaled_remainder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    ids = ["G_QB", "G_WR"]
    # G_QB projects 10 for the whole game: half of it is left, so about 5 more on top of 6
    half, column = _draws({"G_QB": (6.0, 0.5)}, ids, n=20000)
    full, _ = _draws({}, ids, n=20000)
    remainder = half[:, column["G_QB"]] - 6.0
    whole = full[:, column["G_QB"]]
    assert remainder.std() > 0
    assert remainder.mean() == pytest.approx(0.5 * whole.mean(), rel=0.05)
    assert remainder.std() < whole.std()  # less of the game left, less uncertainty


def test_a_started_game_does_not_apply_the_chance_of_playing_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    # G_WR is Questionable (76% to play). Once his game is under way he is playing: the expected
    # remainder is half of his full-game projection (10), not half of the discounted 7.6.
    points, column = _draws({"G_WR": (2.0, 0.5)}, ["G_WR"], n=20000)
    assert (points[:, column["G_WR"]] - 2.0).mean() == pytest.approx(5.0, rel=0.1)


def test_win_probability_floor_is_at_least_a_final_starters_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _with(monkeypatch, live={"G_QB": (HUGE, 0.0)})
    out = data_api.win_probability("t", n_sims=N_SIMS, now=NOW)
    assert (out["floor"] >= HUGE).all()
    assert (out["win_prob"] == 1.0).all()  # the opponent cannot reach it


def test_win_probability_with_a_final_starter_and_one_in_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _with(monkeypatch, live={"G_QB": (20.0, 0.0), "G_WR": (6.0, 0.5)})
    out = data_api.win_probability("t", n_sims=N_SIMS, now=NOW)
    max_points = out.filter(pl.col("option") == "max_points").row(0, named=True)
    # QB is final (20 flat) and the WR has 6 banked: nothing in the lineup can fall below 26
    assert max_points["gsis_ids"] == ["G_QB", "G_WR"]
    assert max_points["floor"] >= 26.0
    assert max_points["median"] > 26.0  # the WR's remainder is still to come
    assert max_points["median"] == pytest.approx(20.0 + 6.0 + 0.5 * 10.0, abs=1.5)


def test_expected_points_of_a_lineup_with_a_player_in_progress_include_his_banked_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _with(monkeypatch, live={"G_QB": (20.0, 0.0), "G_WR": (6.0, 0.5)})
    out = data_api.win_probability("t", n_sims=N_SIMS, now=NOW)
    expected = out.filter(pl.col("option") == "max_points")["expected_points"].item()
    assert expected == pytest.approx(20.0 + 6.0 + 0.5 * 10.0, abs=1.5)


# --- (2) the opponent's finished starters -----------------------------------------------------


def test_opponent_starters_set_in_sleeper_count_when_their_game_is_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _set_starters(tmp_path, [(2, "opp")])
    data, _ = _loaded({"G_OPP": (30.0, 0.0)})
    positions = moves.position_of(data)
    values = _engine._week_values(data, WEEK, positions)
    slots = lineup_slots(data.roster_positions)
    assert _engine._opponent_lineup(data, 2, WEEK, positions, values, slots) == ["G_OPP"]
    points, column = _engine._week_points(data, ["G_OPP"], positions, values, WEEK, N_SIMS)
    assert np.array_equal(points[:, column["G_OPP"]], np.full(N_SIMS, 30.0))


def test_a_huge_final_opponent_score_makes_every_option_a_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _set_starters(tmp_path, [(2, "opp")])
    _with(monkeypatch, live={"G_OPP": (HUGE, 0.0)})
    out = data_api.win_probability("t", n_sims=N_SIMS, now=NOW)
    assert (out["win_prob"] == 0.0).all()


def test_a_final_opponent_starter_whose_projection_is_gone_still_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _set_starters(tmp_path, [(2, "opp")])
    data, _ = _loaded({"G_OPP": (HUGE, 0.0)})
    gone = data.projections.filter(pl.col("gsis_id") != "G_OPP")
    _with(monkeypatch, projections=gone, live={"G_OPP": (HUGE, 0.0)})
    out = data_api.win_probability("t", n_sims=N_SIMS, now=NOW)
    assert (out["win_prob"] == 0.0).all()


def test_with_no_starters_set_the_opponents_best_lineup_includes_his_final_player(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    data, _ = _loaded({"G_OPP": (HUGE, 0.0)})
    positions = moves.position_of(data)
    values = _engine._week_values(data, WEEK, positions)
    slots = lineup_slots(data.roster_positions)
    assert _engine._opponent_lineup(data, 2, WEEK, positions, values, slots) == ["G_OPP"]
    assert values["G_OPP"] == HUGE


def test_opponent_starters_are_ignored_for_a_week_that_is_not_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _set_starters(tmp_path, [(2, "opp")])  # week 3 starters
    data, _ = _loaded({})
    positions = moves.position_of(data)
    values = _engine._week_values(data, 4, positions)
    slots = lineup_slots(data.roster_positions)
    # nothing is set for week 4, so the best lineup is used
    assert _engine._opponent_lineup(data, 2, 4, positions, values, slots) == ["G_OPP"]


# --- _status_and_locks ------------------------------------------------------------------------


def test_status_and_locks_lock_players_whose_team_has_kicked_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _kickoff_schedule(tmp_path, KICKOFF)
    before = _engine._status_and_locks(WEEK, WEEK, KICKOFF - timedelta(seconds=1))[1]
    at = _engine._status_and_locks(WEEK, WEEK, KICKOFF)[1]
    assert before == set()
    assert {"G_QB", "G_WR", "G_OPP"} <= at


def test_status_and_locks_lock_nobody_in_another_week(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _kickoff_schedule(tmp_path, KICKOFF)
    assert _engine._status_and_locks(4, WEEK, KICKOFF + timedelta(days=1))[1] == set()


# --- _constant_points ------------------------------------------------------------------------


def test_constant_points_are_the_kicker_and_defense_scores_so_far_plus_a_draw_for_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from fantasy.sim.odds import CurrentWeek

    _engine_store(tmp_path, monkeypatch)
    data, _ = _engine._league("t")
    data = replace(data, roster_positions=["QB", "K", "DEF"], k_mean=8.0, k_var=0.0)
    data = replace(data, def_mean=6.0, def_var=0.0)
    fresh = _engine._constant_points(data, 100, 1, None)
    assert np.allclose(fresh, 14.0)  # nothing played: both slots at league average, no variance
    done = CurrentWeek(
        realized=9.0,
        open_players=(),
        open_k=0.0,
        open_def=0.5,
        locked_starters=frozenset(),
        kd_actual=9.0,
    )
    assert np.allclose(_engine._constant_points(data, 100, 1, done), 9.0 + 0.5 * 6.0)


# --- simulate.live_clock / current_state / load_league_data ----------------------------------


class _Clock(datetime):
    fixed = KICKOFF + timedelta(minutes=GAME_MINUTES / 2)

    @classmethod
    def now(cls, tz=None):  # type: ignore[no-untyped-def]
        return cls.fixed


def _clock_inputs() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    mp = pl.DataFrame({"sleeper_id": ["a", "b", "c", "BUF", "free", "a"]})
    players = pl.DataFrame(
        {"sleeper_id": ["a", "b", "c", "free"], "team": ["KCC", "BUF", "DAL", None]}
    )
    schedules = pl.DataFrame(
        {
            "season": [2026, 2026],
            "week": [7, 7],
            "gameday": ["2026-10-25", "2026-10-25"],
            "gametime": ["13:00", "20:20"],
            "away_team": ["KC", "DAL"],
            "home_team": ["BUF", "NYG"],
        }
    )
    return mp, players, schedules


def test_live_clock_gives_each_player_the_share_left_of_his_teams_game(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sim, "datetime", _Clock)
    mp, players, schedules = _clock_inputs()
    out = sim.live_clock(mp, players, schedules, 2026, 7)
    assert out["a"] == pytest.approx(0.5)  # KCC maps to KC, kicked off 100 minutes ago
    assert out["b"] == pytest.approx(0.5)
    assert out["BUF"] == pytest.approx(0.5)  # a defense is keyed by its team code
    assert out["c"] == 1.0  # DAL plays at night
    assert out["free"] == 1.0  # no team, no kickoff: not started
    assert list(out) == ["a", "b", "c", "BUF", "free"]  # one key per player, first-seen order


def test_live_clock_reads_final_once_the_game_clock_has_run_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Late(_Clock):
        fixed = KICKOFF + timedelta(minutes=GAME_MINUTES)

    monkeypatch.setattr(sim, "datetime", Late)
    mp, players, schedules = _clock_inputs()
    assert sim.live_clock(mp, players, schedules, 2026, 7)["a"] == 0.0


def test_live_clock_reads_not_started_exactly_at_kickoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AtKickoff(_Clock):
        fixed = KICKOFF

    monkeypatch.setattr(sim, "datetime", AtKickoff)
    mp, players, schedules = _clock_inputs()
    assert sim.live_clock(mp, players, schedules, 2026, 7)["a"] == 1.0


def _starters(rows: list[tuple[str, str, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "roster_id": 1,
                "is_starter": True,
                "sleeper_id": s,
                "gsis_id": s,
                "position": pos,
                "points": pts,
            }
            for s, pos, pts in rows
        ]
    )


def test_current_state_with_only_a_final_defense_has_no_open_skill_players() -> None:
    state = sim.current_state(_starters([("dst", "DEF", 7.0)]), {}, {}, {"dst": 0.0})[1]
    assert state.open_players == () and state.open_def == 0.0 and state.kd_actual == 7.0
    assert state.realized == 7.0 and state.locked_starters == {"dst"}


def test_current_state_does_not_open_a_slot_for_a_final_skill_player() -> None:
    rows = _starters([("done", "WR", 11.0), ("later", "RB", 0.0)])
    state = sim.current_state(
        rows,
        {"done": 12.0, "later": 8.0},
        {"done": "WR", "later": "RB"},
        {"done": 0.0, "later": 1.0},
    )[1]
    assert [p.id for p in state.open_players] == ["later"]
    assert state.realized == 11.0


def test_load_league_data_live_holds_points_and_share_for_every_player_on_the_slate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    write_rows(
        tmp_path,
        "matchup_players",
        [
            {"league_id": "L1", "week": 3, "roster_id": 1, "sleeper_id": "qb", "points": 14.5}
            | {"is_starter": True},
            {"league_id": "L1", "week": 3, "roster_id": 2, "sleeper_id": "opp", "points": 4.0}
            | {"is_starter": True},
        ],
    )
    write_rows(
        tmp_path,
        "nfl_schedules",
        [
            {"season": 2026, "week": 3, "gameday": "2026-09-20", "gametime": "13:00"}
            | {"away_team": "KC", "home_team": "BUF"}
        ],
    )
    monkeypatch.setattr(
        sim, "datetime", type("Done", (_Clock,), {"fixed": datetime(2026, 9, 21, tzinfo=UTC)})
    )
    data = sim.load_league_data(LEAGUE)
    assert data.live["G_QB"] == (14.5, 0.0)
    assert data.live["G_OPP"] == (4.0, 0.0)
    assert data.current[1].locked_starters == {"G_QB"}


# --- (8) the API lineup route ------------------------------------------------------------------


def test_the_lineup_route_returns_a_final_player_as_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from fantasy import api

    _engine_store(tmp_path, monkeypatch)
    _engine._clear_league_cache()
    data, _ = _engine._league("t")
    gone = data.projections.filter(pl.col("gsis_id") != "G_WR")  # his game is over
    _with(monkeypatch, projections=gone, live={"G_WR": (17.5, 0.0), "G_QB": (8.0, 0.4)})
    headers = {"X-Requested-With": "fantasy-app"}
    with TestClient(api.create_app(), base_url="http://localhost", headers=headers) as client:
        response = client.get("/api/leagues/t/lineup?week=3")
    assert response.status_code == 200, response.text
    rows = {r["gsis_id"]: r for r in response.json()["data"]}
    assert (rows["G_WR"]["game"], rows["G_WR"]["actual"]) == ("Final", 17.5)
    assert rows["G_WR"]["projection"] == 17.5
    assert rows["G_QB"]["game"] == "Live, 40% left"
    assert rows["G_RB"]["game"] == "Not started"
