"""Pure functions behind the League page: all_play, best_actual, conditional_odds."""

import itertools
import random

import numpy as np
import polars as pl
import pytest
from test_season import inputs

from fantasy.sim import lineup as lu
from fantasy.sim import schedule as s
from fantasy.sim.lineup import Player
from fantasy.sim.season import conditional_odds, simulate_season

SCHEMA = {
    "league_id": pl.String,
    "week": pl.Int64,
    "roster_id": pl.Int64,
    "matchup_id": pl.Int64,
    "points": pl.Float64,
}
SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX", "K", "DEF", "BN", "BN"]


def matchups(rows: list[tuple[int, int, int | None, float]]) -> pl.DataFrame:
    return pl.DataFrame([("L", *r) for r in rows], schema=SCHEMA, orient="row")


def test_all_play_counts_ties_skips_null_matchups_and_drops_a_zero_week() -> None:
    games = matchups(
        [
            (1, 1, 1, 100.0), (1, 2, 1, 90.0), (1, 3, 2, 90.0), (1, 4, 2, 70.0),
            (2, 1, 1, 60.0), (2, 2, 1, 50.0), (2, 3, None, 999.0), (2, 4, 2, 10.0),
            (3, 1, 1, 0.0), (3, 2, 1, 0.0), (3, 3, 2, 0.0), (3, 4, 2, 0.0),
            (4, 1, 1, 500.0), (4, 2, 1, 1.0),
        ]
    )  # fmt: skip
    out = s.all_play(games, through_week=3)
    row = {r["roster_id"]: r for r in out.iter_rows(named=True)}
    assert (row[1]["weeks"], row[1]["ap_wins"], row[1]["ap_losses"], row[1]["wins"]) == (2, 5, 0, 2)
    assert (row[2]["ap_wins"], row[2]["ap_ties"], row[2]["ap_losses"]) == (2, 1, 2)
    assert (row[2]["wins"], row[2]["losses"]) == (0, 2)
    assert (row[3]["weeks"], row[3]["wins"], row[3]["ap_ties"]) == (1, 1, 1)  # null week skipped
    assert (row[4]["wins"], row[4]["losses"], row[4]["ap_losses"]) == (
        0,
        1,
        5,
    )  # no actual game in week 2


def test_all_play_actual_ties_are_counted_separately() -> None:
    games = matchups([(1, 1, 1, 80.0), (1, 2, 1, 80.0), (1, 3, 2, 70.0), (1, 4, 2, 90.0)])
    out = {r["roster_id"]: r for r in s.all_play(games, 1).iter_rows(named=True)}
    assert (out[1]["ties"], out[1]["ap_ties"], out[1]["ap_wins"]) == (1, 1, 1)


def test_all_play_of_nothing_is_an_empty_frame_with_columns() -> None:
    out = s.all_play(matchups([]), 3)
    assert out.is_empty() and "ap_wins" in out.columns


def test_best_actual_matches_brute_force_with_flex_superflex_k_and_def() -> None:
    rng = random.Random(3)
    skill_slots = lu.lineup_slots(SLOTS)
    for _ in range(25):
        kinds = rng.choices(["QB", "RB", "WR", "TE", "K", "DEF"], k=14)
        players = [
            lu.ActualPlayer(f"p{i}", (pos,), round(rng.uniform(0, 30), 1))
            for i, pos in enumerate(kinds)
        ]
        skill = [p for p in players if p.positions[0] not in ("K", "DEF")]
        constants = sum(
            max((p.points for p in players if p.positions[0] == kind), default=0.0)
            for kind in ("K", "DEF")
        )
        best = max(
            lu.auto_lineup(
                [Player(p.id, p.positions[0], p.points) for p in combo], skill_slots
            ).total
            for combo in itertools.combinations(skill, min(len(skill_slots), len(skill)))
        )
        assert lu.best_actual(players, SLOTS) == pytest.approx(constants + best)


def test_best_actual_uses_the_position_that_helps_a_multi_position_player() -> None:
    players = [
        lu.ActualPlayer("hill", ("QB", "TE"), 20.0),
        lu.ActualPlayer("te", ("TE",), 25.0),
        lu.ActualPlayer("qb", ("QB",), 5.0),
    ]
    assert lu.best_actual(players, ["QB", "TE"]) == 45.0


def test_best_actual_takes_the_top_n_kickers_and_an_empty_roster_is_zero() -> None:
    ks = [lu.ActualPlayer(f"k{i}", ("K",), float(i)) for i in range(3)]
    assert lu.best_actual(ks, ["K", "K"]) == 3.0
    assert lu.best_actual([], ["QB", "K"]) == 0.0


def test_conditional_odds_average_back_to_the_plain_odds_and_gaps_pick_the_winner() -> None:
    mean = np.array([140.0, 60.0, 100, 100, 100, 100, 100, 100])
    inp = inputs(mean, 15.0, n_sims=6000)
    res = simulate_season(inp)
    cond = conditional_odds(inp, res)
    assert cond.columns == [
        *("week", "winner_id", "loser_id", "roster_id"),
        *("n_runs", "p_condition", "p_playoffs", "p_title"),
    ]
    # week 1 pairs team 3 with team 6
    both = cond.filter(
        (cond["week"] == 1)
        & cond["winner_id"].is_in([3, 6])
        & cond["loser_id"].is_in([3, 6])
        & (cond["roster_id"] == 3)
    )
    assert both.height == 2
    assert both["p_condition"].sum() == pytest.approx(1.0)  # continuous scores never tie
    assert (both["p_condition"] * both["p_playoffs"]).sum() == pytest.approx(res.p_playoffs[2])
    assert (both["p_condition"] * both["p_title"]).sum() == pytest.approx(res.p_title[2])
    won = both.filter(pl.col("winner_id") == 3)["p_playoffs"][0]
    lost = both.filter(pl.col("winner_id") == 6)["p_playoffs"][0]
    assert won > lost
    # team 1 (mean 140) against team 8 (100): almost always the winner
    gap = cond.filter((cond["week"] == 1) & (cond["winner_id"] == 1) & (cond["roster_id"] == 1))
    assert gap["p_condition"][0] > 0.9 and gap["n_runs"][0] == round(gap["p_condition"][0] * 6000)
    assert cond["week"].max() == 7  # regular season only
