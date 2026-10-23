import numpy as np
import pytest

from fantasy.sim.season import SeasonInputs, simulate_season

N_TEAMS = 8
REGULAR = [1, 2, 3, 4, 5, 6, 7]
WEEKS = [*REGULAR, 8, 9, 10]  # playoffs start in week 8


def round_robin_pairs() -> dict[int, list[tuple[int, int]]]:
    """Seven weeks, every team plays every other team once (circle method)."""
    teams = list(range(N_TEAMS))
    pairs = {}
    for week in REGULAR:
        pairs[week] = [(teams[i], teams[N_TEAMS - 1 - i]) for i in range(N_TEAMS // 2)]
        teams = [teams[0], teams[-1], *teams[1:-1]]
    return pairs


def inputs(
    mean: np.ndarray, noise: float, n_sims: int = 4000, seed: int = 0, shift_sd: float = 0.0
) -> SeasonInputs:
    shift = shift_sd * np.random.default_rng(5).standard_normal((N_TEAMS, len(WEEKS), n_sims))
    return SeasonInputs(
        roster_ids=list(range(1, N_TEAMS + 1)),
        weeks=WEEKS,
        mean=np.broadcast_to(mean[:, None], (N_TEAMS, len(WEEKS))).copy(),
        noise_sd=np.full((N_TEAMS, len(WEEKS)), noise),
        shift=shift,
        pairs=round_robin_pairs(),
        wins0=np.zeros(N_TEAMS),
        points0=np.zeros(N_TEAMS),
        playoff_start=8,
        seed=seed,
    )


def test_probabilities_sum_to_six_playoff_spots_two_byes_and_one_title() -> None:
    res = simulate_season(inputs(np.full(N_TEAMS, 100.0), 20.0))
    assert res.p_playoffs.sum() == pytest.approx(6.0)
    assert res.p_bye.sum() == pytest.approx(2.0)
    assert res.p_title.sum() == pytest.approx(1.0)


def test_equal_teams_get_equal_odds_within_monte_carlo_error() -> None:
    res = simulate_season(inputs(np.full(N_TEAMS, 100.0), 20.0, n_sims=20000))
    assert res.p_playoffs == pytest.approx(np.full(N_TEAMS, 0.75), abs=0.02)
    assert res.p_title == pytest.approx(np.full(N_TEAMS, 0.125), abs=0.015)
    assert res.exp_wins == pytest.approx(np.full(N_TEAMS, 3.5), abs=0.1)


def test_without_noise_the_strongest_team_wins_everything() -> None:
    mean = np.arange(N_TEAMS, dtype=float) * 10  # team 7 is best, team 0 worst
    res = simulate_season(inputs(mean, 0.0))
    assert res.p_title[N_TEAMS - 1] == 1.0 and res.p_title.sum() == 1.0
    assert res.p_playoffs[[0, 1]].sum() == 0.0  # the two worst never qualify
    assert res.exp_wins[N_TEAMS - 1] == 7.0 and res.exp_wins[0] == 0.0


def test_better_teams_have_better_odds() -> None:
    mean = np.linspace(90, 110, N_TEAMS)
    res = simulate_season(inputs(mean, 15.0, n_sims=10000))
    assert np.all(np.diff(res.p_title) > -0.01)
    assert res.p_title[-1] > 2 * res.p_title[0]


def test_same_seed_reproduces_and_boosting_a_team_raises_its_odds() -> None:
    base = np.full(N_TEAMS, 100.0)
    a = simulate_season(inputs(base, 20.0, seed=3))
    b = simulate_season(inputs(base, 20.0, seed=3))
    assert np.array_equal(a.p_title, b.p_title)
    boosted = base.copy()
    boosted[0] += 8
    c = simulate_season(inputs(boosted, 20.0, seed=3))
    assert c.p_title[0] - a.p_title[0] > 0.02


def test_persistent_error_spreads_odds_across_teams() -> None:
    mean = np.full(N_TEAMS, 100.0)
    flat = simulate_season(inputs(mean, 20.0, n_sims=6000))
    shared = simulate_season(inputs(mean, 20.0, n_sims=6000, shift_sd=15.0))
    # a shift that is the same all season helps a team every week, so results polarize
    assert shared.exp_wins.std() >= flat.exp_wins.std() - 0.01
    assert shared.p_playoffs.sum() == pytest.approx(6.0)
