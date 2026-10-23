"""Joint draws of player points for one week: a Gaussian copula over measured role correlations,
with each player's marginal taken from the empirical quantiles of actual over projected points.

Teammates and opposing players are correlated by role pair (QB1 with WR1 and so on, from
`correlation_pairs`); everyone else is independent. Draws are seeded, so two lineups scored on
the same sample see the same weeks (common random numbers).
"""

import zlib
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

LEVELS = np.round(np.arange(1, 100) / 100, 2)  # quantile levels stored in `marginals`
MIN_EIGENVALUE = 1e-6


@dataclass(frozen=True)
class Slate:
    """Players in one matchup with their roles, NFL teams and projected means."""

    ids: tuple[str, ...]
    positions: tuple[str, ...]
    teams: tuple[str, ...]
    roles: tuple[str, ...]  # "WR1", or "" for a depth player with no measured correlations
    means: tuple[float, ...]  # expected points counting the chance of not playing
    play_probs: tuple[float, ...] = ()  # chance each plays; empty means everyone plays
    tiers: tuple[int, ...] = ()  # size tier of each player's projection; empty means all one shape


def correlation_matrix(
    slate: Slate,
    same_team: dict[tuple[str, str], float],
    opposing: dict[tuple[str, str], float],
    opponent_of: dict[str, str],
) -> np.ndarray:
    """Role-pair correlations, made positive semi-definite and rescaled to a unit diagonal."""
    n = len(slate.ids)
    corr = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            key = (slate.roles[i], slate.roles[j])
            if slate.teams[i] == slate.teams[j]:
                rho = same_team.get(key, 0.0)
            elif opponent_of.get(slate.teams[i]) == slate.teams[j]:
                rho = opposing.get(key, 0.0)
            else:
                rho = 0.0
            corr[i, j] = corr[j, i] = rho
    values, vectors = np.linalg.eigh(corr)
    fixed = (vectors * np.clip(values, MIN_EIGENVALUE, None)) @ vectors.T
    scale = np.sqrt(np.diag(fixed))
    return fixed / np.outer(scale, scale)


def sample_points(
    slate: Slate,
    corr: np.ndarray,
    ratios: dict[str, np.ndarray],
    n_sims: int,
    seed: int,
) -> np.ndarray:
    """(n_sims, n_players) points. `ratios[position]` holds the quantiles at LEVELS.

    A player with play probability p scores 0 in a share 1 - p of draws and otherwise draws from
    his distribution with mean `mean / p`, so his overall mean is `mean`. Whether he plays comes
    from his own seeded stream, so it is the same in every scenario scored on these draws."""
    z = np.random.default_rng(seed).standard_normal((n_sims, len(slate.ids)))
    u = norm.cdf(z @ np.linalg.cholesky(corr).T)
    probs = slate.play_probs or (1.0,) * len(slate.ids)
    tiers = slate.tiers or (-1,) * len(slate.ids)
    out = np.empty_like(u)
    for j, (pid, position, mean, p, tier) in enumerate(
        zip(slate.ids, slate.positions, slate.means, probs, tiers, strict=True)
    ):
        shape = ratios.get(f"{position}:{tier}", ratios[position])
        if p <= 0.0:
            out[:, j] = 0.0
            continue
        plays = np.random.default_rng([seed, zlib.crc32(pid.encode())]).random(n_sims) < p
        out[:, j] = np.where(plays, (mean / p) * np.interp(u[:, j], LEVELS, shape), 0.0)
    return out
