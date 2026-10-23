"""Lineup slots, the best lineup by expected points, and top-K lineups.

Slot eligibility is nested (SUPER_FLEX contains FLEX contains RB, WR and TE, and QB sits inside
SUPER_FLEX), so filling the narrowest slots first with the best remaining player is optimal.
`top_lineups` enumerates every lineup and is used to check the greedy fill and, later, to offer
near-optimal alternatives. K and DEF slots are not filled here: they have no player projections
until E3-7, so callers add a constant for them.
"""

from typing import NamedTuple

ELIGIBLE: dict[str, frozenset[str]] = {
    "QB": frozenset({"QB"}),
    "RB": frozenset({"RB"}),
    "WR": frozenset({"WR"}),
    "TE": frozenset({"TE"}),
    "FLEX": frozenset({"RB", "WR", "TE"}),
    "SUPER_FLEX": frozenset({"QB", "RB", "WR", "TE"}),
}
CONSTANT_SLOTS = {"K", "DEF"}
BENCH_SLOTS = {"BN", "IR", "TAXI"}


class Player(NamedTuple):
    id: str
    position: str
    value: float


class Lineup(NamedTuple):
    total: float
    players: frozenset[str]
    slots: tuple[tuple[str, str], ...]  # (slot, player id), narrowest slots first


def lineup_slots(roster_positions: list[str]) -> list[str]:
    """Slots that hold a player projection. Raises on a slot type this module does not know."""
    slots = []
    for slot in roster_positions:
        if slot in BENCH_SLOTS or slot in CONSTANT_SLOTS:
            continue
        if slot not in ELIGIBLE:
            raise ValueError(f"unknown roster slot {slot!r}")
        slots.append(slot)
    return slots


def constant_slot_count(roster_positions: list[str]) -> dict[str, int]:
    return {s: roster_positions.count(s) for s in sorted(CONSTANT_SLOTS) if s in roster_positions}


def _narrowest_first(slots: list[str]) -> list[str]:
    return sorted(slots, key=lambda s: len(ELIGIBLE[s]))


def auto_lineup(players: list[Player], slots: list[str]) -> Lineup:
    """Best lineup by total value. Empty slots (no eligible player left) score 0."""
    ranked = sorted(players, key=lambda p: (-p.value, p.id))
    used: set[str] = set()
    chosen: list[tuple[str, str]] = []
    total = 0.0
    for slot in _narrowest_first(slots):
        pick = next((p for p in ranked if p.id not in used and p.position in ELIGIBLE[slot]), None)
        if pick is None:
            continue
        used.add(pick.id)
        chosen.append((slot, pick.id))
        total += pick.value
    return Lineup(total, frozenset(used), tuple(chosen))


def top_lineups(players: list[Player], slots: list[str], k: int) -> list[Lineup]:
    """The k best distinct lineups (by set of players), found by exhaustive search."""
    ordered = _narrowest_first(slots)
    by_id = {p.id: p for p in players}
    found: dict[frozenset[str], Lineup] = {}

    def fill(index: int, used: frozenset[str], chosen: tuple[tuple[str, str], ...]) -> None:
        if index == len(ordered):
            total = sum(by_id[pid].value for _, pid in chosen)
            found.setdefault(used, Lineup(total, used, chosen))
            return
        slot = ordered[index]
        options = [p for p in players if p.id not in used and p.position in ELIGIBLE[slot]]
        if not options:
            fill(index + 1, used, chosen)
            return
        for p in options:
            fill(index + 1, used | {p.id}, (*chosen, (slot, p.id)))

    fill(0, frozenset(), ())
    return sorted(found.values(), key=lambda lu: (-lu.total, sorted(lu.players)))[:k]
