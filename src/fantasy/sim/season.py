"""Monte Carlo season simulation: wins, 6-team seeding, bracket, title odds.

Team score in a week = mean + persistent shift + noise_sd * z. The shift is a player-level error
that stays the same across the remaining weeks of one simulated season (a projection that is wrong
is wrong all year), so weeks are not independent. z is keyed by (seed, roster, week), so two runs
with the same seed share random numbers wherever the inputs are unchanged. That makes the difference
between two scenarios (a trade, a waiver add) much less noisy than the odds themselves.

Seeding: wins, then points for, ties broken at random. Bracket (assumed, see decisions.md): seeds 1
and 2 skip the first playoff week; round 1 is 3 v 6 and 4 v 5; then 1 v winner(4/5), 2 v
winner(3/6); the final is the next week.
"""

from dataclasses import dataclass

import numpy as np

N_PLAYOFF_TEAMS = 6
BYE_SEEDS = 2


@dataclass(frozen=True)
class SeasonInputs:
    roster_ids: list[int]  # length T
    weeks: list[int]  # simulated weeks in order, regular season then the three playoff weeks
    mean: np.ndarray  # (T, W) expected team score, realized points included
    noise_sd: np.ndarray  # (T, W) weekly noise
    shift: np.ndarray  # (T, W, S) persistent player-error shift, zeros if none
    pairs: dict[int, list[tuple[int, int]]]  # regular-season week -> [(index a, index b)]
    wins0: np.ndarray  # (T,) wins from completed weeks
    points0: np.ndarray  # (T,) points for from completed weeks
    playoff_start: int
    seed: int = 0


@dataclass(frozen=True)
class SeasonResult:
    p_playoffs: np.ndarray  # (T,)
    p_bye: np.ndarray
    p_title: np.ndarray
    exp_wins: np.ndarray
    p_seed: np.ndarray  # (T, T): share of runs in which team t takes seed k+1
    made_playoffs: np.ndarray  # (T, S) bool, per run, for paired error estimates
    champion: np.ndarray  # (S,) index of the title winner in each run


def noise_matrix(roster_ids: list[int], weeks: list[int], n_sims: int, seed: int) -> np.ndarray:
    """Standard normals (T, W, S), each (roster, week) cell seeded on its own."""
    z = np.empty((len(roster_ids), len(weeks), n_sims))
    for t, roster_id in enumerate(roster_ids):
        for w, week in enumerate(weeks):
            z[t, w] = np.random.default_rng([seed, roster_id, week]).standard_normal(n_sims)
    return z


def simulate_season(inp: SeasonInputs) -> SeasonResult:
    """Simulate inp.shift.shape[2] seasons."""
    n_teams = len(inp.roster_ids)
    n_sims = inp.shift.shape[2]
    z = noise_matrix(inp.roster_ids, inp.weeks, n_sims, inp.seed)
    scores = inp.mean[:, :, None] + inp.shift + inp.noise_sd[:, :, None] * z  # (T, W, S)
    column = {week: w for w, week in enumerate(inp.weeks)}

    wins = np.broadcast_to(inp.wins0[:, None], (n_teams, n_sims)).astype(float)
    points = np.broadcast_to(inp.points0[:, None], (n_teams, n_sims)).astype(float)
    for week, pairs in inp.pairs.items():
        for a, b in pairs:
            sa, sb = scores[a, column[week]], scores[b, column[week]]
            wins[a] += (sa > sb) + 0.5 * (sa == sb)
            wins[b] += (sb > sa) + 0.5 * (sa == sb)
    for week in inp.weeks:
        if week < inp.playoff_start:
            points += scores[:, column[week]]

    # seeds: wins, then points for, then a random tie-break
    rng = np.random.default_rng([inp.seed, 99_999])
    key = wins * 1e6 + points + rng.uniform(0, 1e-3, size=wins.shape)
    order = np.argsort(-key, axis=0).T  # (S, T): order[s, k] = team index with seed k+1

    def winner(team_a: np.ndarray, team_b: np.ndarray, week: int) -> np.ndarray:
        s = scores[:, column[week]].T  # (S, T)
        idx = np.arange(n_sims)
        return np.where(s[idx, team_a] >= s[idx, team_b], team_a, team_b)

    w1, w2, w3 = inp.playoff_start, inp.playoff_start + 1, inp.playoff_start + 2
    seed1, seed2, seed3, seed4, seed5, seed6 = (order[:, k] for k in range(N_PLAYOFF_TEAMS))
    win_36 = winner(seed3, seed6, w1)
    win_45 = winner(seed4, seed5, w1)
    finalist_1 = winner(seed1, win_45, w2)
    finalist_2 = winner(seed2, win_36, w2)
    champion = winner(finalist_1, finalist_2, w3)

    def share(chosen: np.ndarray) -> np.ndarray:
        return np.bincount(chosen.ravel(), minlength=n_teams) / n_sims

    made = np.zeros((n_teams, n_sims), dtype=bool)
    for k in range(N_PLAYOFF_TEAMS):
        made[order[:, k], np.arange(n_sims)] = True

    return SeasonResult(
        p_playoffs=share(order[:, :N_PLAYOFF_TEAMS]),
        p_bye=share(order[:, :BYE_SEEDS]),
        p_title=share(champion),
        exp_wins=wins.mean(axis=1),
        p_seed=np.stack([share(order[:, k]) for k in range(n_teams)], axis=1),
        made_playoffs=made,
        champion=champion,
    )
