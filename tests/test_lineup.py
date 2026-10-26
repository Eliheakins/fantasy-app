import random
from datetime import datetime, timedelta

import pytest

from fantasy.sim import lineup as lu
from fantasy.sim.lineup import Player

SUPERFLEX_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX"]


def roster(spec: dict[str, list[float]]) -> list[Player]:
    players = []
    for pos, values in spec.items():
        players += [Player(f"{pos}{i}", pos, value) for i, value in enumerate(values)]
    return players


def test_slots_skip_bench_and_constant_slots_and_reject_unknown() -> None:
    positions = ["QB", "RB", "FLEX", "K", "DEF", "BN", "BN", "IR"]
    assert lu.lineup_slots(positions) == ["QB", "RB", "FLEX"]
    assert lu.constant_slot_count(positions) == {"DEF": 1, "K": 1}
    with pytest.raises(ValueError, match="unknown roster slot"):
        lu.lineup_slots(["QB", "WRRB_FLEX"])


def test_superflex_takes_the_second_quarterback_when_he_beats_the_flex_options() -> None:
    players = roster(
        {"QB": [20, 18], "RB": [15, 12, 8], "WR": [14, 11, 9], "TE": [7, 4]},
    )
    best = lu.auto_lineup(players, SUPERFLEX_SLOTS)
    assert "QB1" in best.players  # both quarterbacks start
    # QB 20 + RB 15 + 12 + WR 14 + 11 + TE 7 + FLEX 9 (WR2... 8 or 9 -> best leftover) + QB 18
    assert best.total == pytest.approx(20 + 15 + 12 + 14 + 11 + 7 + 9 + 18)


def test_empty_slot_when_no_one_is_eligible() -> None:
    best = lu.auto_lineup(roster({"QB": [20]}), ["QB", "RB"])
    assert best.total == 20 and len(best.slots) == 1


def test_top_lineups_are_distinct_and_sorted() -> None:
    players = roster({"QB": [20, 18], "RB": [15, 12, 8], "WR": [14, 11, 9], "TE": [7, 4]})
    top = lu.top_lineups(players, SUPERFLEX_SLOTS, 5)
    assert [t.total for t in top] == sorted((t.total for t in top), reverse=True)
    assert len({t.players for t in top}) == 5
    assert top[0].total == lu.auto_lineup(players, SUPERFLEX_SLOTS).total


def test_greedy_equals_exhaustive_search_on_random_rosters() -> None:
    rng = random.Random(7)
    for slots in (SUPERFLEX_SLOTS, ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX"]):
        for _ in range(40):
            spec = {
                "QB": [rng.uniform(0, 25) for _ in range(rng.randint(1, 3))],
                "RB": [rng.uniform(0, 20) for _ in range(rng.randint(2, 6))],
                "WR": [rng.uniform(0, 20) for _ in range(rng.randint(2, 6))],
                "TE": [rng.uniform(0, 15) for _ in range(rng.randint(1, 3))],
            }
            players = roster(spec)
            greedy = lu.auto_lineup(players, slots).total
            exhaustive = lu.top_lineups(players, slots, 1)[0].total
            assert greedy == pytest.approx(exhaustive)


SUNDAY = datetime(2026, 10, 25, 13, 0)


def _plan(
    players: list[Player],
    slots: list[str],
    flagged: set[str],
    kicks: dict[str, datetime],
    locked: frozenset[str] = frozenset(),
) -> tuple[lu.Lineup, dict[str, str]]:
    lineup = lu.lineup_with_locks(players, slots, set(locked), set())
    return lineup, lu.swap_plan(lineup, players, flagged, kicks, set(locked))


def test_swap_plan_is_advice_only_and_names_a_bench_player_who_plays_later() -> None:
    kicks = {"q": SUNDAY, "b": SUNDAY + timedelta(hours=3)}
    benched = [Player("q", "WR", 10.0), Player("b", "WR", 12.0)]  # expected points: b starts
    lineup, plan = _plan(benched, ["WR"], {"q"}, kicks)
    assert lineup.players == {"b"} and plan == {}
    started = [Player("q", "WR", 14.0), Player("b", "WR", 12.0)]
    lineup, plan = _plan(started, ["WR"], {"q"}, kicks)
    assert lineup.players == {"q"} and plan == {"q": "b"}


def test_swap_plan_skips_bench_players_whose_game_starts_by_the_inactives_release() -> None:
    players = [Player("q", "WR", 14.0), Player("b", "WR", 12.0)]
    kicks = {"q": SUNDAY, "b": SUNDAY - timedelta(minutes=90)}  # kicks off at q's inactives
    assert _plan(players, ["WR"], {"q"}, kicks)[1] == {}


def test_swap_plan_names_the_best_eligible_bench_player_and_skips_locked_ones() -> None:
    players = [
        Player("q", "RB", 8.0),
        Player("wr", "WR", 9.0),
        Player("rb_low", "RB", 5.0),
        Player("rb_locked", "RB", 7.0),
        Player("wr_bench", "WR", 6.0),  # better, but not eligible for the RB slot
    ]
    kicks = {p.id: SUNDAY + timedelta(hours=3) for p in players} | {"q": SUNDAY}
    assert _plan(players, ["RB", "WR"], {"q"}, kicks, frozenset({"rb_locked"}))[1] == {
        "q": "rb_low"
    }


def test_swap_plan_promises_a_bench_player_to_one_starter_in_kickoff_order() -> None:
    players = [Player("early", "WR", 15.0), Player("late", "WR", 14.0), Player("b", "WR", 6.0)]
    kicks = {
        "early": SUNDAY,
        "late": SUNDAY + timedelta(hours=3),
        "b": SUNDAY + timedelta(hours=7),
    }
    lineup, plan = _plan(players, ["WR", "WR"], {"early", "late"}, kicks)
    assert lineup.players == {"early", "late"} and plan == {"early": "b"}
