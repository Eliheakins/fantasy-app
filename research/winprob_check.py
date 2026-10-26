"""Win-probability lineups against max expected points, judged on actual wins.

Rosters: regret.py's built rosters (constructions A and B), 2024 and 2025 weeks 1 to 17, DRAFTS
drafts per league-season, players who took the field that week (as in regret.py). Each draft
gets a random head-to-head pairing every week. Projections are proj_learned (walk-forward).

Simulation as the app does it (`_lineup.win_probability`): the production sampler
(`sim.sampler`, Gaussian copula over role pairs, per-tier marginals), with marginals and role
correlations fit by `stages.distributions` on 2021 to 2023 only (tiers cut as production cuts
them), LINEUP_SIMS draws, K and DEF as a zero-mean normal with the league's K variance (2021 to
2023 kicker games) and the fallback defense variance (their means are the same for both teams).
For each team against its opponent, who plays his max-expected-points lineup (as the app assumes
when no Sleeper lineup is set):
  A  max expected points (`auto_lineup`)
  B  max win probability: `search` from A over swaps, `choose` on split draws (the app's pick)
  C  the 0.9-quantile lineup (`pick_by_quantile`) when A's win chance is under UNDERDOG, else A
Scored on ACTUAL points: win 1, tie 0.5, loss 0 against the opponent's actual A points, plus one
K-and-DEF noise draw per team-week shared by A, B and C. Paired by team-week; t over weeks (per
league, construction and week the mean of B - A, then t across the 34 weeks; season t over 17).

Prior (normal approximation): 0.1 to 0.3 points of win rate. Rule (fixed before scoring): B or C
becomes the default only if its actual weekly win rate is higher in both leagues with pooled
|t| >= 2 and no season t <= -1; otherwise it stays a display option and nothing in src changes.

Run from the repo root: OMP_NUM_THREADS=3 uv run python research/winprob_check.py [drafts]
"""

import sys
import time
import zlib
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
import regret as r  # noqa: E402

from fantasy import stat_line_table, store  # noqa: E402
from fantasy._engine import _tier_edges  # noqa: E402
from fantasy._lineup import LINEUP_SIMS, UNDERDOG  # noqa: E402
from fantasy.sim.calibration import tier_of  # noqa: E402
from fantasy.sim.lineup import Player, auto_lineup, constant_slot_count, lineup_slots  # noqa: E402
from fantasy.sim.sampler import Slate, correlation_matrix, sample_points  # noqa: E402
from fantasy.sim.winprob import choose, pick_by_quantile, search, swap_candidates  # noqa: E402
from fantasy.stages import distributions as dist  # noqa: E402
from fantasy.stages.simulate import DEF_VAR  # noqa: E402

SEASONS = {2024: 17, 2025: 17}
SHAPE_SEASONS = (2021, 2023)
DRAFTS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
STRATEGIES = ("A", "B", "C")
pl.Config(tbl_rows=60, tbl_cols=20, tbl_width_chars=200)


def shapes() -> tuple[pl.DataFrame, pl.DataFrame]:
    """marginals and correlation_pairs as distributions.run fits them, on SHAPE_SEASONS only."""
    lo, hi = SHAPE_SEASONS
    res = dist.residual_frame(store.projection_table(), store.read_table("player_points"))
    res = res.filter(pl.col("season").is_between(lo, hi))
    if stat_line_table.stored() is not None:
        res = dist.with_stat_line_flag(res, store.read_table("proj_baseline"))
    fitted = dist.shape_frame(res, dist.estimate_curves(res), store.projection_name())
    pairs = dist.estimate_pairs(dist.with_roles(fitted), store.read_table("team_games"))
    return dist.estimate_marginals(fitted), pairs


def kd_sd(lid: str, layout: list[str]) -> float:
    lo, hi = SHAPE_SEASONS
    k = store.read_table("player_points").filter(
        (pl.col("league_id") == lid)
        & (pl.col("position") == "K")
        & pl.col("season").is_between(lo, hi)
    )["points"]
    counts = constant_slot_count(layout)
    k_var = float(k.var()) if k.len() > 1 else 0.0
    return float(np.sqrt(counts.get("K", 0) * k_var + counts.get("DEF", 0) * DEF_VAR))


def roles_and_teams() -> pl.DataFrame:
    """league_id, gsis_id, season, week, team, role (position + projection rank in the NFL team,
    as `_engine._draw_points` labels the week's projections)."""
    p = store.read_table("proj_learned").filter(~pl.col("is_future"))
    rank = (
        pl.col("projection")
        .rank("ordinal", descending=True)
        .over("league_id", "season", "week", "team", "position")
    )
    return p.select(
        *r.KEY, pl.col("team").fill_null(""), role=pl.col("position") + rank.cast(pl.String)
    )


def opponents() -> dict[tuple[int, int], dict[str, str]]:
    s = store.read_table("nfl_schedules", "raw").filter(pl.col("game_type") == "REG")
    out: dict[tuple[int, int], dict[str, str]] = {}
    for season, week, home, away in s.select(
        "season", "week", "home_team", "away_team"
    ).iter_rows():
        out.setdefault((season, week), {}).update({home: away, away: home})
    return out


class League:
    """Everything one league's matchups need."""

    def __init__(self, lg: dict, marginals: pl.DataFrame, pairs: pl.DataFrame) -> None:
        self.lid = lg["league_id"]
        self.slots = lineup_slots(lg["roster_positions"])
        self.kd_sd = kd_sd(self.lid, lg["roster_positions"])
        m = marginals.filter(pl.col("league_id") == self.lid)
        self.ratios = {
            (pos if tier < 0 else f"{pos}:{tier}"): g.sort("tau")["ratio"].to_numpy()
            for (pos, tier), g in m.group_by("position", "tier")
        }
        self.edges = _tier_edges(m)
        self.rho: dict[str, dict[tuple[str, str], float]] = {"same_team": {}, "opposing": {}}
        for rel, a, b, rho in (
            pairs.filter(pl.col("league_id") == self.lid)
            .select("relation", "role_a", "role_b", "rho")
            .iter_rows()
        ):
            self.rho[rel][(a, b)] = self.rho[rel][(b, a)] = rho


def play_side(
    lg: League,
    mine: list[str],
    theirs: list[str],
    info: dict[str, tuple],
    draws: np.ndarray,
    col: dict[str, int],
    seed: int,
) -> dict[str, float]:
    """A, B and C for `mine` against `theirs` playing max expected points."""
    pos = {i: info[i][0] for i in mine + theirs}
    pool = [Player(i, pos[i], info[i][1]) for i in mine]
    base = auto_lineup(pool, lg.slots).players
    opp = auto_lineup([Player(i, pos[i], info[i][1]) for i in theirs], lg.slots).players
    n = draws.shape[0]
    kd_me = lg.kd_sd * np.random.default_rng([seed, 1]).standard_normal(n)
    kd_opp = lg.kd_sd * np.random.default_rng([seed, 2]).standard_normal(n)
    opponent = draws[:, [col[i] for i in opp]].sum(axis=1) + kd_opp
    cache: dict[frozenset[str], np.ndarray] = {}
    half = n // 2

    def totals_of(c: frozenset[str]) -> np.ndarray:
        if c not in cache:
            cache[c] = draws[:, [col[i] for i in c]].sum(axis=1) + kd_me
        return cache[c]

    def train_win(c: frozenset[str]) -> float:
        return float((totals_of(c)[:half] > opponent[:half]).mean())

    def neighbors(c: frozenset[str]) -> list[frozenset[str]]:
        bench = [p.id for p in pool if p.id not in c and p.value > 0]
        return swap_candidates(c, bench, pos, lg.slots, set())

    candidates = search(base, neighbors, train_win)
    totals = {c: totals_of(c) for c in candidates}
    verdict = choose(candidates, base, totals, opponent)
    wp_a = verdict.win_prob[base]
    picks = {
        "A": base,
        "B": verdict.chosen,
        "C": pick_by_quantile(candidates, totals, 0.9)[0] if wp_a < UNDERDOG else base,
    }
    kd_actual = lg.kd_sd * np.sqrt(2) * float(np.random.default_rng([seed, 3]).standard_normal())
    opp_actual = sum(info[i][2] for i in opp)
    out: dict[str, float] = {"wp_A": wp_a, "underdog": float(wp_a < UNDERDOG)}
    for s, ids in picks.items():
        actual = sum(info[i][2] for i in ids) + kd_actual
        out[f"win_{s}"] = 1.0 if actual > opp_actual else 0.5 if actual == opp_actual else 0.0
        out[f"pts_{s}"] = actual - kd_actual
        out[f"exp_{s}"] = sum(info[i][1] for i in ids)
        out[f"wp_{s}"] = verdict.win_prob.get(ids, wp_a)
        out[f"diff_{s}"] = float(ids != base)
    return out


def run_league_season(
    lg: League, cons: str, season: int, rosters: pl.DataFrame, uni: pl.DataFrame, opp_of: dict
) -> list[dict]:
    rows = []
    week_uni = uni.filter((pl.col("league_id") == lg.lid) & (pl.col("season") == season))
    ros = rosters.filter((pl.col("league_id") == lg.lid) & (pl.col("season") == season))
    for (week,), wu in week_uni.group_by("week", maintain_order=True):
        info = {
            g: (p, proj, pts, team, role)
            for g, p, proj, pts, team, role in wu.select(
                "gsis_id", "position", "learned", "points", "team", "role"
            ).iter_rows()
        }
        teams_of = (
            ros.filter(pl.col("week") == week)
            .filter(pl.col("gsis_id").is_in(list(info)))
            .group_by("team")
            .agg("gsis_id")
        )
        roster = {t: sorted(ids) for t, ids in teams_of.iter_rows()}
        by_draft: dict[int, list[int]] = {}
        for t in roster:
            by_draft.setdefault(t // 100, []).append(t)
        for d, teams in by_draft.items():
            rng = np.random.default_rng([int(lg.lid) % 2**32, season, week, d, ord(cons), 7])
            order = [teams[i] for i in rng.permutation(len(teams))]
            for a, b in zip(order[::2], order[1::2], strict=False):
                ids = sorted(set(roster[a]) | set(roster[b]))
                slate = Slate(
                    tuple(ids),
                    tuple(info[i][0] for i in ids),
                    tuple(info[i][3] for i in ids),
                    tuple(info[i][4] for i in ids),
                    tuple(info[i][1] for i in ids),
                    (),
                    tuple(
                        tier_of(lg.edges[info[i][0]], info[i][1]) if info[i][0] in lg.edges else -1
                        for i in ids
                    ),
                )
                corr = correlation_matrix(
                    slate, lg.rho["same_team"], lg.rho["opposing"], opp_of.get((season, week), {})
                )
                seed = zlib.crc32(f"{lg.lid}:{cons}:{season}:{week}:{a}:{b}".encode())
                draws = sample_points(slate, corr, lg.ratios, LINEUP_SIMS, seed)
                col = {i: j for j, i in enumerate(ids)}
                for me, them in ((a, b), (b, a)):
                    side = play_side(lg, roster[me], roster[them], info, draws, col, seed + me)
                    rows.append(
                        {
                            "cons": cons,
                            "league_id": lg.lid,
                            "season": season,
                            "week": week,
                            "team": me,
                            **side,
                        }
                    )
    return rows


def t_of(x: np.ndarray) -> float:
    return r.t_of(x)


def report(res: pl.DataFrame) -> None:
    names = r.league_names()
    res = res.with_columns(pl.col("league_id").replace_strict(names).alias("league"))
    print("\nper construction and league (team-weeks; rates in points of win rate)")
    print(
        res.group_by("cons", "league")
        .agg(
            pl.len().alias("team_weeks"),
            *[pl.col(f"win_{s}").mean().mul(100).round(2).alias(f"win_{s}") for s in STRATEGIES],
            *[
                pl.col(f"diff_{s}").mean().mul(100).round(1).alias(f"changed_{s}%")
                for s in ("B", "C")
            ],
            pl.col("underdog").mean().mul(100).round(1).alias("underdog%"),
            *[
                (pl.col(f"exp_{s}") - pl.col("exp_A")).mean().round(3).alias(f"exp_{s}-A")
                for s in ("B", "C")
            ],
            *[
                (pl.col(f"pts_{s}") - pl.col("pts_A")).mean().round(3).alias(f"pts_{s}-A")
                for s in ("B", "C")
            ],
            *[
                (pl.col(f"wp_{s}") - pl.col("wp_A")).mean().mul(100).round(2).alias(f"wp_{s}-A")
                for s in ("B", "C")
            ],
        )
        .sort("cons", "league")
    )
    rows = []
    for (cons, league), g in res.group_by("cons", "league", maintain_order=True):
        for s in ("B", "C"):
            wk = (
                g.group_by("season", "week")
                .agg((pl.col(f"win_{s}") - pl.col("win_A")).mean().alias("d"))
                .sort("season", "week")
            )
            tw = (g[f"win_{s}"] - g["win_A"]).to_numpy()
            row = {
                "cons": cons,
                "league": league,
                "strategy": s,
                "weeks": wk.height,
                "d_win_pts": round(100 * float(wk["d"].mean()), 3),
                "t_weekly": round(t_of(wk["d"].to_numpy()), 2),
                "t_teamweek": round(t_of(tw), 2),
            }
            for (season,), gs in wk.group_by("season", maintain_order=True):
                row[f"t_{season}"] = round(t_of(gs["d"].to_numpy()), 2)
            # underdog team-weeks only, where C differs from A by design
            dog = g.filter(pl.col("underdog") == 1)
            row["d_win_underdog_pts"] = round(
                100 * float((dog[f"win_{s}"] - dog["win_A"]).mean()), 3
            )
            rows.append(row)
    table = pl.DataFrame(rows).sort("cons", "strategy", "league")
    print("\nactual weekly win rate, strategy minus A (points of win rate; t over weeks)")
    print(table)
    for (cons, s), g in table.group_by("cons", "strategy", maintain_order=True):
        seasons = [v for c in g.columns if c.startswith("t_20") for v in g[c].to_list()]
        ok = (g["d_win_pts"] > 0).all() and (g["t_weekly"].abs() >= 2).any() and min(seasons) > -1
        print(f"verdict {cons} {s}: {'DEFAULT' if ok else 'stays a display option'}")


def self_check() -> None:
    """With the actual points as the only possible outcome, B can never lose to A."""
    slots = ["QB", "RB", "FLEX"]
    info = {"q": ("QB", 10.0, 12.0), "r1": ("RB", 9.0, 3.0), "r2": ("RB", 8.0, 20.0)}
    lg = League.__new__(League)
    lg.slots, lg.kd_sd = slots, 0.0
    col = {"q": 0, "r1": 1, "r2": 2, "o": 3, "o2": 4, "o3": 5}
    info_all = {**info, "o": ("QB", 10.0, 10.0), "o2": ("RB", 10.0, 10.0), "o3": ("RB", 10.0, 10.0)}
    draws = np.tile([12.0, 3.0, 20.0, 10.0, 10.0, 10.0], (100, 1))
    out = play_side(lg, ["q", "r1", "r2"], ["o", "o2", "o3"], info_all, draws, col, 0)
    assert out["win_A"] == 1.0 and out["win_B"] == 1.0, out


def main() -> None:
    self_check()
    t0 = time.time()
    r.LAST_WEEK, r.DRAFTS = SEASONS, DRAFTS
    marginals, pairs = shapes()
    print(f"shapes on {SHAPE_SEASONS}: marginals {marginals.height}, pairs {pairs.height}")
    uni = (
        r.universe()
        .join(roles_and_teams(), on=r.KEY, how="left")
        .with_columns(pl.col("team").fill_null(""), pl.col("role").fill_null(""))
    )
    opp_of = opponents()
    rows = []
    for lg_row in store.read_table("leagues", "raw").iter_rows(named=True):
        lg = League(lg_row, marginals, pairs)
        print(f"{lg_row['name']}: K and DEF sd {lg.kd_sd:.2f}")
        for cons in r.CONSTRUCTIONS:
            rosters = r.built_rosters(cons, uni).filter(pl.col("league_id") == lg.lid)
            for season in SEASONS:
                rows += run_league_season(lg, cons.name, season, rosters, uni, opp_of)
                print(
                    f"  {cons.name} {season}: {len(rows)} team-weeks, {time.time() - t0:.0f} s",
                    flush=True,
                )
    res = pl.DataFrame(rows)
    out = Path("research/scratch/winprob_check.parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    res.write_parquet(out)
    report(res)


if __name__ == "__main__":
    main()
