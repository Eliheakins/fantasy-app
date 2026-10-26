"""Lineup slots, the best lineup by expected points, and top-K lineups.

Slot eligibility is nested (SUPER_FLEX contains FLEX contains RB, WR and TE, and QB sits inside
SUPER_FLEX), so filling the narrowest slots first with the best remaining player is optimal.
`top_lineups` enumerates every lineup and is used to check the greedy fill and, later, to offer
near-optimal alternatives. K and DEF slots are not filled here: they are not skill
players, so callers add their own value for them.
"""

import itertools
from datetime import datetime, timedelta
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
INACTIVES_LEAD = timedelta(minutes=90)  # NFL inactive lists come out this long before kickoff


class Player(NamedTuple):
    id: str
    position: str
    value: float


class Lineup(NamedTuple):
    total: float
    players: frozenset[str]
    slots: tuple[tuple[str, str], ...]  # (slot, player id), narrowest slots first


class ActualPlayer(NamedTuple):
    id: str
    positions: tuple[str, ...]  # fantasy positions; more than one for a multi-position player
    points: float


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


def lineup_with_locks(
    players: list[Player], slots: list[str], locked: set[str], starting: set[str]
) -> Lineup:
    """Best lineup when locked players cannot move: locked starters keep a slot, locked bench
    players cannot start. Everyone else is filled greedily into the slots left over."""
    pinned = auto_lineup([p for p in players if p.id in locked and p.id in starting], slots)
    open_slots = list(slots)
    for slot, _ in pinned.slots:
        open_slots.remove(slot)
    rest = auto_lineup([p for p in players if p.id not in locked], open_slots)
    return Lineup(
        pinned.total + rest.total, pinned.players | rest.players, (*pinned.slots, *rest.slots)
    )


def _swap_option(
    flagged: str,
    lineup: Lineup,
    players: list[Player],
    kicks: dict[str, datetime],
    locked: set[str],
) -> str | None:
    """The best bench player eligible for the flagged starter's slot whose game starts after
    the flagged player's inactives release, or None."""
    slot = next(s for s, pid in lineup.slots if pid == flagged)
    release = kicks[flagged] - INACTIVES_LEAD
    options = [
        p
        for p in players
        if p.id not in lineup.players
        and p.id not in locked
        and p.position in ELIGIBLE[slot]
        and p.id in kicks
        and kicks[p.id] > release
    ]
    return max(options, key=lambda p: (p.value, p.id)).id if options else None


def inactive_swap_lineup(
    players: list[Player],
    slots: list[str],
    chance: dict[str, float],
    kicks: dict[str, datetime],
    locked: set[str],
    starting: set[str],
) -> tuple[Lineup, dict[str, str]]:
    """Lineup when a Questionable or Doubtful player can be swapped out at the inactives release.

    `players` carry expected points; `chance` holds the flagged players' chance of playing. A
    flagged starter is valued at his points when he plays (value / chance) if a bench player
    eligible for his slot kicks off after his inactives release; otherwise he keeps his expected
    points. Returns the lineup (its total counts flagged starters at full value) and the plan:
    flagged starter -> bench player to start if he is inactive. research/questionable_swap_check.py
    measured this rule (policy C)."""
    full = {
        p.id: p.value / chance[p.id]
        for p in players
        if p.id in chance and chance[p.id] > 0 and p.id in kicks and p.id not in locked
    }
    while True:  # each pass drops a flagged starter with no option, so this ends
        pool = [p._replace(value=full.get(p.id, p.value)) for p in players]
        best = lineup_with_locks(pool, slots, locked, starting)
        plan = {x: _swap_option(x, best, players, kicks, locked) for x in full if x in best.players}
        stuck = {x for x, swap in plan.items() if swap is None}
        if not stuck:
            return best, {x: swap for x, swap in plan.items() if swap is not None}
        full = {x: v for x, v in full.items() if x not in stuck}


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


def best_actual(players: list[ActualPlayer], roster_positions: list[str]) -> float:
    """Most points a roster could have started in a week it already played (hindsight). Skill
    slots by the greedy fill, K and DEF as the top n of each (they are not in ELIGIBLE). A
    multi-position player is tried at each of his positions."""
    slots = lineup_slots(roster_positions)
    skill = [p for p in players if p.positions[0] not in CONSTANT_SLOTS]
    total = 0.0
    for kind, n in constant_slot_count(roster_positions).items():
        total += sum(
            sorted((p.points for p in players if p.positions[0] == kind), reverse=True)[:n]
        )
    flexible = [p for p in skill if len(p.positions) > 1]
    fixed = [Player(p.id, p.positions[0], p.points) for p in skill if len(p.positions) == 1]
    best = 0.0
    for choice in itertools.product(*(p.positions for p in flexible)):
        chosen = [Player(p.id, pos, p.points) for p, pos in zip(flexible, choice, strict=True)]
        best = max(best, auto_lineup(fixed + chosen, slots).total)
    return total + best
