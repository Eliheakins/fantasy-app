"""Per-slot paired share: how often the starter outscores the best eligible bench player."""

import numpy as np

from fantasy.sim.winprob import slot_shares

COLUMN = {"qb": 0, "wr": 1, "rb": 2, "te": 3}
# draws: wr beats rb in 3 of 4, ties once counts half only if equal
POINTS = np.array(
    [
        [20.0, 10.0, 8.0, 5.0],
        [20.0, 12.0, 15.0, 5.0],
        [20.0, 9.0, 7.0, 5.0],
        [20.0, 11.0, 6.0, 9.0],
    ]
)
POSITIONS = {"qb": "QB", "wr": "WR", "rb": "RB", "te": "TE"}
VALUES = {"qb": 20.0, "wr": 10.5, "rb": 9.0, "te": 6.0}


def test_share_is_the_paired_fraction_against_the_best_eligible_bench_player() -> None:
    calls = slot_shares(POINTS, COLUMN, [("FLEX", "wr")], ["rb", "te"], POSITIONS, VALUES, set())
    assert calls == [{"slot": "FLEX", "starter": "wr", "alternative": "rb", "share": 0.75}]


def test_a_tie_counts_half() -> None:
    points = np.array([[5.0, 5.0], [6.0, 5.0]])
    calls = slot_shares(
        points, {"a": 0, "b": 1}, [("RB", "a")], ["b"], {"a": "RB", "b": "RB"}, {"b": 1.0}, set()
    )
    assert calls[0]["share"] == 0.75


def test_slot_with_no_eligible_alternative_has_no_share() -> None:
    calls = slot_shares(POINTS, COLUMN, [("QB", "qb")], ["rb", "te"], POSITIONS, VALUES, set())
    assert calls == [{"slot": "QB", "starter": "qb", "alternative": None, "share": None}]


def test_locked_bench_players_and_locked_starters_are_not_alternatives() -> None:
    args = (COLUMN, [("FLEX", "wr")], ["rb", "te"], POSITIONS, VALUES)
    assert slot_shares(POINTS, *args, {"rb"})[0]["alternative"] == "te"
    assert slot_shares(POINTS, *args, {"wr"})[0]["share"] is None


def test_superflex_takes_any_position_and_picks_the_highest_value_bench_player() -> None:
    calls = slot_shares(
        POINTS, COLUMN, [("SUPER_FLEX", "wr")], ["qb", "te"], POSITIONS, VALUES, set()
    )
    assert calls[0]["alternative"] == "qb" and calls[0]["share"] == 0.0


def test_k_and_def_slots_have_no_alternative() -> None:
    calls = slot_shares(
        POINTS, COLUMN, [("K", "wr"), ("DEF", "wr")], ["rb"], POSITIONS, VALUES, set()
    )
    assert [c["share"] for c in calls] == [None, None]


def test_bench_players_worth_nothing_are_not_alternatives() -> None:
    values = {**VALUES, "rb": 0.0}
    calls = slot_shares(POINTS, COLUMN, [("FLEX", "wr")], ["rb"], POSITIONS, values, set())
    assert calls[0]["alternative"] is None


def test_a_starter_worth_nothing_is_still_compared() -> None:
    values = {**VALUES, "wr": 0.0}
    calls = slot_shares(POINTS, COLUMN, [("FLEX", "wr")], ["rb"], POSITIONS, values, set())
    assert calls[0]["share"] == 0.75


def test_the_draws_are_not_modified() -> None:
    before = POINTS.copy()
    slot_shares(POINTS, COLUMN, [("FLEX", "wr")], ["rb"], POSITIONS, VALUES, set())
    assert np.array_equal(POINTS, before)
