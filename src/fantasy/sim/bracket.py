"""Playoff bracket engine: Sleeper-shaped matches resolved over simulated runs.

A team slot is a fixed roster id (int), a reference `("w" | "l", match)` to the winner or loser of
an earlier match in the same run, or a seed `("s", n)` (an index into the run's seed order). A
match winner is `w` when set, else the side with the higher sum of the round's week scores (a tie
goes to t1). The champion wins the `p == 1` match; matches with `p > 1` (placement games) are
resolved but never counted in reach, win or bye shares.

Only the assumed 6-team template exists here (docs/decisions.md); other sizes and round types
plug in through `template_6`'s siblings and `round_weeks` without touching `resolve`.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

Slot = int | tuple[str, int] | None


@dataclass(frozen=True)
class Match:
    bracket: str
    r: int
    m: int
    t1: Slot = None
    t2: Slot = None
    w: int | None = None  # roster id of the winner once played
    l: int | None = None  # noqa: E741  (Sleeper's field name)
    p: int | None = None  # placement the winner takes: 1 title, 3 third place, 5 fifth place


@dataclass(frozen=True)
class BracketResult:
    champion: np.ndarray  # (S,) team index
    rounds: tuple[int, ...]
    p_reach: np.ndarray  # (len(rounds), T) share of runs a team plays a title-path match
    p_win: np.ndarray  # (len(rounds), T) share of runs a team wins one
    p_bye: np.ndarray  # (T,) share of runs a team's first title-path match is after round 1


def template_6(round_type: int = 0) -> tuple[Match, ...]:
    """Today's assumed 6-team bracket as Sleeper shapes it: 3 v 6 and 4 v 5, byes for 1 and 2
    (2 meets the 3/6 winner, 1 the 4/5 winner), the final, and the placement games."""
    if round_type != 0:
        raise ValueError(f"round type {round_type} has no template")
    return (
        Match("winners", 1, 1, ("s", 3), ("s", 6)),
        Match("winners", 1, 2, ("s", 4), ("s", 5)),
        Match("winners", 2, 3, ("s", 2), ("w", 1)),
        Match("winners", 2, 4, ("s", 1), ("w", 2)),
        Match("winners", 2, 5, ("l", 1), ("l", 2), p=5),
        Match("winners", 3, 6, ("w", 3), ("w", 4), p=1),
        Match("winners", 3, 7, ("l", 3), ("l", 4), p=3),
    )


def round_weeks(r: int, playoff_start: int, round_type: int = 0) -> tuple[int, ...]:
    """The NFL weeks whose scores decide round r (type 0: one week a round)."""
    if round_type != 0:
        raise ValueError(f"round type {round_type} is not supported")
    return (playoff_start + r - 1,)


def _slot(team: Any, kind: Any, source: Any) -> Slot:
    if team is not None:
        return int(team)
    if kind is not None and source is not None:
        return (str(kind), int(source))
    return None


def from_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[Match, ...]:
    """Matches from `playoff_brackets` rows (column names as in store.SCHEMAS)."""

    def opt(v: Any) -> int | None:
        return None if v is None else int(v)

    return tuple(
        Match(
            bracket=str(x["bracket"]),
            r=int(x["r"]),
            m=int(x["m"]),
            t1=_slot(x.get("t1"), x.get("t1_from_kind"), x.get("t1_from_m")),
            t2=_slot(x.get("t2"), x.get("t2_from_kind"), x.get("t2_from_m")),
            w=opt(x.get("w")),
            l=opt(x.get("l")),
            p=opt(x.get("p")),
        )
        for x in rows
    )


def is_title_path(match: Match) -> bool:
    return match.p is None or match.p == 1


def seeds_from(real: tuple[Match, ...], template: tuple[Match, ...]) -> list[int] | None:
    """Roster ids of seeds 1..N read off real rows laid over the template, or None if any seed
    has no fixed team."""
    found: dict[int, int] = {}
    by_key = {(m.r, m.m): m for m in real}
    for t in template:
        r = by_key.get((t.r, t.m))
        for mine, theirs in ((t.t1, r.t1 if r else None), (t.t2, r.t2 if r else None)):
            if isinstance(mine, tuple) and mine[0] == "s" and isinstance(theirs, int):
                found[mine[1]] = theirs
    n = max(s[1] for m in template for s in (m.t1, m.t2) if isinstance(s, tuple) and s[0] == "s")
    return [found[k] for k in range(1, n + 1)] if set(found) == set(range(1, n + 1)) else None


def resolve(
    matches: tuple[Match, ...],
    order: np.ndarray,
    scores: np.ndarray,
    column: dict[int, int],
    roster_ids: list[int],
    playoff_start: int,
) -> BracketResult:
    """Run the bracket in every simulated run. `order` (S, T): team index holding seed k+1;
    `scores` (T, W, S) with `column` week -> index; teams are indexes into `roster_ids`."""
    n_sims, n_teams = order.shape[0], scores.shape[0]
    run = np.arange(n_sims)
    index = {rid: i for i, rid in enumerate(roster_ids)}
    won: dict[int, np.ndarray] = {}
    lost: dict[int, np.ndarray] = {}

    def team(slot: Slot) -> np.ndarray:
        if slot is None:
            raise ValueError("bracket slot has no team or source")
        if isinstance(slot, int):
            return np.full(n_sims, index[slot])
        kind, n = slot
        return {"s": lambda: order[:, n - 1], "w": lambda: won[n], "l": lambda: lost[n]}[kind]()

    ordered = sorted(matches, key=lambda x: (x.r, x.m))
    rounds = tuple(sorted({m.r for m in ordered if is_title_path(m)}))
    in_round = {r: np.zeros((n_teams, n_sims), dtype=bool) for r in rounds}
    wins = {r: np.zeros((n_teams, n_sims), dtype=bool) for r in rounds}
    champion: np.ndarray | None = None
    for match in ordered:
        a, b = team(match.t1), team(match.t2)
        if match.w is not None:
            win = np.full(n_sims, index[match.w])
        else:
            weeks = [column[wk] for wk in round_weeks(match.r, playoff_start) if wk in column]
            if not weeks:
                raise ValueError(f"no simulated week for bracket round {match.r}")
            total = scores[:, weeks].sum(axis=1)  # (T, S)
            win = np.where(total[a, run] >= total[b, run], a, b)
        won[match.m], lost[match.m] = win, np.where(win == a, b, a)
        if is_title_path(match):
            in_round[match.r][a, run] = in_round[match.r][b, run] = True
            wins[match.r][win, run] = True
        if match.p == 1:
            champion = win
    if champion is None:
        raise ValueError("bracket has no final (p == 1)")
    none = np.zeros((n_teams, n_sims), dtype=bool)
    later = np.logical_or.reduce([in_round[r] for r in rounds[1:]] or [none])
    bye = later & ~in_round[rounds[0]]
    return BracketResult(
        champion=champion,
        rounds=rounds,
        p_reach=np.stack([in_round[r].mean(axis=1) for r in rounds]),
        p_win=np.stack([wins[r].mean(axis=1) for r in rounds]),
        p_bye=bye.mean(axis=1),
    )
