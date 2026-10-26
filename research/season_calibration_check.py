"""Are the season odds calibrated? Production odds on built leagues against what then happens.

Leagues: `regret.py` construction A (the league's 10 teams, snake draft on prior-season points
over replacement plus noise, then weekly form-rule waiver swaps), DRAFTS drafts per league-season,
2024 and 2025, skill slots only (K and DEF left out of both the simulation and the outcome). Each
draft gets a random 10-team schedule for weeks 1 to 14 and the leagues' playoff format (6 teams,
seeds 1 and 2 on bye, weeks 15 to 17, `leagues` raw).

What happens: every week each team starts the best lineup by that week's `proj_learned`
projection (walk-forward, made before the game) from its roster that week, among players who
played; it scores their actual points. Standings, seeds and bracket as `sim/season.py`.

The odds: as of weeks 4, 7 and 10, `sim.odds.build_inputs` and `sim.season.simulate_season`
(production code) on a LeagueData holding only what was known then: that week's rosters, wins
and points so far, the remaining schedule, and flat projections (a player's projection for that
week if he plays it, else his latest one from the last STALE_WEEKS weeks, for every later week
his NFL team plays). Spreads, size tiers and teammate correlations refit with the
`distributions` stage code on seasons before the scored one only.

Variants (all on the same random draws): production (tau on, drift 2), tau off, drift 0 and 4,
and a churn term: a per-team random walk added to the persistent shift from the week after the
as-of week, step CHURN points a week (rosters keep changing, so team strength wanders).

Rule (fixed before the run): constants are fit on 2024 (drift among 0/2/4, churn step on the
grid, by playoff Brier) and tested on 2025; a change ships only if the 2025 paired bootstrap 95%
interval (drafts resampled within league) of the playoff Brier change excludes 0 and title log
loss is not worse.

Run from the repo root:  OMP_NUM_THREADS=3 uv run python research/season_calibration_check.py
"""

import sys
import time
from collections import defaultdict
from dataclasses import replace
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
import regret as rg  # noqa: E402

from fantasy import stat_line_table, store  # noqa: E402
from fantasy.sim import odds  # noqa: E402
from fantasy.sim.lineup import Player, auto_lineup, lineup_slots  # noqa: E402
from fantasy.sim.odds import LeagueData, build_inputs  # noqa: E402
from fantasy.sim.season import (  # noqa: E402
    N_PLAYOFF_TEAMS,
    SeasonInputs,
    simulate_season,
    team_scores,
)
from fantasy.stages import distributions as dist  # noqa: E402
from fantasy.stages.simulate import tier_spreads  # noqa: E402

SEASONS = (2024, 2025)
AS_OF = (4, 7, 10)
LAST_WEEK = 17
N_SIMS = 4000
STALE_WEEKS = 3  # a player with no game in this many weeks is treated as out for the season
PROD_DRIFT = odds.DRIFT_SD
PROD_TAU = dict(odds.TAU)
DRIFTS = (0.0, 2.0, 4.0)
CHURNS = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
BOOT = 2000
WORKERS = 3
EPS = 1.0 / N_SIMS
pl.Config(tbl_rows=100, tbl_cols=20, tbl_width_chars=200)


def variants() -> dict[str, tuple[bool, float, float]]:
    """name -> (tau on, drift, churn step)."""
    out = {"prod": (True, PROD_DRIFT, 0.0), "tau_off": (False, PROD_DRIFT, 0.0)}
    out |= {f"drift{d:g}": (True, d, 0.0) for d in DRIFTS if d != PROD_DRIFT}
    out |= {f"churn{c:g}": (True, PROD_DRIFT, c) for c in CHURNS}
    return out


# ---------------------------------------------------------------- league facts


def league_rows() -> list[dict]:
    rows = list(store.read_table("leagues", "raw").iter_rows(named=True))
    for r in rows:
        assert r["playoff_teams"] == N_PLAYOFF_TEAMS, r["playoff_teams"]
        assert r["waiver_type"] == 0, r["waiver_type"]  # rolling priority, no bids
    return rows


def skill_layout(roster_positions: list[str]) -> list[str]:
    return [s for s in roster_positions if s not in ("K", "DEF")]


def playoff_start() -> int:
    starts = {int(r["playoff_week_start"]) for r in league_rows()}
    assert len(starts) == 1, starts
    return starts.pop()


def shapes(lid: str, season: int) -> tuple[dict, dict, dict]:
    """(cv, tiers, same-team rho) refit on seasons before `season` with the stage's own code."""
    res = dist.residual_frame(store.projection_table(), store.read_table("player_points"))
    res = res.filter((pl.col("league_id") == lid) & (pl.col("season") < season))
    if stat_line_table.stored() is not None:
        res = dist.with_stat_line_flag(res, store.read_table("proj_baseline"))
    fitted = dist.shape_frame(res, dist.estimate_curves(res), store.projection_name())
    marg = dist.estimate_marginals(fitted)
    pairs = dist.estimate_pairs(dist.with_roles(fitted), store.read_table("team_games"))
    cv = dict(marg.filter(pl.col("tier") == -1).select("position", "cv").unique().iter_rows())
    rho: dict[tuple[str, str], float] = {}
    same = pairs.filter(pl.col("relation") == "same_team")
    for a, b, r in same.select("role_a", "role_b", "rho").iter_rows():
        rho[(a, b)] = rho[(b, a)] = r
    return cv, tier_spreads(marg), rho


def season_facts(lid: str, season: int) -> dict:
    """Per week: projections (players who played), actual points, NFL team; positions; byes."""
    proj = store.projection_table().filter(
        (pl.col("league_id") == lid)
        & (pl.col("season") == season)
        & ~pl.col("is_future")
        & pl.col("position").is_in(rg.POSITIONS)
        & (pl.col("week") <= LAST_WEEK)
    )
    points = store.read_table("player_points").filter(
        (pl.col("league_id") == lid) & (pl.col("season") == season)
    )
    rows = proj.join(
        points.select("gsis_id", "week", "points"), on=["gsis_id", "week"], how="left"
    ).with_columns(pl.col("points").fill_null(0.0))
    proj_w: dict[int, dict[str, float]] = defaultdict(dict)
    pts_w: dict[int, dict[str, float]] = defaultdict(dict)
    team_w: dict[int, dict[str, str]] = defaultdict(dict)
    # drafted players with no game this season still need a position
    earlier = store.read_table("player_points").filter(
        (pl.col("league_id") == lid) & (pl.col("season") <= season)
    )
    pos = dict(earlier.sort("season", "week").select("gsis_id", "position").iter_rows())
    for r in rows.iter_rows(named=True):
        proj_w[r["week"]][r["gsis_id"]] = r["projection"]
        pts_w[r["week"]][r["gsis_id"]] = r["points"]
        team_w[r["week"]][r["gsis_id"]] = r["team"]
        pos[r["gsis_id"]] = r["position"]
    sched = store.read_table("nfl_schedules", "raw").filter(
        (pl.col("season") == season) & (pl.col("game_type") == "REG")
    )
    plays: dict[str, set[int]] = defaultdict(set)
    for r in sched.iter_rows(named=True):
        plays[r["home_team"]].add(r["week"])
        plays[r["away_team"]].add(r["week"])
    return {"proj": dict(proj_w), "pts": dict(pts_w), "team": dict(team_w), "pos": pos,
            "plays": dict(plays)}  # fmt: skip


def flat_projections(facts: dict, week: int) -> list[tuple[str, int, float]]:
    """(gsis_id, week, projection) for `week` to LAST_WEEK as known before `week`."""
    latest: dict[str, tuple[float, str]] = {}
    for w in range(week, max(1, week - STALE_WEEKS) - 1, -1):
        for g, v in facts["proj"].get(w, {}).items():
            latest.setdefault(g, (v, facts["team"][w][g]))
    rows = [(g, week, v) for g, v in facts["proj"].get(week, {}).items()]
    for g, (v, team) in latest.items():
        rows += [(g, j, v) for j in range(week + 1, LAST_WEEK + 1) if j in facts["plays"][team]]
    return rows


# ---------------------------------------------------------------- the season that happens


def random_schedule(n_teams: int, weeks: int, rng: np.random.Generator) -> dict[int, list]:
    """Week -> pairs of team indexes: a shuffled round robin, repeated from the start."""
    order = list(rng.permutation(n_teams))
    rounds = []
    for _ in range(n_teams - 1):
        rounds.append([(order[i], order[n_teams - 1 - i]) for i in range(n_teams // 2)])
        order = [order[0], order[-1], *order[1:-1]]
    seq = list(rng.permutation(len(rounds)))
    seq = (seq * (weeks // len(seq) + 1))[:weeks]
    return {w + 1: [(int(a), int(b)) for a, b in rounds[r]] for w, r in enumerate(seq)}


def weekly_scores(
    rosters_by_week: dict[int, list[tuple[str, ...]]], facts: dict, slots: list[str]
) -> np.ndarray:
    """(T, LAST_WEEK) actual points of the lineup each team starts by projection."""
    n = len(rosters_by_week[1])
    out = np.zeros((n, LAST_WEEK))
    for w in range(1, LAST_WEEK + 1):
        proj, pts = facts["proj"].get(w, {}), facts["pts"].get(w, {})
        for t, roster in enumerate(rosters_by_week[w]):
            pool = [Player(g, facts["pos"][g], proj[g]) for g in roster if g in proj]
            out[t, w - 1] = sum(pts[g] for g in auto_lineup(pool, slots).players)
    return out


def standings(scores: np.ndarray, pairs: dict[int, list], through: int) -> tuple[np.ndarray, ...]:
    """(wins, points) after weeks 1 to `through`."""
    wins = np.zeros(scores.shape[0])
    for w in range(1, through + 1):
        for a, b in pairs[w]:
            sa, sb = scores[a, w - 1], scores[b, w - 1]
            wins[a] += (sa > sb) + 0.5 * (sa == sb)
            wins[b] += (sb > sa) + 0.5 * (sa == sb)
    return wins, scores[:, :through].sum(axis=1)


def outcome(scores: np.ndarray, pairs: dict[int, list], start: int) -> dict[str, np.ndarray]:
    """Made playoffs, champion, final wins: same seeding and bracket as sim/season.py."""
    wins, points = standings(scores, pairs, start - 1)
    seeds = list(np.lexsort((-points, -wins)))

    def winner(a: int, b: int, week: int) -> int:
        return a if scores[a, week - 1] >= scores[b, week - 1] else b

    s = seeds
    w36, w45 = winner(s[2], s[5], start), winner(s[3], s[4], start)
    champ = winner(winner(s[0], w45, start + 1), winner(s[1], w36, start + 1), start + 2)
    made = np.zeros(len(wins), dtype=bool)
    made[s[:N_PLAYOFF_TEAMS]] = True
    title = np.zeros(len(wins), dtype=bool)
    title[champ] = True
    return {"made": made, "title": title, "wins": wins}


# ---------------------------------------------------------------- the odds


def league_data(
    lg: dict, shape: tuple, facts: dict, rosters: list[tuple[str, ...]], week: int,
    scores: np.ndarray, pairs: dict[int, list], start: int,
) -> LeagueData:  # fmt: skip
    cv, tiers, rho = shape
    wins0, points0 = standings(scores, pairs, week - 1)
    ids = list(range(1, len(rosters) + 1))
    proj = pl.DataFrame(
        flat_projections(facts, week), schema=["gsis_id", "week", "projection"], orient="row"
    )
    positions = {g: facts["pos"][g] for g in proj["gsis_id"].unique()}
    roster_rows = [(t + 1, g, facts["pos"][g]) for t, r in enumerate(rosters) for g in r]
    return LeagueData(
        roster_ids=ids,
        team_names={i: str(i) for i in ids},
        current_week=week,
        playoff_start=start,
        roster_positions=skill_layout(lg["roster_positions"]),
        rosters=pl.DataFrame(
            roster_rows, schema={"roster_id": pl.Int64, "gsis_id": pl.String,
                                 "position": pl.String}, orient="row"
        ),  # fmt: skip
        projections=proj,
        cv=cv,
        pair_rho=rho,
        pairings={w: [(a + 1, b + 1) for a, b in p] for w, p in pairs.items() if w >= week},
        wins0={i: float(wins0[i - 1]) for i in ids},
        points0={i: float(points0[i - 1]) for i in ids},
        k_mean=0.0, k_var=0.0, def_mean=0.0, def_var=0.0,  # fmt: skip
        positions=positions,
        league_id=lg["league_id"],
        cv_tiers=tiers,
    )


def inputs(data: LeagueData, seed: int, tau_on: bool) -> SeasonInputs:
    """Production build_inputs with drift 0 (added per variant) and tau on or off."""
    odds.DRIFT_SD = 0.0
    odds.TAU = PROD_TAU if tau_on else dict.fromkeys(PROD_TAU, 0.0)
    try:
        return build_inputs(data, None, N_SIMS, seed)
    finally:
        odds.DRIFT_SD, odds.TAU = PROD_DRIFT, PROD_TAU


def variant_inputs(base: SeasonInputs, drift: float, churn: float) -> SeasonInputs:
    noise = np.sqrt(base.noise_sd**2 + drift**2)
    shift = base.shift
    if churn > 0:
        steps = np.random.default_rng([base.seed, 4242]).standard_normal(base.shift.shape)
        steps[:, 0] = 0.0  # this week's rosters are set
        shift = shift + churn * np.cumsum(steps, axis=1)
    return replace(base, noise_sd=noise, shift=shift)


def sim_wins(inp: SeasonInputs) -> np.ndarray:
    """(T, S) final regular-season wins per run, as simulate_season counts them."""
    scores = team_scores(inp)
    column = {week: w for w, week in enumerate(inp.weeks)}
    wins = np.broadcast_to(inp.wins0[:, None], scores[:, 0].shape).astype(float)
    for week, pairs in inp.pairs.items():
        for a, b in pairs:
            sa, sb = scores[a, column[week]], scores[b, column[week]]
            wins[a] += (sa > sb) + 0.5 * (sa == sb)
            wins[b] += (sb > sa) + 0.5 * (sa == sb)
    return wins


# ---------------------------------------------------------------- workers

_STATE: dict = {}


def _init(shape_by: dict) -> None:
    _STATE["shapes"] = shape_by
    _STATE["leagues"] = {r["league_id"]: r for r in league_rows()}
    _STATE["facts"] = {}
    _STATE["start"] = playoff_start()


def _facts(lid: str, season: int) -> dict:
    key = (lid, season)
    if key not in _STATE["facts"]:
        _STATE["facts"][key] = season_facts(lid, season)
    return _STATE["facts"][key]


def unit_seed(lid: str, season: int, draft: int) -> int:
    return (int(lid) % 9973) * 10**6 + (season - 2000) * 10**4 + draft * 10


def run_unit(unit: tuple) -> list[dict]:
    """One league-season draft: the actual season and the odds as of each AS_OF week."""
    lid, season, draft, rosters_by_week = unit
    lg, facts, start = _STATE["leagues"][lid], _facts(lid, season), _STATE["start"]
    slots = lineup_slots(lg["roster_positions"])
    n = len(rosters_by_week[1])
    rng = np.random.default_rng([unit_seed(lid, season, draft), 1])
    pairs = random_schedule(n, start - 1, rng)
    scores = weekly_scores(rosters_by_week, facts, slots)
    out_actual = outcome(scores, pairs, start)
    rows = []
    for week in AS_OF:
        data = league_data(
            lg, _STATE["shapes"][(lid, season)], facts, rosters_by_week[week], week, scores,
            pairs, start,
        )  # fmt: skip
        seed = unit_seed(lid, season, draft) + week
        base = {on: inputs(data, seed, on) for on in (True, False)}
        for name, (tau_on, drift, churn) in variants().items():
            inp = variant_inputs(base[tau_on], drift, churn)
            res = simulate_season(inp)
            wins = sim_wins(inp)
            for t in range(n):
                rows.append(
                    {
                        "league_id": lid, "season": season, "draft": draft, "as_of": week,
                        "team": t, "variant": name, "p_playoffs": float(res.p_playoffs[t]),
                        "p_title": float(res.p_title[t]), "exp_wins": float(wins[t].mean()),
                        "var_wins": float(wins[t].var()), "made": bool(out_actual["made"][t]),
                        "title": bool(out_actual["title"][t]),
                        "wins": float(out_actual["wins"][t]),
                    }
                )  # fmt: skip
    return rows


# ---------------------------------------------------------------- self-checks


def self_check(shape_by: dict, unit: tuple) -> None:
    """The prod variant equals production build_inputs; outcomes are well formed."""
    _init(shape_by)
    lid, season, draft, rosters_by_week = unit
    lg, facts, start = _STATE["leagues"][lid], _facts(lid, season), _STATE["start"]
    slots = lineup_slots(lg["roster_positions"])
    rng = np.random.default_rng([unit_seed(lid, season, draft), 1])
    pairs = random_schedule(len(rosters_by_week[1]), start - 1, rng)
    assert all(len({x for p in ps for x in p}) == 10 for ps in pairs.values())
    scores = weekly_scores(rosters_by_week, facts, slots)
    res = outcome(scores, pairs, start)
    assert res["made"].sum() == N_PLAYOFF_TEAMS and res["title"].sum() == 1
    assert res["wins"].sum() == 10 * (start - 1) / 2
    data = league_data(lg, _STATE["shapes"][(lid, season)], facts, rosters_by_week[7], 7,
                       scores, pairs, start)  # fmt: skip
    prod = build_inputs(data, None, N_SIMS, 5)
    mine = variant_inputs(inputs(data, 5, True), PROD_DRIFT, 0.0)
    assert np.allclose(prod.noise_sd, mine.noise_sd) and np.allclose(prod.shift, mine.shift)
    assert np.allclose(prod.mean, mine.mean)
    assert (prod.mean[:, 0] > 50).all(), prod.mean[:, 0]  # a real lineup's points


# ---------------------------------------------------------------- scoring


def with_losses(rows: pl.DataFrame) -> pl.DataFrame:
    p, y = pl.col("p_title").clip(EPS, 1 - EPS), pl.col("title").cast(pl.Float64)
    return rows.with_columns(
        brier=(pl.col("p_playoffs") - pl.col("made").cast(pl.Float64)) ** 2,
        brier_title=(pl.col("p_title") - y) ** 2,
        ll_title=-(y * p.log() + (1 - y) * (1 - p).log()),
        sq_wins=(pl.col("wins") - pl.col("exp_wins")) ** 2,
    )


def metrics(scored: pl.DataFrame) -> pl.DataFrame:
    return (
        scored.group_by("season", "variant")
        .agg(
            pl.col("brier").mean(),
            pl.col("brier_title").mean(),
            pl.col("ll_title").mean(),
            (pl.col("sq_wins").mean() / pl.col("var_wins").mean()).alias("wins_mse_over_var"),
        )
        .sort("season", "brier")
    )


def spread_table(scored: pl.DataFrame, chosen: list[str]) -> pl.DataFrame:
    """Final-win spread: actual sd across teams against the simulated sd (between and within)."""
    return (
        scored.filter(pl.col("variant").is_in(chosen))
        .group_by("season", "variant", "as_of")
        .agg(
            pl.col("wins").std().alias("sd_actual"),
            (pl.col("var_wins").mean() + pl.col("exp_wins").var()).sqrt().alias("sd_sim"),
            pl.col("sq_wins").mean().sqrt().alias("rmse_vs_exp"),
            pl.col("var_wins").mean().sqrt().alias("sim_sd_within"),
        )
        .sort("variant", "season", "as_of")
    )


def reliability(scored: pl.DataFrame, variant: str) -> pl.DataFrame:
    return (
        scored.filter(pl.col("variant") == variant)
        .with_columns(decile=(pl.col("p_playoffs") * 10).floor().clip(0, 9).cast(pl.Int64))
        .group_by("season", "decile")
        .agg(
            pl.len().alias("n"),
            pl.col("p_playoffs").mean().round(3).alias("mean_p"),
            pl.col("made").mean().round(3).alias("observed"),
        )
        .sort("season", "decile")
    )


def paired_boot(scored: pl.DataFrame, season: int, variant: str, col: str) -> tuple[float, ...]:
    """Mean change (variant minus prod) and a 95% interval, drafts resampled within league."""
    keys = ["league_id", "draft", "as_of", "team"]
    one = scored.filter(pl.col("season") == season)
    a = one.filter(pl.col("variant") == variant).select(*keys, pl.col(col).alias("v"))
    b = one.filter(pl.col("variant") == "prod").select(*keys, pl.col(col).alias("p"))
    per = (
        a.join(b, on=keys)
        .group_by("league_id", "draft")
        .agg((pl.col("v") - pl.col("p")).sum().alias("d"), pl.len().alias("n"))
        .sort("league_id", "draft")
    )
    rng = np.random.default_rng(7)
    sums, counts = [], []
    for (_,), g in per.group_by("league_id", maintain_order=True):
        d, n = g["d"].to_numpy(), g["n"].to_numpy()
        pick = rng.integers(0, len(d), size=(BOOT, len(d)))
        sums.append(d[pick].sum(axis=1))
        counts.append(n[pick].sum(axis=1))
    boot = np.sum(sums, axis=0) / np.sum(counts, axis=0)
    mean = float(per["d"].sum() / per["n"].sum())
    lo, hi = np.quantile(boot, [0.025, 0.975])
    return mean, float(lo), float(hi)


def fit_on(scored: pl.DataFrame, names: list[str], season: int) -> str:
    table = scored.filter((pl.col("season") == season) & pl.col("variant").is_in(names))
    return table.group_by("variant").agg(pl.col("brier").mean()).sort("brier")["variant"][0]


def report(scored: pl.DataFrame) -> None:
    print("\nBrier (playoffs, title), title log loss; wins_mse_over_var > 1: too narrow")
    print(metrics(scored))
    print("\nreliability of playoff odds, production")
    print(reliability(scored, "prod"))
    print("\nfinal win totals: actual sd against simulated sd")
    print(spread_table(scored, ["prod", "tau_off", "drift0", "drift4"]))
    print("\nby as-of week, production and tau off")
    print(
        scored.filter(pl.col("variant").is_in(["prod", "tau_off"]))
        .group_by("season", "as_of", "variant")
        .agg(pl.col("brier").mean(), pl.col("ll_title").mean())
        .sort("season", "as_of", "variant")
    )
    names = variants()
    drift_pick = fit_on(scored, ["prod", *[n for n in names if n.startswith("drift")]], 2024)
    churn_pick = fit_on(scored, ["prod", *[n for n in names if n.startswith("churn")]], 2024)
    print(f"\nfit on 2024: drift -> {drift_pick}, churn -> {churn_pick}")
    print("2025 test against prod (change, 95% interval); ships if the Brier interval is below 0")
    for cand in dict.fromkeys(["tau_off", drift_pick, churn_pick]):
        if cand == "prod":
            print("  fit picked prod: nothing to test")
            continue
        brier = paired_boot(scored, 2025, cand, "brier")
        ll = paired_boot(scored, 2025, cand, "ll_title")
        ships = brier[2] < 0 and ll[0] <= 0
        print(
            f"  {cand}: Brier {brier[0]:+.5f} [{brier[1]:+.5f}, {brier[2]:+.5f}]  "
            f"title log loss {ll[0]:+.5f} [{ll[1]:+.5f}, {ll[2]:+.5f}]  "
            f"{'SHIPS' if ships else 'no'}"
        )
    for cand in names:
        if cand != "prod":
            b24, b25 = (paired_boot(scored, s, cand, "brier") for s in SEASONS)
            print(f"  {cand}: Brier change 2024 {b24[0]:+.5f}, 2025 {b25[0]:+.5f} "
                  f"[{b25[1]:+.5f}, {b25[2]:+.5f}]")  # fmt: skip


# ---------------------------------------------------------------- main


def units() -> list[tuple]:
    rosters = rg.built_rosters(rg.CONSTRUCTIONS[0], None).filter(
        pl.col("season").is_in(SEASONS)
    )
    out = []
    for (lid, season, team_draft), g in rosters.with_columns(
        (pl.col("team") // 100).alias("draft")
    ).group_by("league_id", "season", "draft", maintain_order=True):
        by_week: dict[int, list[tuple[str, ...]]] = {}
        for (week,), gw in g.group_by("week"):
            teams = gw.group_by("team").agg("gsis_id").sort("team")
            by_week[week] = [tuple(sorted(x)) for x in teams["gsis_id"].to_list()]
        out.append((lid, season, int(team_draft), by_week))
    return out


def main() -> None:
    cache = Path(__file__).parent / "scratch" / "season_calibration_rows.parquet"
    if "--cached" in sys.argv and cache.exists():
        report(with_losses(pl.read_parquet(cache)))
        return
    t0 = time.time()
    shape_by = {(r["league_id"], s): shapes(r["league_id"], s) for r in league_rows() for s in
                SEASONS}  # fmt: skip
    todo = units()
    limit = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--drafts=")), None)
    if limit is not None:
        todo = [u for u in todo if u[2] < limit]
    print(f"{len(todo)} league-season drafts, built in {time.time() - t0:.0f}s")
    self_check(shape_by, todo[0])
    with get_context("spawn").Pool(WORKERS, initializer=_init, initargs=(shape_by,)) as pool:
        rows = [r for chunk in pool.imap_unordered(run_unit, todo, chunksize=4) for r in chunk]
    print(f"simulated in {time.time() - t0:.0f}s")
    frame = pl.DataFrame(rows)
    cache.parent.mkdir(exist_ok=True)
    frame.write_parquet(cache)
    report(with_losses(frame))


if __name__ == "__main__":
    main()
