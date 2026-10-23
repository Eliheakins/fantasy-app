import pytest

from fantasy.sim.lineup import Player
from fantasy.sim.value import absence_probs, replacement_pool, season_value, stand_ins

SLOTS = ["TE"]
POSITIONS = {"s": "TE", "b": "TE", "fa": "TE"}
VALUES = {1: {"s": 10.0, "b": 9.0, "fa": 9.0}}
OUT = {"s": [0.2]}


def test_a_backup_is_worth_nothing_when_a_free_agent_of_the_same_quality_exists() -> None:
    fa = {1: [Player("fa", "TE", 9.0)]}
    with_backup = season_value(SLOTS, POSITIONS, VALUES, ["s", "b"], OUT, fa)
    without = season_value(SLOTS, POSITIONS, VALUES, ["s"], OUT, fa)
    assert with_backup == pytest.approx(without)


def test_a_backup_is_worth_his_gap_over_nothing_when_the_position_has_no_free_agents() -> None:
    with_backup = season_value(SLOTS, POSITIONS, VALUES, ["s", "b"], OUT, {})
    without = season_value(SLOTS, POSITIONS, VALUES, ["s"], OUT, {})
    assert with_backup - without == pytest.approx(0.2 * 9.0)  # out 20% of the time, backup scores 9


def test_a_starter_below_the_replacement_floor_adds_nothing() -> None:
    floor = {1: [Player("fa", "TE", 12.0)]}
    alone = season_value(SLOTS, POSITIONS, VALUES, ["s"], OUT, floor)
    empty = season_value(SLOTS, POSITIONS, VALUES, [], {}, floor)
    assert alone == pytest.approx(empty) == pytest.approx(12.0)


def test_a_bye_week_hole_is_filled_by_a_stand_in_not_left_empty() -> None:
    floor = {1: [Player("fa", "TE", 7.0)]}
    on_bye = {1: {}}  # the starter has no projection this week
    assert season_value(SLOTS, POSITIONS, on_bye, ["s"], {}, floor) == pytest.approx(7.0)
    assert season_value(SLOTS, POSITIONS, on_bye, ["s"], {}, {}) == 0.0  # no stand-in, no points


def test_absence_probs_start_at_the_status_and_move_toward_the_long_run_rate() -> None:
    chances = absence_probs(0.0, 30, hazard=0.07, stay_out=0.55)
    assert chances[0] == 1.0 and chances[1] == pytest.approx(0.55)
    assert chances[-1] == pytest.approx(0.07 / (0.07 + 1 - 0.55), abs=1e-3)
    assert absence_probs(1.0, 1, 0.07, 0.55) == [0.0]


def test_replacement_pool_skips_the_best_free_agents_who_are_adds_not_stand_ins() -> None:
    positions = {"a": "TE", "b": "TE", "c": "TE", "d": "TE", "w": "WR"}
    values = {1: {"a": 5.0, "b": 8.0, "c": 7.0, "d": 6.0, "w": 9.0}}
    pool = replacement_pool(list(positions), positions, values)[1]
    assert [p.id for p in pool if p.position == "TE"] == ["d", "a"]  # ranks 3 and 4
    assert [p.id for p in pool if p.position == "WR"] == []  # only one WR: he is an add


def test_stand_ins_exclude_players_the_roster_holds_and_keep_the_next_ones() -> None:
    candidates = [Player(i, "TE", v) for i, v in (("x", 9.0), ("y", 8.0), ("z", 7.0))]
    chosen = stand_ins(candidates, {"x"})
    assert [p.id for p in chosen] == ["y", "z"]
