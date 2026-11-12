"""Bracket engine, realized playoff weeks, standings cap and the week 16+ crash fix."""

from dataclasses import replace
from typing import Any

import numpy as np
import polars as pl
import pytest
from test_odds import N_TEAMS, toy_league
from test_season import inputs

from fantasy.sim import bracket, odds
from fantasy.sim.league_data import _standings_inputs
from fantasy.sim.season import simulate_season

START = 8  # toy league: playoffs are weeks 8 to 10

# One real winners bracket from Sleeper (6 teams, nothing played), roster ids anonymised.
REAL_ROWS: list[dict[str, Any]] = [
    {"r": 1, "m": 1, "t1": 13, "t2": 14},
    {"r": 1, "m": 2, "t1": 15, "t2": 16},
    {"r": 2, "m": 3, "t1": 12, "t2_from_kind": "w", "t2_from_m": 1},
    {"r": 2, "m": 4, "t1": 11, "t2_from_kind": "w", "t2_from_m": 2},
    {"r": 2, "m": 5, "p": 5, "t1_from_kind": "l", "t1_from_m": 1, "t2_from_kind": "l", "t2_from_m": 2},  # noqa: E501
    {"r": 3, "m": 6, "p": 1, "t1_from_kind": "w", "t1_from_m": 3, "t2_from_kind": "w", "t2_from_m": 4},  # noqa: E501
    {"r": 3, "m": 7, "p": 3, "t1_from_kind": "l", "t1_from_m": 3, "t2_from_kind": "l", "t2_from_m": 4},  # noqa: E501
]  # fmt: skip


def real(rows: list[dict[str, Any]] = REAL_ROWS) -> tuple[bracket.Match, ...]:
    return bracket.from_rows([{"bracket": "winners", **r} for r in rows])


def shape(matches: tuple[bracket.Match, ...]) -> list[tuple[Any, ...]]:
    def kind(slot: bracket.Slot) -> Any:
        if isinstance(slot, int):
            return "team"  # a roster id (real) stands where a seed does (template)
        return "team" if slot is None or slot[0] == "s" else slot

    return [(m.r, m.m, m.p, kind(m.t1), kind(m.t2)) for m in sorted(matches, key=lambda x: x.m)]


def test_template_6_has_the_shape_of_sleepers_real_six_team_bracket() -> None:
    assert shape(bracket.template_6()) == shape(real())


def test_template_6_seeds_are_3v6_4v5_with_byes_for_1_and_2() -> None:
    by_m = {m.m: m for m in bracket.template_6()}
    assert (by_m[1].t1, by_m[1].t2) == (("s", 3), ("s", 6))
    assert (by_m[2].t1, by_m[2].t2) == (("s", 4), ("s", 5))
    assert by_m[3].t1 == ("s", 2) and by_m[3].t2 == ("w", 1)
    assert by_m[4].t1 == ("s", 1) and by_m[4].t2 == ("w", 2)
    assert [m.m for m in bracket.template_6() if m.p == 1] == [6]


def test_round_weeks_map_round_one_to_the_playoff_start() -> None:
    assert [bracket.round_weeks(r, 15) for r in (1, 2, 3)] == [(15,), (16,), (17,)]


def test_zero_noise_ordered_means_make_the_top_seed_win_and_byes_sum_to_two() -> None:
    inp = inputs(np.arange(N_TEAMS, dtype=float)[::-1] * 10, 0.0)  # team 0 is best
    # seeds come from wins, so give the order directly: best team wins every game
    res = simulate_season(inp)
    assert res.p_title[0] == 1.0
    assert res.p_bye.sum() == pytest.approx(2.0)
    assert res.p_reach[0].sum() == 0.0 or res.p_reach.shape[0] == 3
    assert res.p_win[2, 0] == 1.0  # the final round's winner is the champion
    assert res.p_reach[1].sum() == pytest.approx(4.0)  # four teams play round 2
    assert res.p_reach[2].sum() == pytest.approx(2.0)


def at_week(week: int, **kw: Any) -> odds.LeagueData:
    played = {(r, w): 90.0 + r for r in range(1, N_TEAMS + 1) for w in range(START, week)}
    return replace(toy_league(), current_week=week, realized=played, **kw)


@pytest.mark.parametrize("week", [START - 1, START, START + 1, START + 2, 18])
def test_the_season_runs_from_the_week_before_the_playoffs_to_after_the_final(week: int) -> None:
    data = at_week(week)
    res = odds.league_odds(data, n_sims=200)
    assert res.p_title.sum() == pytest.approx(1.0)
    inp = odds.build_inputs(data, None, 50, 0)
    assert inp.weeks[0] == min(week, START) and inp.weeks[-1] == START + 2


def test_played_playoff_weeks_take_actual_points_with_no_noise() -> None:
    inp = odds.build_inputs(at_week(START + 1), None, 50, 0)
    assert inp.mean[0, 0] == 91.0 and inp.noise_sd[0, 0] == 0.0
    assert not inp.shift[:, 0].any()
    assert inp.noise_sd[0, 1] > 0  # the current week is still simulated


def test_standings_after_the_regular_season_count_no_playoff_week() -> None:
    inp = odds.build_inputs(at_week(START + 1), None, 50, 0)
    assert inp.pairs == {}  # regular-season weeks only; none left
    assert simulate_season(inp).p_title.sum() == pytest.approx(1.0)


def seeded_rows(w1: int | None = None, w2: int | None = None) -> list[dict[str, Any]]:
    """Seeds 1 to 6 are rosters 1 to 6; w1 and w2 are the round-1 winners when played."""
    return [
        {"r": 1, "m": 1, "t1": 3, "t2": 6, "w": w1},
        {"r": 1, "m": 2, "t1": 4, "t2": 5, "w": w2},
        {"r": 2, "m": 3, "t1": 2, "t2_from_kind": "w", "t2_from_m": 1},
        {"r": 2, "m": 4, "t1": 1, "t2_from_kind": "w", "t2_from_m": 2},
        {"r": 3, "m": 6, "p": 1, "t1_from_kind": "w", "t1_from_m": 3, "t2_from_kind": "w", "t2_from_m": 4},  # noqa: E501
    ]  # fmt: skip


def test_a_played_round_gives_the_loser_exactly_zero_title_odds() -> None:
    rows = seeded_rows(w1=3, w2=5)
    res = odds.league_odds(at_week(START + 1, bracket=real(rows)), n_sims=500)
    assert res.p_title[[5, 3]].tolist() == [0.0, 0.0]  # rosters 6 and 4 lost
    assert res.p_title[[6, 7]].tolist() == [0.0, 0.0]  # never in the playoffs
    assert res.p_playoffs.tolist() == [1, 1, 1, 1, 1, 1, 0, 0]  # the field is fixed
    assert res.p_seed[0, 0] == 1.0 and res.p_seed[2, 2] == 1.0


def test_real_seeds_replace_the_simulated_order_once_trusted() -> None:
    rows = seeded_rows()  # seeds 3, 6, 4, 5, 2, 1 are rosters 8, 1, 7, 2, 6, 5
    rows[0] |= {"t1": 8, "t2": 1}
    rows[1] |= {"t1": 7, "t2": 2}
    rows[2] |= {"t1": 6}
    rows[3] |= {"t1": 5}
    data = at_week(START, bracket=real(rows))
    res = odds.league_odds(data, n_sims=300)
    assert res.p_playoffs[[7, 6, 5, 4, 0, 1]].tolist() == [1.0] * 6
    assert res.p_seed[4, 0] == 1.0  # roster 5 is the top seed (t1 of match 4)


def test_provisional_rows_before_the_playoffs_are_ignored() -> None:
    rows = seeded_rows(w1=3, w2=5)
    base = odds.league_odds(at_week(START - 1), n_sims=300)
    ignored = odds.league_odds(at_week(START - 1, bracket=real(rows)), n_sims=300)
    assert np.array_equal(base.p_title, ignored.p_title)
    assert np.array_equal(base.p_seed, ignored.p_seed)


def test_a_known_champion_is_fixed_after_the_final() -> None:
    rows = [*seeded_rows(w1=3, w2=5)[:4], {**seeded_rows()[4], "w": 2}]
    rows[2] = {**rows[2], "w": 2}
    rows[3] = {**rows[3], "w": 5}
    res = odds.league_odds(at_week(18, bracket=real(rows)), n_sims=50)
    assert res.p_title.tolist() == [0, 1, 0, 0, 0, 0, 0, 0]


def test_standings_inputs_count_regular_season_weeks_only() -> None:
    weeks = [1, 2, 3, 4]  # playoffs start in week 3
    matchups = pl.DataFrame(
        [("L", w, 1, r, 100.0 * r) for w in weeks for r in (1, 2)],
        schema=["league_id", "week", "matchup_id", "roster_id", "points"],
        orient="row",
    )
    teams = pl.DataFrame({"league_id": ["L", "L"], "roster_id": [1, 2], "team_name": ["a", "b"]})
    wins, points = _standings_inputs(matchups, teams, "L", current=5, playoff_start=3)
    assert wins == {1: 0.0, 2: 2.0} and points == {1: 200.0, 2: 400.0}
