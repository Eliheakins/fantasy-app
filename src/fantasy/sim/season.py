"""Monte Carlo season simulation: wins, seeding, bracket, title odds.

Team score in a week = mean + persistent shift + noise_sd * z. The shift is a player-level error
that stays the same across the remaining weeks of one simulated season (a projection that is wrong
is wrong all year), so weeks are not independent. z is keyed by (seed, roster, week), so two runs
with the same seed share random numbers wherever the inputs are unchanged. That makes the difference
between two scenarios (a trade, a waiver add) much less noisy than the odds themselves.

Seeding: wins, then points for, ties broken at random, unless `seeds` holds the real seeds (the
bracket is seeded). The bracket is `sim/bracket.py`: the assumed 4, 6 or 8-team template (6 teams:
seeds 1 and 2 skip round 1; 3 v 6 and 4 v 5; then 1 v winner(4/5), 2 v winner(3/6); the final)
or, once seeded, Sleeper's real rows with played games fixed. Playoff weeks already played arrive
as zero-noise means (realized points); standings count weeks before `playoff_start` only.
"""

from dataclasses import dataclass

import numpy as np
import polars as pl

from fantasy.sim.bracket import Match, resolve, template, with_division_winners

N_PLAYOFF_TEAMS = 6  # the default size (research scripts)


@dataclass(frozen=True)
class SeasonInputs:
    roster_ids: list[int]  # length T
    weeks: list[int]  # simulated weeks in order: regular season, then the bracket's playoff weeks
    mean: np.ndarray  # (T, W) expected team score, realized points included
    noise_sd: np.ndarray  # (T, W) weekly noise
    shift: np.ndarray  # (T, W, S) persistent player-error shift, zeros if none
    pairs: dict[int, list[tuple[int, int]]]  # regular-season week -> [(index a, index b)]
    wins0: np.ndarray  # (T,) wins from completed weeks
    points0: np.ndarray  # (T,) points for from completed weeks
    playoff_start: int
    seed: int = 0
    # real winners rows once trusted; None: the template for playoff_teams and round_type (the
    # one case where seed_type reseeding applies)
    bracket: tuple[Match, ...] | None = None
    seeds: tuple[int, ...] | None = None  # roster ids of seeds 1..N when the bracket is seeded
    playoff_teams: int = 6
    round_type: int = 0  # Sleeper's playoff_round_type
    seed_type: int = 0  # Sleeper's playoff_seed_type: 1 reseeds each round
    divisions: tuple[int, ...] = ()  # division per team (index as roster_ids), empty: none


@dataclass(frozen=True)
class SeasonResult:
    p_playoffs: np.ndarray  # (T,)
    p_bye: np.ndarray
    p_title: np.ndarray
    exp_wins: np.ndarray
    p_seed: np.ndarray  # (T, T): share of runs in which team t takes seed k+1
    made_playoffs: np.ndarray  # (T, S) bool, per run, for paired error estimates
    champion: np.ndarray  # (S,) index of the title winner in each run
    rounds: tuple[int, ...]  # bracket rounds that count toward the title
    p_reach: np.ndarray  # (rounds, T)
    p_win: np.ndarray  # (rounds, T) won a game


def noise_matrix(roster_ids: list[int], weeks: list[int], n_sims: int, seed: int) -> np.ndarray:
    """Standard normals (T, W, S), each (roster, week) cell seeded on its own."""
    z = np.empty((len(roster_ids), len(weeks), n_sims))
    for t, roster_id in enumerate(roster_ids):
        for w, week in enumerate(weeks):
            z[t, w] = np.random.default_rng([seed, roster_id, week]).standard_normal(n_sims)
    return z


def team_scores(inp: SeasonInputs) -> np.ndarray:
    """Simulated team scores (T, W, S): mean + persistent shift + noise."""
    z = noise_matrix(inp.roster_ids, inp.weeks, inp.shift.shape[2], inp.seed)
    scores: np.ndarray = inp.mean[:, :, None] + inp.shift + inp.noise_sd[:, :, None] * z
    return scores


def simulate_season(inp: SeasonInputs) -> SeasonResult:
    """Simulate inp.shift.shape[2] seasons."""
    n_teams = len(inp.roster_ids)
    n_sims = inp.shift.shape[2]
    scores = team_scores(inp)
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

    # seeds: wins, then points for, then a random tie-break; real seeds, once known, come first
    rng = np.random.default_rng([inp.seed, 99_999])
    key = wins * 1e6 + points + rng.uniform(0, 1e-3, size=wins.shape)
    index = {rid: i for i, rid in enumerate(inp.roster_ids)}
    if any(inp.divisions) and not inp.seeds:  # division winners are guaranteed a spot
        key = with_division_winners(key, inp.divisions, inp.playoff_teams)
    for k, rid in enumerate(inp.seeds or ()):
        key[index[rid]] = 1e10 - k
    order = np.argsort(-key, axis=0).T  # (S, T): order[s, k] = team index with seed k+1

    matches = inp.bracket or template(inp.playoff_teams, inp.round_type)
    reseed = inp.seed_type == 1 and inp.bracket is None  # real rows, once trusted, are the truth
    out = resolve(
        matches, order, scores, column, inp.roster_ids, inp.playoff_start, inp.round_type, reseed
    )

    def share(chosen: np.ndarray) -> np.ndarray:
        shares: np.ndarray = np.bincount(chosen.ravel(), minlength=n_teams) / n_sims
        return shares

    made = np.zeros((n_teams, n_sims), dtype=bool)
    for k in range(inp.playoff_teams):
        made[order[:, k], np.arange(n_sims)] = True

    return SeasonResult(
        p_playoffs=share(order[:, : inp.playoff_teams]),
        p_bye=out.p_bye,
        p_title=share(out.champion),
        exp_wins=wins.mean(axis=1),
        p_seed=np.stack([share(order[:, k]) for k in range(n_teams)], axis=1),
        made_playoffs=made,
        champion=out.champion,
        rounds=out.rounds,
        p_reach=out.p_reach,
        p_win=out.p_win,
    )


CONDITIONAL_SCHEMA = {
    "week": pl.Int64,
    "winner_id": pl.Int64,
    "loser_id": pl.Int64,
    "roster_id": pl.Int64,
    "n_runs": pl.Int64,
    "p_condition": pl.Float64,
    "p_playoffs": pl.Float64,
    "p_title": pl.Float64,
}


def conditional_odds(
    inp: SeasonInputs, result: SeasonResult, scores: np.ndarray | None = None
) -> pl.DataFrame:
    """Every team's playoff and title odds given each outcome of each remaining regular-season
    matchup: the runs where that side won (ties drop out), averaged. One row per (matchup
    outcome, team); p_condition is the share of runs, n_runs the runs behind the averages.
    `scores` is `team_scores(inp)` when the caller already has it."""
    scores = team_scores(inp) if scores is None else scores
    column = {week: w for w, week in enumerate(inp.weeks)}
    n_teams, n_sims = scores.shape[0], scores.shape[2]
    ids = inp.roster_ids
    rows = []
    for week, pairs in inp.pairs.items():
        if week not in column:
            continue
        for a, b in pairs:
            sa, sb = scores[a, column[week]], scores[b, column[week]]
            for win, lose, mask in ((a, b, sa > sb), (b, a, sb > sa)):
                n_runs = int(mask.sum())
                if n_runs == 0:
                    continue
                playoffs = result.made_playoffs[:, mask].mean(axis=1)
                titles = np.bincount(result.champion[mask], minlength=n_teams) / n_runs
                rows += [
                    (week, ids[win], ids[lose], ids[t], n_runs, n_runs / n_sims,
                     float(playoffs[t]), float(titles[t]))
                    for t in range(n_teams)
                ]  # fmt: skip
    return pl.DataFrame(rows, schema=CONDITIONAL_SCHEMA, orient="row")


WIN_NEED_SCHEMA = {
    "roster_id": pl.Int64,
    "n_games": pl.Int64,
    "wins": pl.Int64,
    "n_runs": pl.Int64,
    "p_condition": pl.Float64,
    "p_playoffs": pl.Float64,
}
NEED_GAMES = 4


def win_need_odds(
    inp: SeasonInputs,
    result: SeasonResult,
    horizon: int = NEED_GAMES,
    scores: np.ndarray | None = None,
) -> pl.DataFrame:
    """Each team's playoff odds given how many of its next `horizon` regular-season games it wins
    (a tie is not a win). Display only: it reads the draws and result the season run already made
    and changes nothing in them. One row per (team, wins) that happened in at least one run;
    p_condition is the share of runs, n_runs the runs behind p_playoffs. A team with no
    regular-season game left has no rows. `scores` is `team_scores(inp)` when the caller has it."""
    scores = team_scores(inp) if scores is None else scores
    column = {week: w for w, week in enumerate(inp.weeks)}
    n_sims = scores.shape[2]
    games: dict[int, list[tuple[int, int]]] = {t: [] for t in range(len(inp.roster_ids))}
    for week in sorted(w for w in inp.pairs if w in column):
        for a, b in inp.pairs[week]:
            games[a].append((column[week], b))
            games[b].append((column[week], a))
    rows = []
    for t, schedule in games.items():
        ahead = schedule[:horizon]
        if not ahead:
            continue
        wins = sum((scores[t, w] > scores[opp, w]).astype(int) for w, opp in ahead)
        for k in range(len(ahead) + 1):
            mask = wins == k
            n_runs = int(mask.sum())
            if n_runs:
                rows.append(
                    (inp.roster_ids[t], len(ahead), k, n_runs, n_runs / n_sims,
                     float(result.made_playoffs[t, mask].mean()))
                )  # fmt: skip
    return pl.DataFrame(rows, schema=WIN_NEED_SCHEMA, orient="row")
