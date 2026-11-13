"""Playoff bracket engine: Sleeper-shaped matches resolved over simulated runs.

A team slot is a fixed roster id (int), a reference `("w" | "l", match)` to the winner or loser of
an earlier match in the same run, or a seed `("s", n)` (1-based seed n in the run's seed order). A
match winner is `w` when set, else the side with the higher sum of the round's week scores (a tie
goes to t1). The champion wins the `p == 1` match; matches with `p > 1` (placement games) are
resolved but never counted in reach, win or bye shares.

Templates exist for 4, 6 and 8 teams; the round type (one- or two-week rounds, a round decided by
the sum of its weeks) only changes `round_weeks`.
"""

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

import numpy as np

# a roster id, ("s", seed), ("w" | "l", match id) for the winner or loser of that match, or None
SlotKind = Literal["s", "w", "l"]
Slot = int | tuple[SlotKind, int] | None


@dataclass(frozen=True)
class Match:
    """One game as Sleeper lays it out: round `r`, match id `m`, sides `t1` and `t2`."""

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


ROUNDS = {4: 2, 6: 3, 8: 3}  # rounds in the winners bracket by playoff teams
LAST_PLAYOFF_WEEK = 17  # project and sync stop at week 17
ROUND_TYPES = (0, 1, 2)  # Sleeper's playoff_round_type; semantics in docs/decisions.md
SEED_TYPES = (0, 1)  # Sleeper's playoff_seed_type: 0 reseeding off, 1 on (decisions.md 2026-11-12)
DIVISION_BONUS = 1e9  # lifts a playoff team's sort key above every non-qualifier's


def _match(r: int, m: int, t1: Slot, t2: Slot, p: int | None = None) -> Match:
    return Match("winners", r, m, t1, t2, p=p)


def _seed(n: int) -> Slot:
    return ("s", n)


def _winner_of(n: int) -> Slot:
    return ("w", n)


def _loser_of(n: int) -> Slot:
    return ("l", n)


def template(playoff_teams: int, round_type: int = 0) -> tuple[Match, ...]:
    """The assumed winners bracket as Sleeper lays it out. The shape does not depend on the round
    type (it only sets how many weeks a round lasts). Placement games below 3rd are left out
    except 6-team's 5th place: they never change title odds."""
    if round_type not in ROUND_TYPES:
        raise ValueError(f"round type {round_type} has no template")
    if playoff_teams == 4:
        return (
            _match(1, 1, _seed(1), _seed(4)), _match(1, 2, _seed(2), _seed(3)),
            _match(2, 3, _winner_of(1), _winner_of(2), 1),
            _match(2, 4, _loser_of(1), _loser_of(2), 3),
        )  # fmt: skip
    if playoff_teams == 6:
        return (
            _match(1, 1, _seed(3), _seed(6)), _match(1, 2, _seed(4), _seed(5)),
            _match(2, 3, _seed(2), _winner_of(1)), _match(2, 4, _seed(1), _winner_of(2)),
            _match(2, 5, _loser_of(1), _loser_of(2), 5),
            _match(3, 6, _winner_of(3), _winner_of(4), 1),
            _match(3, 7, _loser_of(3), _loser_of(4), 3),
        )  # fmt: skip
    if playoff_teams == 8:
        return (
            _match(1, 1, _seed(1), _seed(8)), _match(1, 2, _seed(4), _seed(5)),
            _match(1, 3, _seed(2), _seed(7)), _match(1, 4, _seed(3), _seed(6)),
            _match(2, 5, _winner_of(1), _winner_of(2)), _match(2, 6, _winner_of(3), _winner_of(4)),
            _match(3, 7, _winner_of(5), _winner_of(6), 1),
            _match(3, 8, _loser_of(5), _loser_of(6), 3),
        )  # fmt: skip
    raise ValueError(f"no template for {playoff_teams} playoff teams")


def _spans(n_rounds: int, round_type: int) -> tuple[int, ...]:
    """Weeks per round: type 0 one each, 1 a two-week final, 2 two weeks every round."""
    if round_type not in ROUND_TYPES:
        raise ValueError(f"round type {round_type} is not supported")
    return tuple(2 if round_type == 2 or (round_type == 1 and r == n_rounds) else 1
                 for r in range(1, n_rounds + 1))  # fmt: skip


def playoff_weeks(playoff_teams: int, round_type: int = 0) -> int:
    """Weeks the bracket lasts (0 for a size it has no template for)."""
    n = ROUNDS.get(playoff_teams)
    return sum(_spans(n, round_type)) if n else 0


def round_weeks(r: int, playoff_start: int, round_type: int, n_rounds: int) -> tuple[int, ...]:
    """The NFL weeks whose scores decide round r (summed when there are two)."""
    spans = _spans(n_rounds, round_type)
    first = playoff_start + sum(spans[: r - 1])
    return tuple(range(first, first + spans[r - 1]))


def round_of_week(week: int, playoff_start: int, round_type: int, n_rounds: int) -> int:
    """The round a playoff week belongs to (beyond the last round: n_rounds + 1)."""
    for r in range(1, n_rounds + 1):
        if week in round_weeks(r, playoff_start, round_type, n_rounds):
            return r
    return n_rounds + 1


def settings_dict(settings_json: str | None) -> dict[str, Any]:
    """`leagues.settings` as a dict; unreadable or missing settings read as empty."""
    try:
        settings = json.loads(settings_json) if settings_json else {}
    except json.JSONDecodeError:
        return {}
    return settings if isinstance(settings, dict) else {}


def round_type_of(settings_json: str | None) -> int:
    """Sleeper's playoff_round_type from `leagues.settings`; missing or odd reads as 0."""
    value = settings_dict(settings_json).get("playoff_round_type")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def shape_problem(
    num_teams: int | None,
    playoff_teams: int | None,
    playoff_week_start: int | None,
    round_type: int | None = 0,
    seed_type: int | None = 0,
    divisions: int | None = 0,
) -> str | None:
    """Why the simulation cannot model a league, in words fit to show, or None when it can.
    The one gate for the add-time check, the simulate stage and the data loader."""
    if not playoff_teams:
        return "This league has no playoff bracket (it may use weekly eliminations)."
    if playoff_teams not in ROUNDS:
        return (
            "Only leagues with a 4, 6 or 8-team playoff are supported "
            f"(this one has {playoff_teams})."
        )
    if num_teams is None or num_teams < playoff_teams:
        return f"The league needs at least {playoff_teams} teams."
    round_type = round_type or 0
    if round_type not in ROUND_TYPES:
        return f"This league's playoff round setting ({round_type}) is not supported."
    if (seed_type or 0) not in SEED_TYPES:
        return f"This league's playoff seeding setting ({seed_type}) is not supported."
    if divisions and divisions > playoff_teams:
        return f"This league has more divisions ({divisions}) than playoff spots ({playoff_teams})."
    weeks = playoff_weeks(playoff_teams, round_type)
    last_start = LAST_PLAYOFF_WEEK - weeks + 1
    if playoff_week_start is None or not 1 <= playoff_week_start <= last_start:
        return (
            f"The playoff start week must be between 1 and {last_start} for a {weeks}-week bracket."
        )
    return None


def row_problem(league: Mapping[str, Any]) -> str | None:
    """`shape_problem` for a `leagues` table row (round type and divisions come from its JSON)."""
    settings = settings_dict(league.get("settings"))
    return shape_problem(
        league.get("num_teams"), league.get("playoff_teams"), league.get("playoff_week_start"),
        round_type_of(league.get("settings")), league.get("playoff_seed_type"),
        settings.get("divisions"),
    )  # fmt: skip


def _slot(team: Any, kind: Any, source: Any) -> Slot:
    if team is not None:
        return int(team)
    if kind is not None and source is not None:
        if kind not in ("s", "w", "l"):
            raise ValueError(f"unknown bracket slot kind {kind!r}")
        return (cast(SlotKind, kind), int(source))
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


def with_division_winners(
    key: np.ndarray, divisions: tuple[int, ...], playoff_teams: int
) -> np.ndarray:
    """Sort keys (T, S) with every playoff team lifted above the rest: each division's best key
    is guaranteed a spot, the other spots go to the best remaining keys, and the lifted teams
    keep their own order. `divisions[t]` is team t's division (0: none, never a winner)."""
    division = np.asarray(divisions)
    runs = np.arange(key.shape[1])
    winners = key.copy()
    for d in set(divisions) - {0}:
        members = np.flatnonzero(division == d)
        winners[members[np.argmax(key[members], axis=0)], runs] += DIVISION_BONUS
    qualified = np.argsort(-winners, axis=0)[:playoff_teams]
    lifted = key.copy()
    lifted[qualified, runs] += DIVISION_BONUS
    return lifted


def _reseeded(
    ordered: list[Match], r: int, team: Callable[[Slot], np.ndarray], seed_of: np.ndarray,
    run: np.ndarray,
) -> dict[int, tuple[np.ndarray, np.ndarray]]:  # fmt: skip
    """Round r's title-path matches re-paired per run: best remaining seed v worst, and so on."""
    games = [m for m in ordered if m.r == r and is_title_path(m)]
    teams = np.stack([team(slot) for g in games for slot in (g.t1, g.t2)], axis=1)  # (S, 2k)
    best_first = np.take_along_axis(teams, np.argsort(seed_of[run[:, None], teams], axis=1), axis=1)
    return {g.m: (best_first[:, i], best_first[:, -1 - i]) for i, g in enumerate(games)}


def resolve(
    matches: tuple[Match, ...],
    order: np.ndarray,
    scores: np.ndarray,
    column: dict[int, int],
    roster_ids: list[int],
    playoff_start: int,
    round_type: int = 0,
    reseed: bool = False,
) -> BracketResult:
    """Run the bracket in every simulated run. `order` (S, T): team index holding seed k+1;
    `scores` (T, W, S) with `column` week -> index; teams are indexes into `roster_ids`.
    `reseed` re-pairs each title-path round after the first: the teams left (byes included) play
    highest seed v lowest, next highest v next lowest. Placement games keep their template slots."""
    n_sims, n_teams = order.shape[0], scores.shape[0]
    run = np.arange(n_sims)
    index = {rid: i for i, rid in enumerate(roster_ids)}
    n_rounds = max(m.r for m in matches)
    won: dict[int, np.ndarray] = {}
    lost: dict[int, np.ndarray] = {}
    pairing: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    seed_of = np.empty_like(order)  # (S, T): seed index of each team
    seed_of[run[:, None], order] = np.arange(n_teams)

    def team(slot: Slot) -> np.ndarray:
        if slot is None:
            raise ValueError("bracket slot has no team or source")
        if isinstance(slot, int):
            return np.full(n_sims, index[slot])
        kind, n = slot
        if kind == "s":
            return order[:, n - 1]
        return won[n] if kind == "w" else lost[n]

    ordered = sorted(matches, key=lambda x: (x.r, x.m))
    rounds = tuple(sorted({m.r for m in ordered if is_title_path(m)}))
    in_round = {r: np.zeros((n_teams, n_sims), dtype=bool) for r in rounds}
    wins = {r: np.zeros((n_teams, n_sims), dtype=bool) for r in rounds}
    champion: np.ndarray | None = None
    for match in ordered:
        if reseed and match.r > 1 and is_title_path(match) and match.m not in pairing:
            pairing.update(_reseeded(ordered, match.r, team, seed_of, run))
        a, b = pairing[match.m] if match.m in pairing else (team(match.t1), team(match.t2))
        if match.w is not None:
            win = np.full(n_sims, index[match.w])
        else:
            weeks = [
                column[wk]
                for wk in round_weeks(match.r, playoff_start, round_type, n_rounds)
                if wk in column
            ]
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
