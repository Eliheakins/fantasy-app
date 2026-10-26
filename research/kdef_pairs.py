"""K and DEF correlations: measure them, then test whether they improve team-total calibration.

Residuals: skill players from the learned model's walk-forward projections (2021 on, roles QB1,
RB1, WR1 by projection rank within team-week as `distributions.with_roles`); K and DEF from the
streaming projection (`streaming.project_units`) refit before every week on earlier weeks only,
as `streaming.backtest` does (2019 on). K is the team's top projected kicker who played; DEF is
every team-week. Correlation: Spearman of residuals turned into a Gaussian-copula rho with
2 sin(pi rho_s / 6), as `distributions._correlate`. 95% intervals: 1,000 bootstrap resamples of
games (a game holds both team-weeks, so this is at least as wide as resampling team-weeks).

Pairs: DEF with the opposing QB1, RB1, WR1 and K; DEF with its own QB1 and K; K with its own QB1,
RB1 and WR1; K with the opposing K.

Held-out test (rule fixed before the run): fit everything on seasons up to 2023 (pairs with a
skill player 2021 to 2023, K and DEF pairs 2019 to 2023), keep the pairs whose fit-period interval
excludes 0, and score 2024 and 2025 team totals that include K and DEF. Both arms use the same
marginals (skill: ratio quantiles by position and size tier, `estimate_marginals`; K and DEF:
additive residual quantiles), the same skill pairs (`estimate_pairs`) and the same random numbers;
the candidate adds the kept K and DEF pairs. Ship if CRPS or pinball of the simulated team total
improves in both leagues and 80% coverage is no worse.
Primary set: synthetic 10-team leagues per week (skill players who played, snake-drafted by
projection, best lineup by projection for the league's slots), K and DEF dealt to the teams at
random, REPLICATES deals a week. Diagnostic only: whole-game stacks (both teams' QB1, RB1, WR1,
K and DEF), where the pairs bind.

KDEF_SEED changes the K and DEF deal and the simulation draws (robustness reruns; the registered
run uses the default).

Run from the repo root: OMP_NUM_THREADS=3 uv run python research/kdef_pairs.py
"""

import math
import os
import sys
from pathlib import Path

import numpy as np
import polars as pl
from scipy.stats import norm, rankdata

sys.path.insert(0, str(Path(__file__).parent))
import wf_panel as w  # noqa: E402

from fantasy import store  # noqa: E402
from fantasy.sim.lineup import Player, auto_lineup, lineup_slots  # noqa: E402
from fantasy.stages.distributions import (  # noqa: E402
    estimate_marginals,
    estimate_pairs,
    residual_frame,
    with_roles,
)
from fantasy.stages.streaming import project_units  # noqa: E402

KD_FROM = 2019
SKILL_FROM = 2021
TRAIN_END = 2023
TEST = [2024, 2025]
N_BOOT = 1000
N_SIMS = 4000
N_TEAMS, ROUNDS, REPLICATES = 10, 12, 5
LEVELS = np.round(np.arange(1, 100) / 100, 2)
PINBALL_LEVELS = np.round(np.arange(1, 10) / 10, 1)
MIN_EIGENVALUE = 1e-6
SEED = int(os.environ.get("KDEF_SEED", "20261025"))  # robustness reruns change it
TW = ["league_id", "season", "week", "team"]
PAIRS = [  # (role on the DEF/K side, role of the other, relation)
    ("DEF", "QB1", "opposing"),
    ("DEF", "RB1", "opposing"),
    ("DEF", "WR1", "opposing"),
    ("DEF", "K", "opposing"),
    ("DEF", "QB1", "same_team"),
    ("DEF", "K", "same_team"),
    ("K", "QB1", "same_team"),
    ("K", "RB1", "same_team"),
    ("K", "WR1", "same_team"),
    ("K", "K", "opposing"),
]


def walk_forward_units(hist: pl.DataFrame, use_dome: bool) -> pl.DataFrame:
    """unit, team, season, week, points, projection: each week projected from earlier weeks."""
    out = []
    for (season, week), g in hist.filter(pl.col("season") >= KD_FROM).group_by("season", "week"):
        past = hist.filter(
            (pl.col("season") < season) | ((pl.col("season") == season) & (pl.col("week") < week))
        )
        upcoming = g.select("unit", "team", "week", "implied", "roof")
        proj = project_units(past, upcoming, "unit", "implied", use_dome)
        out.append(g.join(proj.select("unit", "projection"), on="unit"))
    return pl.concat(out).select("unit", "team", "season", "week", "points", "projection")


def kd_residuals() -> pl.DataFrame:
    """TW, kind (K or DEF), points, projection, resid."""
    games = store.read_table("team_games").filter(pl.col("game_type") == "REG")
    kickers = store.read_table("player_points").filter(
        (pl.col("position") == "K") & (pl.col("season_type") == "REG")
    )
    defense = store.read_table("defense_points")
    parts = []
    for lid in w.league_ids():
        d_hist = defense.filter(pl.col("league_id") == lid).select(
            pl.col("team").alias("unit"),
            "team",
            "season",
            "week",
            "points",
            pl.col("opp_implied").alias("implied"),
            "roof",
        )
        d = walk_forward_units(d_hist, False).with_columns(kind=pl.lit("DEF"))
        k_hist = kickers.filter(pl.col("league_id") == lid).select(
            pl.col("gsis_id").alias("unit"),
            "team",
            "season",
            "week",
            "points",
            pl.col("team_implied").alias("implied"),
            "roof",
        )
        k = (
            walk_forward_units(k_hist, True)
            .sort("projection", descending=True)
            .unique(["team", "season", "week"], keep="first")
            .with_columns(kind=pl.lit("K"))
        )
        parts.append(pl.concat([d, k]).with_columns(league_id=pl.lit(lid)))
    out = pl.concat(parts).with_columns((pl.col("points") - pl.col("projection")).alias("resid"))
    regular = games.select("team", "season", "week")
    return out.join(regular, on=["team", "season", "week"]).select(
        *TW, "kind", "unit", "points", "projection", "resid"
    )


def skill_residuals() -> pl.DataFrame:
    """Learned residuals from SKILL_FROM with roles (2019 and 2020 are dropped by the store)."""
    res = residual_frame(store.projection_table(), store.read_table("player_points"))
    return with_roles(res.filter(pl.col("season") >= SKILL_FROM))


def role_wide(skill: pl.DataFrame, kd: pl.DataFrame) -> pl.DataFrame:
    """One row per team-week: resid of QB1, RB1, WR1, K and DEF (null when absent), game id."""
    s = skill.filter(pl.col("role").is_in(["QB1", "RB1", "WR1"])).pivot(
        on="role", index=TW, values="resid"
    )
    k = kd.pivot(on="kind", index=TW, values="resid")
    games = store.read_table("team_games").filter(pl.col("game_type") == "REG")
    return k.join(s, on=TW, how="left").join(
        games.select("team", "season", "week", "opponent", "game_id"),
        on=["team", "season", "week"],
    )


def pair_rows(wide: pl.DataFrame, a: str, b: str, relation: str) -> pl.DataFrame:
    """game_id, season, x (role a's resid), y (role b's resid) for one pair."""
    if relation == "same_team":
        rows = wide.select("league_id", "game_id", "season", x=pl.col(a), y=pl.col(b))
    else:
        opp = wide.select("league_id", "season", "week", "team", pl.col(b).alias("y"))
        rows = wide.join(
            opp,
            left_on=["league_id", "season", "week", "opponent"],
            right_on=["league_id", "season", "week", "team"],
        )
        if a == b:  # symmetric: one row per game
            rows = rows.filter(pl.col("team") < pl.col("opponent"))
        rows = rows.select("league_id", "game_id", "season", x=pl.col(a), y="y")
    return rows.drop_nulls(["x", "y"])


def to_rho(rs: np.ndarray | float) -> np.ndarray | float:
    return 2 * np.sin(np.pi * np.asarray(rs) / 6)


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    return float(np.corrcoef(rankdata(x), rankdata(y))[0, 1])


def measure(rows: pl.DataFrame, rng: np.random.Generator) -> dict[str, float]:
    """rho with a game-bootstrap 95% interval."""
    x, y = rows["x"].to_numpy(), rows["y"].to_numpy()
    codes = rows["game_id"].cast(pl.Categorical).to_physical().to_numpy()
    n_games = int(codes.max()) + 1
    members = [np.flatnonzero(codes == g) for g in range(n_games)]
    boots = []
    for _ in range(N_BOOT):
        pick = np.concatenate([members[g] for g in rng.integers(0, n_games, n_games)])
        boots.append(spearman(x[pick], y[pick]))
    low, high = np.quantile(to_rho(np.array(boots)), [0.025, 0.975])
    return {"n": len(x), "rho": float(to_rho(spearman(x, y))), "lo": float(low), "hi": float(high)}


def measure_all(wide: pl.DataFrame, last: int | None) -> pl.DataFrame:
    rng = np.random.default_rng(SEED)
    rows = []
    for lid in w.league_ids():
        lw = wide.filter(pl.col("league_id") == lid)
        for a, b, relation in PAIRS:
            first = KD_FROM if b in ("K", "DEF") else SKILL_FROM
            sel = pair_rows(lw, a, b, relation).filter(pl.col("season") >= first)
            if last is not None:
                sel = sel.filter(pl.col("season") <= last)
            m = measure(sel, rng)
            rows.append(
                {
                    "league": w.LEAGUE_NAMES[lid],
                    "league_id": lid,
                    "a": a,
                    "b": b,
                    "relation": relation,
                    "seasons": f"{first}-{last or 'now'}",
                    **m,
                }
            )
    return pl.DataFrame(rows).with_columns(excludes_0=(pl.col("lo") > 0) | (pl.col("hi") < 0))


# --- held-out team totals ------------------------------------------------------------------


def skill_shapes(train: pl.DataFrame, lid: str) -> dict[str, list[tuple[float, np.ndarray]]]:
    """position -> [(proj_max, ratio quantiles)] by size tier, fit on training rows."""
    marg = estimate_marginals(train.filter(pl.col("league_id") == lid)).filter(pl.col("tier") >= 0)
    out: dict[str, list[tuple[float, np.ndarray]]] = {}
    for (position, _tier), g in marg.sort("tau").group_by("position", "tier", maintain_order=True):
        out.setdefault(position, []).append((float(g["proj_max"][0]), g["ratio"].to_numpy()))
    return {p: sorted(v, key=lambda t: t[0]) for p, v in out.items()}


def shape_for(shapes: dict, position: str, projection: float) -> np.ndarray:
    for upper, q in shapes[position]:
        if projection <= upper:
            return q
    return shapes[position][-1][1]


def pair_lookup(pairs: pl.DataFrame, lid: str) -> dict[tuple[str, str, str], float]:
    out = {}
    for a, b, rel, rho in (
        pairs.filter(pl.col("league_id") == lid)
        .select("role_a", "role_b", "relation", "rho")
        .iter_rows()
    ):
        out[(*sorted((a, b)), rel)] = rho
    return out


def corr_matrix(slate: list[dict], rho: dict[tuple[str, str, str], float], opp: dict) -> np.ndarray:
    n = len(slate)
    c = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            pi, pj = slate[i], slate[j]
            if pi["team"] == pj["team"]:
                rel = "same_team"
            elif opp.get(pi["team"]) == pj["team"]:
                rel = "opposing"
            else:
                continue
            c[i, j] = c[j, i] = rho.get((*sorted((pi["role"], pj["role"])), rel), 0.0)
    values, vectors = np.linalg.eigh(c)
    fixed = (vectors * np.clip(values, MIN_EIGENVALUE, None)) @ vectors.T
    scale = np.sqrt(np.diag(fixed))
    return fixed / np.outer(scale, scale)


def simulate_total(slate: list[dict], corr: np.ndarray, z: np.ndarray) -> np.ndarray:
    u = norm.cdf(z[:, : len(slate)] @ np.linalg.cholesky(corr).T)
    total = np.zeros(z.shape[0])
    for j, p in enumerate(slate):
        q = np.interp(u[:, j], LEVELS, p["shape"])
        total += p["projection"] * q if p["kind"] == "skill" else p["projection"] + q
    return total


def score(sims: np.ndarray, y: float) -> dict[str, float]:
    x = np.sort(sims)
    n = len(x)
    crps = float(np.mean(np.abs(x - y)) - np.sum((2 * np.arange(1, n + 1) - n - 1) * x) / n**2)
    qs = np.quantile(x, PINBALL_LEVELS)
    pinball = float(np.mean(np.maximum(PINBALL_LEVELS * (y - qs), (PINBALL_LEVELS - 1) * (y - qs))))
    lo, hi = np.quantile(x, [0.1, 0.9])
    return {
        "crps": crps,
        "pinball": pinball,
        "cover80": float(lo <= y <= hi),
        "z": (y - x.mean()) / x.std(),
    }


def snake(ids: list[str]) -> list[list[str]]:
    teams: list[list[str]] = [[] for _ in range(N_TEAMS)]
    for pick, pid in enumerate(ids[: N_TEAMS * ROUNDS]):
        rnd, slot = divmod(pick, N_TEAMS)
        teams[slot if rnd % 2 == 0 else N_TEAMS - 1 - slot].append(pid)
    return teams


def league_lineups(pool: pl.DataFrame, kd: pl.DataFrame, slots: list[str], rng) -> list[list[dict]]:
    """Synthetic league lineups for one week: skill by snake draft and best lineup, plus a K and
    a DEF dealt at random."""
    ranked = pool.sort("projection", descending=True)
    by_id = {r["gsis_id"]: r for r in ranked.iter_rows(named=True)}
    ks = kd.filter(pl.col("kind") == "K").to_dicts()
    ds = kd.filter(pl.col("kind") == "DEF").to_dicts()
    out = []
    for _ in range(REPLICATES):
        k_pick = rng.permutation(len(ks))[:N_TEAMS]
        d_pick = rng.permutation(len(ds))[:N_TEAMS]
        for t, team in enumerate(snake(ranked["gsis_id"].to_list())):
            players = [Player(i, by_id[i]["position"], by_id[i]["projection"]) for i in team]
            started = auto_lineup(players, slots).players
            out.append([by_id[i] for i in team if i in started] + [ks[k_pick[t]], ds[d_pick[t]]])
    return out


def game_stacks(pool: pl.DataFrame, kd: pl.DataFrame, opp: dict) -> list[list[dict]]:
    tops = pool.filter(pl.col("role").is_in(["QB1", "RB1", "WR1"]))
    allp = pl.concat([tops.select(kd.columns), kd]) if tops.height else kd
    by_team: dict[str, list[dict]] = {}
    for r in allp.to_dicts():
        by_team.setdefault(r["team"], []).append(r)
    return [
        by_team.get(a, []) + by_team.get(b, [])
        for a, b in opp.items()
        if a < b and a in by_team and b in by_team
    ]


def test_heldout(skill: pl.DataFrame, kd: pl.DataFrame, fit_pairs: pl.DataFrame) -> pl.DataFrame:
    games = store.read_table("team_games").filter(pl.col("game_type") == "REG")
    train_skill = skill.filter(pl.col("season") <= TRAIN_END)
    skill_pairs = estimate_pairs(train_skill, games)
    kept = fit_pairs.filter("excludes_0")
    rows = []
    for league in store.read_table("leagues", "raw").iter_rows(named=True):
        lid = league["league_id"]
        slots = [s for s in lineup_slots(list(league["roster_positions"])) if s not in ("K", "DEF")]
        shapes = skill_shapes(train_skill, lid)
        kd_train = kd.filter((pl.col("league_id") == lid) & (pl.col("season") <= TRAIN_END))
        kd_shape = {
            kind: np.quantile(g["resid"].to_numpy(), LEVELS)
            for (kind,), g in kd_train.group_by("kind")
        }
        base = pair_lookup(skill_pairs, lid)
        extra = {
            (*sorted((a, b)), rel): rho
            for a, b, rel, rho in kept.filter(pl.col("league_id") == lid)
            .select("a", "b", "relation", "rho")
            .iter_rows()
        }
        arms = {"without": base, "with": {**base, **extra}}
        rng = np.random.default_rng(SEED)
        for season in TEST:
            for week in range(1, 19):
                pool = skill.filter(
                    (pl.col("league_id") == lid)
                    & (pl.col("season") == season)
                    & (pl.col("week") == week)
                )
                wk = kd.filter(
                    (pl.col("league_id") == lid)
                    & (pl.col("season") == season)
                    & (pl.col("week") == week)
                )
                if pool.is_empty() or wk.is_empty():
                    continue
                g = games.filter((pl.col("season") == season) & (pl.col("week") == week))
                opp = dict(g.select("team", "opponent").iter_rows())
                pool = pool.select(
                    "team", "gsis_id", "position", "role", "projection", "points"
                ).with_columns(kind=pl.lit("skill"))
                wk = wk.select(
                    "team",
                    pl.col("unit").alias("gsis_id"),
                    pl.col("kind").alias("position"),
                    pl.col("kind").alias("role"),
                    "projection",
                    "points",
                    "kind",
                )
                for set_name, lineups in (
                    ("league", league_lineups(pool, wk, slots, rng)),
                    ("game_stack", game_stacks(pool, wk, opp)),
                ):
                    for lineup in lineups:
                        slate = [
                            {
                                **p,
                                "shape": shape_for(shapes, p["position"], p["projection"])
                                if p["kind"] == "skill"
                                else kd_shape[p["kind"]],
                            }
                            for p in lineup
                        ]
                        y = float(sum(p["points"] for p in slate))
                        z = rng.standard_normal((N_SIMS, len(slate)))
                        for arm, rho in arms.items():
                            sims = simulate_total(slate, corr_matrix(slate, rho, opp), z)
                            rows.append(
                                {
                                    "league": league["league_key"],
                                    "set": set_name,
                                    "arm": arm,
                                    "season": season,
                                    "week": week,
                                    "actual": y,
                                    **score(sims, y),
                                }
                            )
    return pl.DataFrame(rows)


def summarize(scores: pl.DataFrame) -> pl.DataFrame:
    out = []
    for (league, set_name), g in scores.group_by("league", "set", maintain_order=True):
        a, b = g.filter(pl.col("arm") == "without"), g.filter(pl.col("arm") == "with")
        wk = (
            g.group_by("season", "week", "arm")
            .agg(pl.col("crps").mean())
            .pivot(on="arm", index=["season", "week"], values="crps")
        )
        d = (wk["without"] - wk["with"]).to_numpy()
        t = float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d))))
        out.append(
            {
                "league": league,
                "set": set_name,
                "n": a.height,
                "crps_without": round(float(a["crps"].mean()), 4),
                "crps_with": round(float(b["crps"].mean()), 4),
                "crps_t": round(t, 2),
                "pinball_without": round(float(a["pinball"].mean()), 4),
                "pinball_with": round(float(b["pinball"].mean()), 4),
                "cover80_without": round(float(a["cover80"].mean()), 3),
                "cover80_with": round(float(b["cover80"].mean()), 3),
                "zsd_without": round(float(a["z"].std()), 3),
                "zsd_with": round(float(b["z"].std()), 3),
            }
        )
    return pl.DataFrame(out)


def main() -> None:
    kd = kd_residuals()
    skill = skill_residuals()
    wide = role_wide(skill, kd)
    with pl.Config(tbl_rows=60, tbl_cols=12, fmt_float="full"):
        full = measure_all(wide, None).with_columns(pl.col("rho", "lo", "hi").round(3))
        print("all seasons:")
        print(full.drop("league_id"))
        fit = measure_all(wide, TRAIN_END).with_columns(pl.col("rho", "lo", "hi").round(3))
        print(f"fit period (to {TRAIN_END}):")
        print(fit.drop("league_id"))
        scores = test_heldout(skill, kd, fit)
        summary = summarize(scores)
        print(summary)
    primary = summary.filter(pl.col("set") == "league")
    better = (primary["crps_with"] < primary["crps_without"]).all() or (
        primary["pinball_with"] < primary["pinball_without"]
    ).all()
    no_worse = (
        (primary["cover80_with"] - 0.8).abs() <= (primary["cover80_without"] - 0.8).abs()
    ).all()
    print(
        f"ship rule: CRPS or pinball better in both {better}, coverage no worse {no_worse} -> "
        f"{'SHIP' if better and no_worse else 'report only'}"
    )


if __name__ == "__main__":
    main()
