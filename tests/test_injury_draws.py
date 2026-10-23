import numpy as np
import pytest
from test_odds import toy_league

from fantasy.sim import odds
from fantasy.sim.sampler import LEVELS, Slate, correlation_matrix, sample_points
from fantasy.sim.winprob import choose

RATIOS = {"WR": -np.log(1 - LEVELS)}  # mean ratio about 1


def _draw(play_probs: tuple[float, ...]) -> np.ndarray:
    slate = Slate(("a", "b"), ("WR", "WR"), ("X", "Y"), ("WR1", "WR1"), (10.0, 10.0), play_probs)
    corr = correlation_matrix(slate, {}, {}, {})
    return sample_points(slate, corr, RATIOS, 100_000, seed=3)


def test_everyone_playing_matches_the_default_draws_exactly() -> None:
    assert np.array_equal(_draw((1.0, 1.0)), _draw(()))


def test_a_player_with_play_probability_keeps_his_mean_and_scores_zero_when_out() -> None:
    draws = _draw((0.76, 1.0))
    assert draws[:, 0].mean() == pytest.approx(10.0, rel=0.03)  # no double discount
    assert (draws[:, 0] == 0).mean() == pytest.approx(0.24, abs=0.01)
    assert (draws[:, 1] == 0).mean() < 0.01
    assert _draw((0.0, 1.0))[:, 0].max() == 0.0


def test_a_players_play_decision_is_the_same_in_every_scenario() -> None:
    first, second = _draw((0.5, 1.0)), _draw((0.5, 0.9))
    assert np.array_equal(first[:, 0] == 0, second[:, 0] == 0)


def test_absence_path_follows_status_then_a_chain_with_the_stated_long_run_rate() -> None:
    path = odds.absence_path("p", 0.76, 40, 40_000, 0, 0.07, 0.55)
    assert path[0].mean() == pytest.approx(0.24, abs=0.01)
    assert path[-1].mean() == pytest.approx(0.07 / (0.07 + 1 - 0.55), abs=0.01)
    assert np.array_equal(path, odds.absence_path("p", 0.76, 40, 40_000, 0, 0.07, 0.55))
    other = odds.absence_path("q", 0.76, 40, 40_000, 0, 0.07, 0.55)
    assert not np.array_equal(path, other)


def test_no_hazard_leaves_the_season_inputs_unchanged_and_hazard_only_lowers_later_weeks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = toy_league()
    monkeypatch.setattr(odds, "HAZARD", 0.0)
    plain = odds.build_inputs(data, None, n_sims=500, seed=1)
    monkeypatch.setattr(odds, "HAZARD", 0.07)
    absent = odds.build_inputs(data, None, n_sims=500, seed=1)
    assert np.array_equal(plain.shift[:, 0], absent.shift[:, 0])  # the current week is unchanged
    assert (absent.shift[:, 1:] <= plain.shift[:, 1:] + 1e-9).all()  # absences only subtract
    assert absent.shift[:, 1:].mean() < plain.shift[:, 1:].mean()
    drop = plain.shift[:, 1:] - absent.shift[:, 1:]
    assert (drop <= absent.mean[:, 1:, None] + 1e-9).all()  # never more than the lineup is worth


def test_playoff_and_title_odds_still_sum_to_six_and_one_with_absences() -> None:
    result, _ = odds.league_odds(toy_league(), n_sims=2000)
    assert result.p_playoffs.sum() == pytest.approx(6.0)
    assert result.p_title.sum() == pytest.approx(1.0)


def test_a_challenger_that_does_not_win_on_held_out_draws_is_not_recommended() -> None:
    rng = np.random.default_rng(5)
    base, other = frozenset({"a"}), frozenset({"b"})
    noise = rng.standard_normal(10_000)
    totals = {base: 100 + 10 * noise, other: 100 + 10 * noise}
    totals[other] = totals[other].copy()
    totals[other][:5_000] += 3.0  # better on the first half only
    verdict = choose([base, other], base, totals, 100 + 10 * rng.standard_normal(10_000))
    assert verdict.tag == "same as max points" and verdict.chosen == base
