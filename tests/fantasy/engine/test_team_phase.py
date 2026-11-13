"""`team_phase`: the one classifier for a team's playoff state (B, audit fixes for #82)."""

from typing import Any

import pytest

from fantasy._bracket import team_phase
from fantasy.sim.bracket import Match, from_rows

START, WEEKS = 15, 3  # a 6-team bracket with one-week rounds: weeks 15, 16, 17


def _rows(winners: list[dict[str, Any]], losers: list[dict[str, Any]]) -> tuple[Match, ...]:
    tagged = [("winners", r) for r in winners] + [("losers", r) for r in losers]
    return from_rows([{"bracket": kind, **r} for kind, r in tagged])


def _w(r: int, m: int, **over: Any) -> dict[str, Any]:
    return {"r": r, "m": m, **over}


# seeds 1 to 6 are rosters 1 to 6; rosters 7 and 8 play a losers-bracket game; 9 is in no row
ROUND_ONE = [
    _w(1, 1, t1=3, t2=6), _w(1, 2, t1=4, t2=5),
    _w(2, 3, t1=2, t2_from_kind="w", t2_from_m=1), _w(2, 4, t1=1, t2_from_kind="w", t2_from_m=2),
    _w(2, 5, p=5, t1_from_kind="l", t1_from_m=1, t2_from_kind="l", t2_from_m=2),
    _w(3, 6, p=1, t1_from_kind="w", t1_from_m=3, t2_from_kind="w", t2_from_m=4),
    _w(3, 7, p=3, t1_from_kind="l", t1_from_m=3, t2_from_kind="l", t2_from_m=4),
]  # fmt: skip
LOSERS = [_w(1, 1, t1=7, t2=8)]
PLAYED_ONE = [_w(1, 1, t1=3, t2=6, w=3, l=6), _w(1, 2, t1=4, t2=5, w=5, l=4)]
ROUND_TWO = [*PLAYED_ONE, _w(2, 3, t1=2, t2=3), _w(2, 4, t1=1, t2=5),
             _w(2, 5, p=5, t1=6, t2=4), *ROUND_ONE[5:]]  # fmt: skip
PENDING_PLACEMENT = [*ROUND_TWO[:4], ROUND_ONE[4], *ROUND_ONE[5:]]  # 5th place still references
NO_PLACEMENT = [*ROUND_TWO[:4], *ROUND_ONE[5:]]  # a bracket with no 5th place game
FINISHED = [*PLAYED_ONE, _w(2, 3, t1=2, t2=3, w=2, l=3), _w(2, 4, t1=1, t2=5, w=1, l=5),
            _w(3, 6, p=1, t1=2, t2=1, w=1, l=2), _w(3, 7, p=3, t1=3, t2=5, w=5, l=3)]  # fmt: skip


@pytest.mark.parametrize(
    ("winners", "losers", "roster", "week", "phase"),
    [
        (ROUND_ONE, LOSERS, 3, START - 1, "regular"),
        (ROUND_ONE, LOSERS, 3, START, "playing"),
        (ROUND_ONE, LOSERS, 1, START, "bye"),
        (ROUND_ONE, LOSERS, 7, START, "consolation"),  # a losers-bracket game
        (ROUND_TWO, [], 6, START + 1, "consolation"),  # a placement game in the winners bracket
        (ROUND_ONE, LOSERS, 9, START, "eliminated"),  # round 1 fully seeded, my team in no row
        (NO_PLACEMENT, [], 6, START + 1, "eliminated"),  # lost and no game this week
        (FINISHED, [], 1, START + 2, "champion"),  # the final is decided
        (FINISHED, [], 2, START + 2, "playing"),  # the final's loser still shows the final
        (FINISHED, [], 1, START + WEEKS, "champion"),
        (FINISHED, [], 2, START + WEEKS, "over"),  # runner-up after the final
        (FINISHED, [], 9, START + WEEKS, "over"),
        ([], [], 3, START + WEEKS, "over"),  # the calendar alone ends the season
        ([], [], 3, START, None),  # no fixed rows yet
        (ROUND_ONE, LOSERS, 3, START + 1, None),  # my round-two slot is still "winner of 1"
        (PENDING_PLACEMENT, [], 6, START + 1, None),  # 5th place slot is still "loser of 1"
        (ROUND_ONE, LOSERS, 7, START + 1, None),  # no losers game in round two yet
    ],
)
def test_team_phase_needs_positive_evidence(
    winners: list[dict[str, Any]],
    losers: list[dict[str, Any]],
    roster: int,
    week: int,
    phase: str | None,
) -> None:
    got = team_phase(
        _rows(winners, losers), roster_id=roster, week=week, playoff_start=START,
        playoff_weeks=WEEKS, round_type=0,
    )  # fmt: skip
    assert got == phase
