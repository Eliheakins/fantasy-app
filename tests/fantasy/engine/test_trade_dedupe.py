"""Near-duplicate finder rows: a 2-for-2 that is a smaller swap plus a like-for-like add-on."""

from typing import Any

from fantasy.sim.moves import ODDS_TOL, drop_addons

POSITIONS = dict(swift="RB", shough="QB", stroud="QB", lamb="WR", kelce="TE", wr2="WR")


def row(give: list[str], get: list[str], odds: float = 0.02, partner: int = 2) -> dict[str, Any]:
    return {
        "partner_id": partner, "give_ids": give, "get_ids": get,
        "my_playoff": odds / 2, "my_title": odds / 2,
    }  # fmt: skip


def test_drops_the_larger_swap_when_the_extra_leg_swaps_the_same_position() -> None:
    small = row(["swift"], ["lamb"])
    big = row(["swift", "shough"], ["lamb", "stroud"], odds=0.02 + ODDS_TOL / 2)
    assert drop_addons([big, small], POSITIONS) == [small]


def test_keeps_it_when_the_extra_leg_moves_my_odds_by_the_tolerance_or_more() -> None:
    small = row(["swift"], ["lamb"])
    big = row(["swift", "shough"], ["lamb", "stroud"], odds=0.02 + ODDS_TOL * 1.01)
    assert drop_addons([small, big], POSITIONS) == [small, big]


def test_keeps_it_when_the_extra_legs_differ_in_position() -> None:
    small, big = row(["swift"], ["lamb"]), row(["swift", "shough"], ["lamb", "kelce"])
    assert drop_addons([small, big], POSITIONS) == [small, big]


def test_keeps_it_across_partners_and_when_the_smaller_swap_is_absent() -> None:
    big = row(["swift", "shough"], ["lamb", "stroud"])
    assert drop_addons([row(["swift"], ["lamb"], partner=3), big], POSITIONS)[1] == big
    assert drop_addons([big], POSITIONS) == [big]
    assert drop_addons([], POSITIONS) == []


def test_keeps_it_when_the_smaller_swap_is_not_a_subset() -> None:
    small, big = row(["swift"], ["wr2"]), row(["swift", "shough"], ["lamb", "stroud"])
    assert drop_addons([small, big], POSITIONS) == [small, big]
