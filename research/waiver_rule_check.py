"""Which waiver rule wins more games? One team's rule against nine form-rule teams.

Leagues: the same drafts as `regret.py` construction A and `season_calibration_check.py` (same
seeds), 2024 and 2025, DRAFTS a league-season, the same random schedules. Waivers are rolling
priority as both leagues run them (`waiver_type` 0, no bids): before each week from 2 the teams
claim in priority order, at most one claim each, and a team that claims moves to the back.
Initial priority is the reverse of the first draft round. A player dropped that week is not
claimable until the next week.

One team (draft index mod 10, so it rotates) uses the rule under test; the other nine use
regret.py's form rule. Arms, paired on the same draft and schedule:
  A form: worst rostered player at a position by form (mean of the last FORM_GAMES games) against
    the best free agent there, add if the gain is over ADD_MARGIN points a game.
  B next week: the same on this week's projection (proj_learned row, made before the game; a
    player who does not play this week counts 0).
  C rest of season: the app's own `moves.waiver_candidates` (Valuer: expected points over the
    rest of the season with free-agent stand-ins and absences) on flat projections known before
    the week; claim the top add if it adds over C_MARGIN points (fixed, not tuned).
Lineups are the best by that week's projection; scores are actual points (skill slots only).

Metric: that team's regular-season wins (weeks 1 to 14) and actual points, paired over drafts.
Rule (fixed before the run): C (or B) is recommended in the app only if its season wins are
higher than A's in both leagues and the pooled paired |t| >= 2; otherwise report only.

`--real` also prints, for the user's real teams this week (data copy), the Waivers page order
(extra points) against the digest order (playoff change).

Run from the repo root:  OMP_NUM_THREADS=3 uv run python research/waiver_rule_check.py [--real]
"""

import sys
import time
from collections import defaultdict
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
import regret as rg  # noqa: E402
import season_calibration_check as scc  # noqa: E402

from fantasy import store  # noqa: E402
from fantasy.sim import moves  # noqa: E402
from fantasy.sim.lineup import lineup_slots  # noqa: E402
from fantasy.sim.odds import LeagueData  # noqa: E402

SEASONS = scc.SEASONS
DRAFTS = rg.DRAFTS
RULES = ("A", "B", "C")
C_MARGIN = 2.0  # rest-of-season points; an add worth less is not worth losing priority
CONS = rg.CONSTRUCTIONS[0]
pl.Config(tbl_rows=60, tbl_cols=20, tbl_width_chars=200)

_STATE: dict = {}


# ---------------------------------------------------------------- per league-season inputs


def _league_season(lid: str, season: int) -> dict:
    key = (lid, season)
    if key in _STATE:
        return _STATE[key]
    lg = {r["league_id"]: r for r in scc.league_rows()}[lid]
    points = store.read_table("player_points").filter(
        (pl.col("season_type") == "REG") & pl.col("position").is_in(rg.POSITIONS)
    )
    baseline = store.read_table("proj_baseline").filter(~pl.col("is_future"))
    values = rg.preseason_values(CONS, lid, season, points, baseline)
    this = points.filter((pl.col("league_id") == lid) & (pl.col("season") == season))
    games: dict[str, list[tuple[int, float]]] = defaultdict(list)
    positions = {}
    for r in this.sort("week").iter_rows(named=True):
        games[r["gsis_id"]].append((r["week"], r["points"]))
        positions[r["gsis_id"]] = r["position"]
    _STATE[key] = {
        "lg": lg, "values": values, "games": dict(games),
        "pos_of": {**positions, **{g: p for g, (p, _) in values.items()}},
        "facts": scc.season_facts(lid, season), "flat": {}, "start": scc.playoff_start(),
    }  # fmt: skip
    return _STATE[key]


def _flat(ls: dict, week: int) -> pl.DataFrame:
    if week not in ls["flat"]:
        ls["flat"][week] = pl.DataFrame(
            scc.flat_projections(ls["facts"], week),
            schema=["gsis_id", "week", "projection"],
            orient="row",
        )
    return ls["flat"][week]


# ---------------------------------------------------------------- the rules


def best_swap_by(
    score: dict[str, float], roster: list[str], free: dict[str, list[str]], pos_of: dict
) -> tuple[str, str] | None:
    """(add, drop): the position where the best free agent beats the worst rostered player by
    the most, if by more than ADD_MARGIN; `free` lists are best first by `score`."""
    best = None
    for pos in rg.POSITIONS:
        mine = [g for g in roster if pos_of.get(g) == pos]
        if not mine or not free[pos]:
            continue
        worst = min(mine, key=lambda g: score[g])
        gain = score[free[pos][0]] - score[worst]
        if gain > rg.ADD_MARGIN and (best is None or gain > best[0]):
            best = (gain, free[pos][0], worst)
    return None if best is None else (best[1], best[2])


def ros_claim(
    ls: dict, week: int, rosters: list[list[str]], team: int, blocked: set[str]
) -> tuple[str, str] | None:
    """The app's top waiver add (moves.waiver_candidates) if it adds over C_MARGIN points."""
    proj = _flat(ls, week).filter(~pl.col("gsis_id").is_in(list(blocked)))
    pos = ls["facts"]["pos"]
    rows = [(t + 1, g, pos[g]) for t, r in enumerate(rosters) for g in r]
    data = LeagueData(
        roster_ids=list(range(1, len(rosters) + 1)), team_names={}, current_week=week,
        playoff_start=ls["start"], roster_positions=scc.skill_layout(
            ls["lg"]["roster_positions"]),
        rosters=pl.DataFrame(rows, schema={"roster_id": pl.Int64, "gsis_id": pl.String,
                                           "position": pl.String}, orient="row"),
        projections=proj, cv={}, pair_rho={}, pairings={}, wins0={}, points0={},
        k_mean=0.0, k_var=0.0, def_mean=0.0, def_var=0.0,
        positions={g: pos[g] for g in proj["gsis_id"].unique()},
    )  # fmt: skip
    top = moves.waiver_candidates(data, team + 1, top_n=1)
    if not top or top[0].delta_mu <= C_MARGIN:
        return None
    return top[0].gsis_id, top[0].drop_id


def rolling_season(
    ls: dict, initial: list[list[str]], treated: int, rule: str, last_week: int
) -> tuple[dict[int, list[tuple[str, ...]]], int]:
    """Week -> rosters under rolling priority, and the treated team's claims."""
    values, games, pos_of = ls["values"], ls["games"], ls["pos_of"]
    rosters = [list(r) for r in initial]
    priority = list(reversed(range(len(rosters))))
    out = {1: [tuple(r) for r in rosters]}
    claims = 0
    for week in range(2, last_week + 1):
        form = {}
        for g in set(games) | set(values):
            played = [p for wk, p in games.get(g, []) if wk < week][-rg.FORM_GAMES :]
            form[g] = float(np.mean(played)) if played else values.get(g, (None, -np.inf))[1]
        nxt = ls["facts"]["proj"].get(week, {})
        owned = {g for r in rosters for g in r}
        pool = [g for g in set(games) | set(values) | set(nxt) if g not in owned]
        pool = [g for g in pool if pos_of.get(g) in rg.POSITIONS]
        blocked: set[str] = set()  # dropped this week: on waivers until next week
        for t in list(priority):
            mine = rule if t == treated else "A"
            free_now = [g for g in pool if g not in owned and g not in blocked]
            if mine == "C":
                claim = ros_claim(ls, week, rosters, t, blocked)
            else:
                score = form if mine == "A" else defaultdict(float, nxt)
                if mine == "A":
                    free_now = [g for g in free_now if g in form]
                free: dict[str, list[str]] = defaultdict(list)
                for g in sorted(free_now, key=lambda g: -score[g]):
                    free[pos_of[g]].append(g)
                claim = best_swap_by(score, rosters[t], free, pos_of)
            if claim is None:
                continue
            add, drop = claim
            assert add not in owned and drop in rosters[t], (add, drop)
            rosters[t][rosters[t].index(drop)] = add
            owned = (owned - {drop}) | {add}
            blocked.add(drop)
            priority.remove(t)
            priority.append(t)
            claims += t == treated
        out[week] = [tuple(r) for r in rosters]
    return out, claims


# ---------------------------------------------------------------- one draft


def run_unit(unit: tuple[str, int, int]) -> list[dict]:
    lid, season, draft = unit
    ls = _league_season(lid, season)
    lg = ls["lg"]
    layout = lg["roster_positions"]
    size = len(lineup_slots(layout)) + layout.count("BN")
    rng = np.random.default_rng([int(lid) % 2**32, season, draft, ord(CONS.name)])
    initial = rg.draft(ls["values"], lg["num_teams"], size, "SUPER_FLEX" in layout, rng)
    start = ls["start"]
    pairs = scc.random_schedule(
        len(initial), start - 1, np.random.default_rng([scc.unit_seed(lid, season, draft), 1])
    )
    treated = draft % len(initial)
    slots = lineup_slots(layout)
    rows = []
    for rule in RULES:
        by_week, claims = rolling_season(ls, initial, treated, rule, start - 1)
        by_week |= {w: by_week[start - 1] for w in range(start, scc.LAST_WEEK + 1)}
        scores = scc.weekly_scores(by_week, ls["facts"], slots)
        wins, points = scc.standings(scores, pairs, start - 1)
        rows.append(
            {
                "league_id": lid, "season": season, "draft": draft, "rule": rule,
                "wins": float(wins[treated]), "points": float(points[treated]),
                "claims": claims, "league_points": float(points.mean()),
            }
        )  # fmt: skip
    return rows


# ---------------------------------------------------------------- report


def t_of(d: np.ndarray) -> float:
    return float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))) if d.std() > 0 else 0.0


def report(frame: pl.DataFrame) -> None:
    names = rg.league_names()
    base = frame.filter(pl.col("rule") == "A").select(
        "league_id", "season", "draft", pl.col("wins").alias("wins_A"),
        pl.col("points").alias("points_A"),
    )  # fmt: skip
    paired = frame.join(base, on=["league_id", "season", "draft"])
    print("\nmean per team-season (treated team), rule against A (form)")
    rows = []
    for rule in ("B", "C"):
        g = paired.filter(pl.col("rule") == rule)
        for lid in [*sorted(g["league_id"].unique()), "pooled"]:
            h = g if lid == "pooled" else g.filter(pl.col("league_id") == lid)
            dw = (h["wins"] - h["wins_A"]).to_numpy()
            dp = (h["points"] - h["points_A"]).to_numpy()
            rows.append(
                {
                    "rule": rule, "league": names.get(lid, lid), "n": len(dw),
                    "wins": round(float(h["wins"].mean()), 3),
                    "wins_A": round(float(h["wins_A"].mean()), 3),
                    "d_wins": round(float(dw.mean()), 3), "t_wins": round(t_of(dw), 2),
                    "d_points": round(float(dp.mean()), 1), "t_points": round(t_of(dp), 2),
                    "claims": round(float(h["claims"].mean()), 1),
                    **{f"d_wins_{s}": round(float((h.filter(pl.col("season") == s)["wins"]
                       - h.filter(pl.col("season") == s)["wins_A"]).mean()), 3)
                       for s in SEASONS},
                }
            )  # fmt: skip
    table = pl.DataFrame(rows)
    print(table)
    print(f"claims under A: {frame.filter(pl.col('rule') == 'A')['claims'].mean():.1f} a season")
    for rule in ("B", "C"):
        g = table.filter(pl.col("rule") == rule)
        leagues = g.filter(pl.col("league") != "pooled")
        pooled = g.filter(pl.col("league") == "pooled")
        ok = (leagues["d_wins"] > 0).all() and abs(pooled["t_wins"][0]) >= 2
        print(f"verdict {rule}: {'RECOMMEND' if ok else 'report only'}")
    keys = ["league_id", "season", "draft"]
    b, c = (frame.filter(pl.col("rule") == r).sort(keys) for r in ("B", "C"))
    for col in ("wins", "points"):
        d = (c[col] - b[col]).to_numpy()
        print(f"C minus B, {col}: {d.mean():+.3f} (t {t_of(d):.2f}, n {len(d)})")


def real_rankings() -> None:
    """My real teams this week: Waivers page order (extra points) against the digest order."""
    from fantasy import data_api

    for key in ("colgate", "yinzburgh"):
        w = data_api.waivers(key)
        by_points = w.sort("delta_points", descending=True)["full_name"].to_list()
        by_odds = w.sort("playoff_delta", descending=True)["full_name"].to_list()
        top = 5
        rank_p = {n: i for i, n in enumerate(by_points)}
        rank_o = {n: i for i, n in enumerate(by_odds)}
        common = list(rank_p)
        rho = (
            float(np.corrcoef([rank_p[n] for n in common], [rank_o[n] for n in common])[0, 1])
            if len(common) > 2
            else float("nan")
        )
        print(f"\n{key}: {len(w)} adds; rank correlation {rho:.2f}; same top add: "
              f"{by_points[:1] == by_odds[:1]}; top-{top} overlap "
              f"{len(set(by_points[:top]) & set(by_odds[:top]))}")  # fmt: skip
        print(
            w.sort("delta_points", descending=True)
            .select("full_name", "position", "drop_name", "delta_points", "playoff_delta",
                    "title_delta", "se_title")  # fmt: skip
            .head(8)
        )


def main() -> None:
    if "--real" in sys.argv:
        real_rankings()
    cache = Path(__file__).parent / "scratch" / "waiver_rule_rows.parquet"
    if "--cached" in sys.argv and cache.exists():
        report(pl.read_parquet(cache))
        return
    limit = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--drafts=")), DRAFTS)
    todo = [(r["league_id"], s, d) for r in scc.league_rows() for s in SEASONS
            for d in range(limit)]  # fmt: skip
    t0 = time.time()
    check = run_unit(todo[0])
    assert {r["rule"] for r in check} == set(RULES)
    print(f"{len(todo)} drafts; first in {time.time() - t0:.1f}s")
    with get_context("spawn").Pool(scc.WORKERS) as pool:
        rows = [r for chunk in pool.imap_unordered(run_unit, todo, chunksize=2) for r in chunk]
    print(f"done in {time.time() - t0:.0f}s")
    frame = pl.DataFrame(rows)
    cache.parent.mkdir(exist_ok=True)
    frame.write_parquet(cache)
    report(frame)


if __name__ == "__main__":
    main()
