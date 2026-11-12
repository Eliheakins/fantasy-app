"""Reseeding each round and division-winner seeding (decisions.md 2026-11-12, PR 7)."""

from pathlib import Path

import numpy as np
import polars as pl

from fantasy.sim import bracket
from fantasy.sim.season import SeasonInputs, SeasonResult, simulate_season

N_SIMS = 5


def play(
    means: list[list[float]],
    playoff_teams: int,
    wins: list[float] | None = None,
    seed_type: int = 0,
    divisions: tuple[int, ...] = (),
    real: tuple[bracket.Match, ...] | None = None,
) -> SeasonResult:
    """Teams 1..n; mean score per playoff week from `means`, no noise. Seeds follow `wins`
    (default: team 1 best)."""
    n, n_weeks = len(means), len(means[0])
    wins = wins or [float(n - t) for t in range(n)]
    return simulate_season(
        SeasonInputs(
            roster_ids=list(range(1, n + 1)),
            weeks=list(range(3, 3 + n_weeks)),
            mean=np.array(means),
            noise_sd=np.zeros((n, n_weeks)),
            shift=np.zeros((n, n_weeks, N_SIMS)),
            pairs={},
            wins0=np.array(wins),
            points0=np.zeros(n),
            playoff_start=3,
            bracket=real,
            playoff_teams=playoff_teams,
            seed_type=seed_type,
            divisions=divisions,
        )
    )


def winners_of_round(res: SeasonResult, r: int) -> set[int]:
    return {int(t) for t in np.flatnonzero(res.p_win[res.rounds.index(r)] > 0.5)}


# Round 1 upsets in the 8-team bracket: seed 5 beats 4 and seed 7 beats 2, leaving seeds 1, 3, 5, 7.
# The template then plays 1 v 5 and 7 v 3; reseeding plays 1 v 7 and 3 v 5.
EIGHT: list[list[float]] = [  # round 1, 2, 3 mean points per team (index = seed - 1)
    [100, 100, 0], [60, 0, 0], [80, 90, 0], [60, 0, 0],
    [70, 80, 0], [10, 0, 0], [70, 95, 0], [10, 0, 0],
]  # fmt: skip
# 6-team: seed 6 beats 3, leaving 1, 2, 4, 6 (4 v 5 goes to 4). Template: 2 v 6 and 1 v 4;
# reseeding: 1 v 6 and 2 v 4.
SIX: list[list[float]] = [[0, 100, 0], [0, 90, 0], [10, 0, 0], [70, 80, 0], [10, 0, 0], [70, 95, 0]]


def test_reseeding_off_follows_the_template_8() -> None:
    assert winners_of_round(play(EIGHT, 8), 2) == {0, 6}


def test_reseeding_pairs_the_top_seed_with_the_lowest_remaining_8() -> None:
    assert winners_of_round(play(EIGHT, 8, seed_type=1), 2) == {0, 2}


def test_reseeding_off_follows_the_template_6() -> None:
    assert winners_of_round(play(SIX, 6), 2) == {0, 5}


def test_reseeding_pairs_the_top_seed_with_the_lowest_remaining_6() -> None:
    assert winners_of_round(play(SIX, 6, seed_type=1), 2) == {0, 1}


def test_real_rows_win_over_reseeding_once_trusted() -> None:
    real = bracket.template(8)
    assert winners_of_round(play(EIGHT, 8, seed_type=1, real=real), 2) == {0, 6}


def test_a_division_winner_with_a_worse_record_takes_a_spot_and_is_seeded_by_record() -> None:
    # teams 1-4 are one division (winner: 1); teams 5-6 the other (winner: 5, 2 wins)
    res = play([[0, 0]] * 6, 4, wins=[6, 5, 4, 3, 2, 1], divisions=(1, 1, 1, 1, 2, 2))
    assert res.p_playoffs.tolist() == [1, 1, 1, 0, 1, 0]  # team 5 in, team 4 (3 wins) out
    assert res.p_seed[4, 3] == 1  # seeded 4th, by record, below the teams it beat out


def test_without_divisions_the_better_record_keeps_the_spot() -> None:
    res = play([[0, 0]] * 6, 4, wins=[6, 5, 4, 3, 2, 1])
    assert res.p_playoffs.tolist() == [1, 1, 1, 1, 0, 0]


def test_a_division_winner_is_seeded_by_record_not_first() -> None:
    res = play([[0, 0]] * 6, 4, wins=[6, 5, 1, 4, 3, 2], divisions=(1, 2, 2, 2, 1, 1))
    assert res.p_seed[1, 0] == 0 and res.p_seed[0, 0] == 1  # team 1 (6 wins) stays seed 1
    assert res.p_playoffs.tolist() == [1, 1, 0, 1, 1, 0]  # winners 1 and 2; then 4 (4 wins), 5


def test_division_winner_key_ignores_teams_with_no_division() -> None:
    key = np.array([[3.0], [2.0], [1.0]])
    assert bracket.with_division_winners(key, (0, 0, 0), 2).argmax() == 0


def test_divisions_load_only_for_a_league_with_divisions(tmp_path: Path) -> None:
    from fantasy import store
    from fantasy.sim.league_data import _load_divisions

    frame = pl.DataFrame(
        {"league_id": ["L", "M"], "roster_id": [1, 1], "division": [2, 1]},
        schema=store.SCHEMAS["roster_divisions"],
    )
    assert _load_divisions("L", '{"divisions": 2}', tmp_path) == {}  # no table: no divisions
    store.write_table("roster_divisions", frame, "raw", tmp_path)
    assert _load_divisions("L", '{"divisions": 2}', tmp_path) == {1: 2}
    assert _load_divisions("L", '{"divisions": 1}', tmp_path) == {}
    assert _load_divisions("L", None, tmp_path) == {}
