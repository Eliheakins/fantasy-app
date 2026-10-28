from dataclasses import replace
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from fantasy import store
from fantasy.sim import odds
from fantasy.sim.lineup import Player
from fantasy.stages import simulate as sim_stage

N_TEAMS = 8
POSITIONS = {"qb": "QB", "rb1": "RB", "rb2": "RB", "wr1": "WR", "wr2": "WR", "te": "TE"}
VALUE = {"QB": 20.0, "RB": 14.0, "WR": 13.0, "TE": 8.0}
WEEKS = list(range(1, 11))  # regular season 1 to 7, playoffs 8 to 10


def toy_league(boost_team: int | None = None, boost: float = 0.0) -> odds.LeagueData:
    rows, proj = [], []
    for rid in range(1, N_TEAMS + 1):
        for key, pos in POSITIONS.items():
            gid = f"t{rid}_{key}"
            rows.append((rid, gid, pos))
            extra = boost if rid == boost_team else 0.0
            proj += [(gid, w, VALUE[pos] + extra) for w in WEEKS]
    teams = list(range(N_TEAMS))
    pairings = {}
    for week in range(1, 8):  # circle-method round robin on roster ids 1..8
        pairings[week] = [(teams[i] + 1, teams[N_TEAMS - 1 - i] + 1) for i in range(N_TEAMS // 2)]
        teams = [teams[0], teams[-1], *teams[1:-1]]
    return odds.LeagueData(
        roster_ids=list(range(1, N_TEAMS + 1)),
        team_names={r: f"Team {r}" for r in range(1, N_TEAMS + 1)},
        current_week=1,
        playoff_start=8,
        roster_positions=["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF", "BN"],
        rosters=pl.DataFrame(rows, schema=["roster_id", "gsis_id", "position"], orient="row"),
        projections=pl.DataFrame(proj, schema=["gsis_id", "week", "projection"], orient="row"),
        cv={"QB": 0.5, "RB": 0.7, "WR": 0.7, "TE": 0.8},
        pair_rho={("QB1", "WR1"): 0.35, ("WR1", "QB1"): 0.35},
        pairings=pairings,
        wins0={r: 0.0 for r in range(1, N_TEAMS + 1)},
        points0={r: 0.0 for r in range(1, N_TEAMS + 1)},
        k_mean=8.0,
        k_var=16.0,
        def_mean=8.0,
        def_var=25.0,
    )


def test_a_single_player_has_variance_from_his_projection() -> None:
    mean, var, persistent = odds.lineup_moments([Player("a", "WR", 10.0)], {"WR": 0.7}, {})
    assert (mean, var) == (10.0, pytest.approx(49.0))
    assert persistent == odds.TAU["WR"] ** 2


def test_correlated_teammates_have_more_variance_than_independent_ones() -> None:
    pair = [Player("q", "QB", 20.0), Player("w", "WR", 14.0)]
    cv = {"QB": 0.5, "WR": 0.7}
    _, independent, _ = odds.lineup_moments(pair, cv, {})
    _, stacked, _ = odds.lineup_moments(pair, cv, {("QB1", "WR1"): 0.35, ("WR1", "QB1"): 0.35})
    assert stacked - independent == pytest.approx(2 * 0.35 * 10.0 * 9.8)


def test_player_error_is_reproducible_per_player_and_seed() -> None:
    a1, a2 = odds.player_error("x", 100, 1), odds.player_error("x", 100, 1)
    assert np.array_equal(a1, a2)
    assert not np.array_equal(a1, odds.player_error("y", 100, 1))
    assert not np.array_equal(a1, odds.player_error("x", 100, 2))


def test_inputs_have_one_mean_per_team_and_week_including_playoff_weeks() -> None:
    inputs = odds.build_inputs(toy_league(), None, n_sims=200, seed=0)
    assert inputs.mean.shape == (N_TEAMS, 10) and inputs.shift.shape == (N_TEAMS, 10, 200)
    # QB 20 + RB 14 + 14 + WR 13 + 13 + TE 8 + FLEX 0 (nobody left) + K 8 + DEF 8
    assert inputs.mean[0, 0] == pytest.approx(20 + 28 + 26 + 8 + 16)
    assert set(inputs.pairs) == set(range(1, 8))


def test_a_teams_own_kicker_and_defense_projection_replaces_the_league_mean() -> None:
    data = replace(toy_league(), kd_slot={("K", 1, 1): 11.0, ("DEF", 1, 1): 2.0})
    inputs = odds.build_inputs(data, None, n_sims=50, seed=0)
    assert inputs.mean[0, 0] == pytest.approx(20 + 28 + 26 + 8 + 13)  # K 11 + DEF 2
    assert inputs.mean[0, 1] == pytest.approx(20 + 28 + 26 + 8 + 16)  # no entry for week 2
    assert inputs.mean[1, 0] == pytest.approx(20 + 28 + 26 + 8 + 16)  # nor for team 2


def test_odds_sum_to_six_two_and_one_and_equal_teams_are_close() -> None:
    result = odds.league_odds(toy_league(), n_sims=8000)
    assert result.p_playoffs.sum() == pytest.approx(6.0)
    assert result.p_bye.sum() == pytest.approx(2.0)
    assert result.p_title.sum() == pytest.approx(1.0)
    assert result.p_title == pytest.approx(np.full(N_TEAMS, 0.125), abs=0.03)


def test_a_stronger_roster_raises_title_odds_and_same_seed_reuses_draws() -> None:
    base = odds.league_odds(toy_league(), n_sims=8000, seed=1)
    better = odds.league_odds(toy_league(boost_team=1, boost=3.0), n_sims=8000, seed=1)
    assert better.p_title[0] - base.p_title[0] > 0.04
    again = odds.league_odds(toy_league(), n_sims=8000, seed=1)
    assert np.array_equal(base.p_title, again.p_title)


def test_realized_points_in_the_current_week_replace_the_projection() -> None:
    data = toy_league()
    scored = odds.CurrentWeek(realized=50.0, open_players=(), open_k=0, open_def=0)
    data = replace(data, current={1: scored})
    inputs = odds.build_inputs(data, None, n_sims=100, seed=0)
    assert inputs.mean[0, 0] == pytest.approx(50.0)  # nothing left to play
    assert inputs.mean[1, 0] > 90.0  # other teams are unchanged


def test_history_appends_and_never_overwrites(tmp_path: Path) -> None:
    row = ("L", "Team 1", 1, 7, 100, 0.5, 0.1, 0.05, 4.0)
    latest = pl.DataFrame([row], schema=store.SCHEMAS["sim_season"], orient="row")
    first = sim_stage.append_history(latest, tmp_path)
    second = sim_stage.append_history(latest, tmp_path)
    assert first.height == 1 and second.height == 2
    assert store.read_table("sim_season_history", "archive", tmp_path).height == 2


def test_a_big_projection_uses_its_own_size_tiers_spread() -> None:
    tiers = {"WR": ((6.0, 1.0), (12.0, 0.8), (1e9, 0.4))}
    steady = odds.lineup_moments([Player("a", "WR", 10.0)], {"WR": 0.7}, {}, tiers)
    erratic = odds.lineup_moments([Player("b", "WR", 4.0)], {"WR": 0.7}, {}, tiers)
    huge = odds.lineup_moments([Player("c", "WR", 20.0)], {"WR": 0.7}, {}, tiers)
    assert steady[1] == pytest.approx((10.0 * 0.8) ** 2)
    assert erratic[1] == pytest.approx((4.0 * 1.0) ** 2)
    assert huge[1] == pytest.approx((20.0 * 0.4) ** 2)
    unlisted = odds.lineup_moments([Player("d", "QB", 10.0)], {"QB": 0.5}, {}, tiers)
    assert unlisted[1] == pytest.approx(25.0)  # a position without tiers keeps its pooled spread


def test_persistent_variance_of_a_game_in_progress_scales_with_the_share_left() -> None:
    from fantasy.sim.odds import TAU, lineup_moments

    players = [Player("a", "WR", 5.0), Player("b", "WR", 8.0)]
    cv = {"WR": 0.5}
    _, _, full = lineup_moments(players, cv, {})
    _, _, half = lineup_moments(players, cv, {}, shares={"a": 0.5})
    assert full == pytest.approx(2 * TAU["WR"] ** 2)
    assert half == pytest.approx(TAU["WR"] ** 2 * (1 + 0.25))
