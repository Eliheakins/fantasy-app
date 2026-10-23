"""Win probability of lineups against one opponent, and which lineup to prefer.

Candidates are the max-points lineup, the lineup set in Sleeper, and every single swap of an
unlocked starter for an unlocked bench player. The choice is made on one half of the draws and
reported on the other, so picking the best of many candidates does not inflate its win rate.
"""

from typing import NamedTuple

import numpy as np

from fantasy.sim.lineup import Player, auto_lineup

CLEAR_SHARE = 0.70
LEAN_SHARE = 0.55


class Verdict(NamedTuple):
    chosen: frozenset[str]
    win_prob: dict[frozenset[str], float]  # on the held-out half of the draws
    share_better: float  # of games where the two lineups disagree, how often the choice wins
    tag: str  # "clear", "lean", "toss-up", or "same as max points"


def feasible(ids: frozenset[str], positions: dict[str, str], slots: list[str]) -> bool:
    """True if the players can fill len(ids) distinct slots they are eligible for."""
    players = [Player(i, positions[i], 0.0) for i in ids]
    return len(auto_lineup(players, slots).players) == len(ids)


def swap_candidates(
    base: frozenset[str],
    bench: list[str],
    positions: dict[str, str],
    slots: list[str],
    locked: set[str],
) -> list[frozenset[str]]:
    """`base` plus every legal one-player swap that moves no locked player."""
    found = {base}
    for out in base - locked:
        for incoming in bench:
            if incoming in locked:
                continue
            swapped = (base - {out}) | {incoming}
            if feasible(swapped, positions, slots):
                found.add(swapped)
    return sorted(found, key=sorted)


def choose(
    candidates: list[frozenset[str]],
    baseline: frozenset[str],
    totals: dict[frozenset[str], np.ndarray],
    opponent: np.ndarray,
) -> Verdict:
    """Pick the candidate with the best win rate on the first half of the draws, then report
    every candidate's win rate and the paired comparison with `baseline` on the second half."""
    half = opponent.size // 2
    train = {c: float((totals[c][:half] > opponent[:half]).mean()) for c in candidates}
    chosen = max(candidates, key=lambda c: (train[c], c == baseline))
    held = {c: float((totals[c][half:] > opponent[half:]).mean()) for c in candidates}
    if chosen == baseline:
        return Verdict(chosen, held, 0.5, "same as max points")
    win_a = totals[chosen][half:] > opponent[half:]
    win_b = totals[baseline][half:] > opponent[half:]
    a_only, b_only = int((win_a & ~win_b).sum()), int((win_b & ~win_a).sum())
    share = a_only / (a_only + b_only) if a_only + b_only else 0.5
    tag = "clear" if share >= CLEAR_SHARE else "lean" if share >= LEAN_SHARE else "toss-up"
    return Verdict(chosen, held, share, tag)
