"""4-, 6- and 8-team brackets, one- and two-week rounds, and the one shape gate."""

from typing import Any

import numpy as np
import pytest

from fantasy.sim import bracket
from fantasy.sim.league_checks import check_league_shape


def run(
    n_teams: int,
    weeks: list[int],
    scores_by_team: dict[int, list[float]] | None = None,
    round_type: int = 0,
    start: int = 10,
) -> bracket.BracketResult:
    """Seeds are teams 0..n-1 in order. Default scores: team 0 best, falling by 10 a team."""
    scores = np.zeros((n_teams, len(weeks), 1))
    for t in range(n_teams):
        scores[t, :, 0] = (scores_by_team or {}).get(t, [100.0 - 10 * t] * len(weeks))
    order = np.arange(n_teams)[None, :]
    tpl = bracket.template(n_teams if n_teams in (4, 8) else 6, round_type)
    return bracket.resolve(
        tpl, order, scores, {w: i for i, w in enumerate(weeks)},
        list(range(1, n_teams + 1)), start, round_type,
    )  # fmt: skip


@pytest.mark.parametrize(("size", "byes", "rounds"), [(4, 0, 2), (6, 2, 3), (8, 0, 3)])
def test_the_top_seed_wins_and_byes_match_the_bracket_size(
    size: int, byes: int, rounds: int
) -> None:
    res = run(size, list(range(10, 10 + rounds)))
    assert res.champion[0] == 0
    assert res.p_bye.sum() == pytest.approx(byes)
    assert res.p_reach[0].sum() == pytest.approx(size - byes)
    assert res.p_reach[-1].sum() == pytest.approx(2.0)
    assert len(res.rounds) == rounds


def test_a_two_week_round_is_decided_by_the_sum_of_both_weeks() -> None:
    # round 1 = weeks 10 and 11, the final = 12 and 13. First week alone or last week alone
    # would pick a different winner in one of the two games.
    res = run(
        4, [10, 11, 12, 13],
        {0: [50, 50, 0, 0], 3: [100, 1, 0, 0], 1: [50, 50, 0, 0], 2: [1, 100, 5, 5]},
        round_type=2,
    )  # fmt: skip
    assert res.p_reach[1, [2, 3]].tolist() == [1.0, 1.0]  # sums 101 beat 100 in both games
    assert res.p_reach[1, [0, 1]].tolist() == [0.0, 0.0]


def test_round_type_1_makes_only_the_final_two_weeks() -> None:
    res = run(
        4, [10, 11, 12],
        {0: [100, 100, 0], 1: [100, 0, 60], 2: [0, 0, 0], 3: [0, 0, 0]},
        round_type=1,
    )  # fmt: skip
    assert res.champion[0] == 0  # 100 + 0 beats 0 + 60, and 100 + 100 beats team 2 in round one
    assert res.p_win[1, 0] == 1.0


@pytest.mark.parametrize(
    ("teams", "round_type", "weeks"),
    [
        (4, 0, [(15,), (16,)]),
        (4, 1, [(15,), (16, 17)]),
        (4, 2, [(15, 16), (17, 18)]),
        (6, 0, [(15,), (16,), (17,)]),
        (6, 1, [(15,), (16,), (17, 18)]),
        (8, 2, [(15, 16), (17, 18), (19, 20)]),
    ],
)
def test_round_weeks_follow_the_round_type(
    teams: int, round_type: int, weeks: list[tuple[int, ...]]
) -> None:
    n = len(weeks)
    assert [bracket.round_weeks(r, 15, round_type, n) for r in range(1, n + 1)] == weeks
    assert bracket.playoff_weeks(teams, round_type) == sum(len(w) for w in weeks)


def test_templates_have_the_layout_of_the_real_sleeper_brackets() -> None:
    assert bracket.template(6) == bracket.template_6()
    t8 = {m.m: m for m in bracket.template(8)}
    assert [(t8[i].t1, t8[i].t2) for i in (1, 2, 3, 4)] == [
        (("s", 1), ("s", 8)), (("s", 4), ("s", 5)), (("s", 2), ("s", 7)), (("s", 3), ("s", 6)),
    ]  # fmt: skip
    assert [m.p for m in t8.values() if m.p] == [1, 3]
    t4 = bracket.template(4)
    assert [(m.t1, m.t2) for m in t4 if m.r == 1] == [
        (("s", 1), ("s", 4)), (("s", 2), ("s", 3)),
    ]  # fmt: skip
    assert sorted(m.p for m in t4 if m.p) == [1, 3]


SHAPE: list[tuple[Any, ...]] = [
    # num_teams, playoff_teams, start, round_type, seed_type, divisions, words (None: fine)
    (10, 6, 15, 0, 0, 1, None),
    (10, 4, 15, 0, 0, 1, None),
    (12, 8, 15, 0, 0, 0, None),
    (12, 8, 14, 1, None, None, None),
    (12, 8, 14, 1, 0, 1, None),
    (12, 8, 12, 2, 0, 1, None),
    (12, 4, 16, 0, 0, 1, None),
    (10, 6, 14, 0, 0, 1, None),
    (10, 6, 16, 0, 0, 1, "start week"),  # three rounds from week 16 end in week 18
    (10, 6, 15, 1, 0, 1, "start week"),
    (10, 6, 13, 2, 0, 1, "start week"),
    (12, 8, 13, 2, 0, 1, "start week"),
    (10, 4, 17, 0, 0, 1, "start week"),
    (10, 6, 0, 0, 0, 1, "start week"),
    (10, 6, None, 0, 0, 1, "start week"),
    (16, None, 0, 0, 0, 1, "no playoff"),
    (16, 0, 0, 0, 0, 1, "no playoff"),
    (10, 5, 15, 0, 0, 1, "4, 6 or 8"),
    (10, 12, 15, 0, 0, 1, "4, 6 or 8"),
    (5, 6, 15, 0, 0, 1, "at least 6 teams"),
    (6, 8, 12, 0, 0, 1, "at least 8 teams"),
    (10, 6, 15, 3, 0, 1, "round"),
    (10, 6, 15, 0, 1, 1, None),
    (10, 6, 15, 0, 2, 1, "seeding setting"),
    (10, 6, 15, 0, 0, 2, None),
    (12, 6, 15, 0, 1, 6, None),
    (12, 6, 15, 0, 0, 7, "divisions"),
]


@pytest.mark.parametrize(("teams", "po", "start", "rt", "seed", "divs", "words"), SHAPE)
def test_the_shape_gate_table(
    teams: Any, po: Any, start: Any, rt: Any, seed: Any, divs: Any, words: Any
) -> None:
    problem = bracket.shape_problem(teams, po, start, rt, seed, divs)
    if words is None:
        assert problem is None
    else:
        assert problem is not None and words in problem


@pytest.mark.parametrize(("teams", "po", "start", "rt", "seed", "divs", "words"), SHAPE)
def test_check_league_shape_agrees_with_the_gate(
    teams: Any, po: Any, start: Any, rt: Any, seed: Any, divs: Any, words: Any
) -> None:
    import json

    league = {
        "league_id": "L", "num_teams": teams, "playoff_teams": po, "playoff_week_start": start,
        "playoff_seed_type": seed,
        "settings": json.dumps({"playoff_round_type": rt, "divisions": divs}),
    }  # fmt: skip
    if po is None or po == 0:
        return  # check_league_shape leaves a no-bracket league to the gate
    if words is None:
        check_league_shape(league)
    else:
        with pytest.raises(ValueError):
            check_league_shape(league)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 0),
        ("", 0),
        ("{", 0),
        ("[]", 0),
        ('{"playoff_round_type": 2}', 2),
        ('{"playoff_round_type": null}', 0),
    ],
)
def test_round_type_is_read_defensively_from_the_settings_json(
    raw: str | None, expected: int
) -> None:
    assert bracket.round_type_of(raw) == expected


@pytest.mark.parametrize(("teams", "round_type", "weeks"), [(4, 0, 2), (8, 2, 6), (6, 1, 4)])
def test_the_season_simulation_follows_the_leagues_bracket_length(
    teams: int, round_type: int, weeks: int
) -> None:
    from dataclasses import replace

    from test_odds import toy_league

    from fantasy.sim import odds

    data = replace(toy_league(), playoff_teams=teams, round_type=round_type)
    assert data.playoff_weeks == weeks
    inp = odds.build_inputs(data, None, 50, 0)
    assert inp.weeks[-1] == data.playoff_start + weeks - 1
    res = odds.league_odds(data, n_sims=100)
    assert res.p_title.sum() == pytest.approx(1.0)
    assert res.p_playoffs.sum() == pytest.approx(teams)
