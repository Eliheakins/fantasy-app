import numpy as np

from fantasy.sim.sampler import LEVELS, Slate, correlation_matrix, sample_points
from fantasy.sim.winprob import choose, feasible, swap_candidates

POSITIONS = {"qb": "QB", "wr1": "WR", "wr2": "WR", "rb": "RB", "te": "TE"}
SLOTS = ["QB", "WR", "FLEX"]
# a skewed marginal whose mean ratio is about 1: quantiles of an exponential(1) draw
RATIOS = {p: -np.log(1 - LEVELS) for p in ("QB", "WR", "RB", "TE")}


def _slate(teams: tuple[str, ...]) -> Slate:
    return Slate(
        ids=("qb", "wr1", "wr2"),
        positions=("QB", "WR", "WR"),
        teams=teams,
        roles=("QB1", "WR1", "WR2"),
        means=(20.0, 12.0, 8.0),
    )


def test_sample_means_match_projections_and_teammates_correlate():
    slate = _slate(("A", "A", "A"))
    same = {("QB1", "WR1"): 0.6, ("WR1", "QB1"): 0.6}
    corr = correlation_matrix(slate, same, {}, {})
    points = sample_points(slate, corr, RATIOS, 200_000, seed=1)
    assert np.allclose(points.mean(axis=0) / np.array([20, 12, 8]), 1.0, atol=0.03)
    assert abs(np.corrcoef(points[:, 0], points[:, 1])[0, 1] - 0.55) < 0.1
    assert abs(np.corrcoef(points[:, 0], points[:, 2])[0, 1]) < 0.02


def test_opposing_players_use_opposing_correlations_and_strangers_none():
    slate = _slate(("A", "B", "C"))
    opposing = {("QB1", "WR1"): 0.5, ("WR1", "QB1"): 0.5}
    corr = correlation_matrix(slate, {}, opposing, {"A": "B", "B": "A"})
    assert corr[0, 1] == corr[1, 0] and corr[0, 1] > 0.4
    assert corr[0, 2] == 0.0


def test_correlation_matrix_is_repaired_to_a_valid_matrix():
    slate = _slate(("A", "A", "A"))
    bad = {("QB1", "WR1"): 0.9, ("QB1", "WR2"): 0.9, ("WR1", "WR2"): -0.9}
    corr = correlation_matrix(slate, {**bad, **{(b, a): r for (a, b), r in bad.items()}}, {}, {})
    assert np.linalg.eigvalsh(corr).min() > 0
    assert np.allclose(np.diag(corr), 1.0)


def test_feasible_and_swaps_respect_slots_and_locks():
    base = frozenset({"qb", "wr1", "wr2"})
    swaps = swap_candidates(base, ["rb", "te"], POSITIONS, SLOTS, locked={"wr1"})
    assert frozenset({"qb", "wr1", "rb"}) in swaps  # wr2 -> rb fits FLEX
    assert frozenset({"qb", "te", "wr2"}) not in swaps  # wr1 is locked
    assert not feasible(frozenset({"qb", "rb", "te"}), POSITIONS, SLOTS)  # no WR slot filler


def test_choose_picks_the_high_variance_lineup_for_an_underdog():
    rng = np.random.default_rng(0)
    steady, boom = frozenset({"a"}), frozenset({"b"})
    totals = {
        steady: 90 + 5 * rng.standard_normal(40_000),
        boom: 90 + 30 * rng.standard_normal(40_000),
    }
    opponent = 110 + 10 * rng.standard_normal(40_000)
    verdict = choose([steady, boom], baseline=steady, totals=totals, opponent=opponent)
    assert verdict.chosen == boom
    assert verdict.win_prob[boom] > verdict.win_prob[steady]
    assert verdict.tag in {"clear", "lean", "toss-up"}


def test_choose_says_same_when_the_baseline_is_best():
    rng = np.random.default_rng(1)
    a, b = frozenset({"a"}), frozenset({"b"})
    totals = {a: 100 + 5 * rng.standard_normal(20_000), b: 90 + 5 * rng.standard_normal(20_000)}
    verdict = choose(
        [a, b], baseline=a, totals=totals, opponent=95 + 5 * rng.standard_normal(20_000)
    )
    assert verdict.chosen == a and verdict.tag == "same as max points"


def test_search_climbs_through_successive_improvements_and_returns_everything_it_saw() -> None:
    from fantasy.sim.winprob import search

    a, b, c, d = "a", "b", "c", "d"
    base, mid, top = frozenset({a, b}), frozenset({c, b}), frozenset({c, d})
    worth = {base: 0.40, mid: 0.45, top: 0.50, frozenset({a, d}): 0.30}
    graph = {base: [mid, frozenset({a, d})], mid: [top, base], top: [mid]}
    found = search(base, lambda x: graph[x], lambda x: worth.get(x, 0.0))
    assert top in found and mid in found and frozenset({a, d}) in found


def test_search_stops_when_no_neighbor_improves_enough() -> None:
    from fantasy.sim.winprob import search

    base, other = frozenset({"a"}), frozenset({"b"})
    found = search(base, lambda x: [other], lambda x: 0.5 + (0.0005 if x == other else 0.0))
    assert set(found) == {base, other}  # looked at, but not moved to (gain below min_gain)


def test_ceiling_and_floor_picks_favor_spread_and_steadiness() -> None:
    from fantasy.sim.winprob import pick_by_quantile

    rng = np.random.default_rng(3)
    steady, boom = frozenset({"s"}), frozenset({"b"})
    totals = {
        steady: 100 + 5 * rng.standard_normal(20_000),
        boom: 100 + 25 * rng.standard_normal(20_000),
    }
    assert pick_by_quantile([steady, boom], totals, 0.9)[0] == boom
    assert pick_by_quantile([steady, boom], totals, 0.1)[0] == steady
    chosen, held = pick_by_quantile([steady, boom], totals, 0.9)
    assert held[chosen] > held[steady]  # and it holds on the half not used to choose


def test_the_sampler_gives_each_size_tier_its_own_floor_and_ceiling() -> None:
    slate = Slate(
        ids=("small", "big"),
        positions=("WR", "WR"),
        teams=("X", "Y"),
        roles=("WR1", "WR1"),
        means=(10.0, 10.0),
        tiers=(0, 2),
    )
    corr = correlation_matrix(slate, {}, {}, {})
    steady = 0.7 + 0.6 * LEVELS  # ratios from 0.7 to 1.3
    duds = np.where(LEVELS < 0.8, 0.1, 3.0 + 10 * (LEVELS - 0.8))  # mostly 0.1, then a long tail
    draws = sample_points(slate, corr, {"WR": steady, "WR:0": duds, "WR:2": steady}, 50_000, 0)
    assert (
        np.quantile(draws[:, 0], 0.5) < 2.0 < np.quantile(draws[:, 1], 0.5)
    )  # small median far below
    assert np.quantile(draws[:, 0], 0.97) > 3 * np.quantile(draws[:, 1], 0.97) * 0.7  # but upside


def test_a_players_draws_do_not_change_when_other_players_join_the_slate() -> None:
    alone = Slate(("a",), ("WR",), ("X",), ("WR1",), (10.0,))
    crowd = Slate(("b", "a"), ("WR", "WR"), ("Y", "X"), ("WR1", "WR1"), (7.0, 10.0))
    draws_alone = sample_points(alone, correlation_matrix(alone, {}, {}, {}), RATIOS, 1000, 5)
    corr = correlation_matrix(crowd, {}, {}, {})
    draws_crowd = sample_points(crowd, corr, RATIOS, 1000, 5)
    assert np.array_equal(draws_alone[:, 0], draws_crowd[:, 1])
