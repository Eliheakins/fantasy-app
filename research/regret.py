"""Decision yardstick: score a projection set by the start/sit choices it drives, not by RMSE.

RMSE over every player-game mostly weighs players nobody starts. Here a projection picks each
roster's lineup (`sim.lineup.auto_lineup`, each league's real skill slots; K and DEF are left out)
and is charged the regret: points of the hindsight-best lineup from the same roster minus the
actual points of the lineup it chose. Scored on 2024 and 2025 weeks 1 to 17 and 2026 weeks 1 to 6.

Population: player-games with a `proj_learned` row (players who took the field). A rostered player
with no game that week is out for both the choice and the hindsight lineup, as if his manager knew
he was out. A candidate missing a row in this population gets the learned projection there
(coverage is printed).

Rosters. Past seasons have no rosters, so they are built reproducibly (numpy seed per league and
season), DRAFTS drafts per league-season, each team keeping skill slots plus bench (14 players):
  A (primary) the league's 10 teams; snake draft on prior-season points per game (4 or more
    games, the league's scoring) minus the value at a replacement rank per position, plus normal
    noise of DRAFT_NOISE points (draft-day disagreement); position caps and a rule that the last
    picks fill missing starting positions. Players with no prior season (rookies) go undrafted.
    Before each week from 2, every team (random order) may swap its worst player at a position
    (by form: mean of the last FORM_GAMES games, else the pre-season value) for the best free
    agent there if the free agent's form is ADD_MARGIN points higher; one swap a week.
  B (robustness) 12 teams, pre-season value from the uncalibrated baseline's week-1 projection,
    two swaps a week. Same everything else.
Rosters never depend on the candidate, so every candidate is scored on the same roster-weeks.
  real 2026 weeks 1 to 6: the leagues' actual rosters (matchup_players, starters and bench).

Flex-cutoff error: per roster-week, the cutoff is the projection of the player in the widest slot
the lineup filled last (SUPER_FLEX in Colgate, FLEX in YinzBurgh); the band is the roster players
eligible for that slot projected within BAND points of it. A candidate is compared with the
reference on the union of both models' bands, so both are scored on the same player-games.

Paired per-week t: per league and week, the mean over roster-weeks of reference regret minus
candidate regret (positive: candidate better), t over weeks; the same on band and all-row squared
error. Verdict (fixed before scoring): a candidate wins on decisions if its regret is lower in both
leagues, pooled weekly |t| >= 2 in at least one, and no league-season t <= -1 (construction A).

Run from the repo root:
  OMP_NUM_THREADS=3 uv run python research/regret.py [name=path.parquet ...]
Each file: league_id, gsis_id, season, week, projection. `learned` (proj_learned, the reference)
and `baseline` (size-calibrated with earlier seasons' curves, `wf_panel.calibrated_baseline`) are
always scored. `--ref=name` makes another candidate the reference (for a null such as a two-seed
average).
"""

import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
import wf_panel as w  # noqa: E402

from fantasy import store  # noqa: E402
from fantasy.sim.lineup import ELIGIBLE, Player, auto_lineup, lineup_slots  # noqa: E402

LAST_WEEK = {2024: 17, 2025: 17, 2026: 6}
POSITIONS = ("QB", "RB", "WR", "TE")
KEY = ["league_id", "gsis_id", "season", "week"]
DRAFTS = 100  # 20 left the verdict hinging on the draw (seed salts flipped it)
DRAFT_NOISE = 2.0  # points per game
MIN_PRIOR_GAMES = 4
FORM_GAMES = 3
ADD_MARGIN = 2.0  # points per game
BAND = 3.0  # projected points around the cutoff
MIN_START = {"QB": 1, "RB": 2, "WR": 2, "TE": 1}
REPLACEMENT = {"QB": 1.0, "RB": 2.5, "WR": 3.0, "TE": 1.0}  # x teams; QB doubled in Super Flex
REF = "learned"
pl.Config(tbl_rows=200, tbl_cols=20, tbl_width_chars=220)


@dataclass(frozen=True)
class Construction:
    name: str
    extra_teams: int
    preseason: str  # "ppg" or "proj"
    adds: int


CONSTRUCTIONS = (Construction("A", 0, "ppg", 1), Construction("B", 2, "proj", 2))


# ---------------------------------------------------------------- data


def universe() -> pl.DataFrame:
    """KEY, position, points, learned for the scored league-weeks."""
    learned = store.read_table("proj_learned").filter(~pl.col("is_future"))
    points = store.read_table("player_points").filter(pl.col("season_type") == "REG")
    in_scope = pl.any_horizontal(
        [(pl.col("season") == s) & (pl.col("week") <= wk) for s, wk in LAST_WEEK.items()]
    )
    return (
        learned.filter(in_scope & pl.col("position").is_in(POSITIONS))
        .select(*KEY, "position", pl.col("projection").alias(REF))
        .join(points.select(*KEY, "points"), on=KEY)
    )


def with_candidates(uni: pl.DataFrame, files: dict[str, str]) -> tuple[pl.DataFrame, list[str]]:
    base = w.calibrated_baseline().select(*KEY, "baseline")
    uni = uni.join(base, on=KEY, how="left")
    sources = {"baseline": None, **files}
    for name, path in files.items():
        cand = pl.read_parquet(path).select(*KEY, pl.col("projection").alias(name))
        uni = uni.join(cand.unique(KEY), on=KEY, how="left")
    for name in sources:
        print(f"coverage {name}: {uni[name].is_not_null().mean():.4f} of {uni.height} rows")
        uni = uni.with_columns(pl.col(name).fill_null(pl.col(REF)))
    return uni, [REF, *sources]


# ---------------------------------------------------------------- rosters


def preseason_values(
    cons: Construction, lid: str, season: int, points: pl.DataFrame, baseline: pl.DataFrame
) -> dict[str, tuple[str, float]]:
    """gsis_id -> (position, value) known before the season."""
    if cons.preseason == "ppg":
        frame = (
            points.filter((pl.col("league_id") == lid) & (pl.col("season") == season - 1))
            .group_by("gsis_id")
            .agg(pl.col("position").last(), pl.col("points").mean().alias("v"), pl.len().alias("n"))
            .filter(pl.col("n") >= MIN_PRIOR_GAMES)
        )
    else:
        frame = baseline.filter(
            (pl.col("league_id") == lid) & (pl.col("season") == season) & (pl.col("week") == 1)
        ).select("gsis_id", "position", pl.col("projection").alias("v"))
    frame = frame.filter(pl.col("position").is_in(POSITIONS))
    return {r["gsis_id"]: (r["position"], r["v"]) for r in frame.iter_rows(named=True)}


def draft(
    values: dict[str, tuple[str, float]], teams: int, size: int, sf: bool, rng: np.random.Generator
) -> list[list[str]]:
    """Snake draft on value over a replacement rank plus noise, with caps and starter needs."""
    by_pos: dict[str, list[float]] = defaultdict(list)
    for pos, v in values.values():
        by_pos[pos].append(v)
    repl = {}
    for pos in POSITIONS:
        ranked = sorted(by_pos[pos], reverse=True)
        rank = int(REPLACEMENT[pos] * teams * (2 if sf and pos == "QB" else 1))
        repl[pos] = ranked[min(rank, len(ranked) - 1)] if ranked else 0.0
    ids = sorted(values)
    noisy = {g: values[g][1] - repl[values[g][0]] + rng.normal(0, DRAFT_NOISE) for g in ids}
    order = sorted(ids, key=lambda g: -noisy[g])
    caps = {"QB": 3 if sf else 2, "RB": 6, "WR": 6, "TE": 2}
    rosters: list[list[str]] = [[] for _ in range(teams)]
    counts = [Counter() for _ in range(teams)]
    taken: set[str] = set()
    for rnd in range(size):
        for t in range(teams) if rnd % 2 == 0 else reversed(range(teams)):
            short = {p: n - counts[t][p] for p, n in MIN_START.items() if counts[t][p] < n}
            must = sum(short.values()) >= size - len(rosters[t])
            pick = next(
                (
                    g
                    for g in order
                    if g not in taken
                    and counts[t][values[g][0]] < caps[values[g][0]]
                    and (not must or values[g][0] in short)
                ),
                None,
            )
            if pick is None:
                continue
            taken.add(pick)
            rosters[t].append(pick)
            counts[t][values[pick][0]] += 1
    return rosters


def season_rosters(
    initial: list[list[str]],
    values: dict[str, tuple[str, float]],
    games: dict[str, list[tuple[int, float]]],
    positions: dict[str, str],
    cons: Construction,
    last_week: int,
    rng: np.random.Generator,
) -> dict[int, list[tuple[str, ...]]]:
    """Week -> rosters, with free-agent swaps by form before each week from 2."""
    rosters = [list(r) for r in initial]
    out = {1: [tuple(r) for r in rosters]}
    pos_of = {**positions, **{g: p for g, (p, _) in values.items()}}
    for week in range(2, last_week + 1):

        def form(g: str, week: int = week) -> float:
            played = [p for wk, p in games.get(g, []) if wk < week][-FORM_GAMES:]
            if played:
                return float(np.mean(played))
            return values[g][1] if g in values else -np.inf

        owned = {g for r in rosters for g in r}
        free: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for g in set(games) | set(values):
            if g not in owned and pos_of.get(g) in POSITIONS:
                free[pos_of[g]].append((form(g), g))
        for pos in free:
            free[pos].sort(reverse=True)
        for t in rng.permutation(len(rosters)):
            for _ in range(cons.adds):
                best = None
                for pos in POSITIONS:
                    mine = [g for g in rosters[t] if pos_of.get(g) == pos]
                    if not mine or not free[pos]:
                        continue
                    worst = min(mine, key=form)
                    gain = free[pos][0][0] - form(worst)
                    if gain > ADD_MARGIN and (best is None or gain > best[0]):
                        best = (gain, pos, worst)
                if best is None:
                    break
                _, pos, worst = best
                _, added = free[pos].pop(0)
                rosters[t][rosters[t].index(worst)] = added
        out[week] = [tuple(r) for r in rosters]
    return out


def built_rosters(cons: Construction, uni: pl.DataFrame) -> pl.DataFrame:
    """construction, league_id, season, week, team, gsis_id."""
    leagues = store.read_table("leagues", "raw")
    points = store.read_table("player_points").filter(
        (pl.col("season_type") == "REG") & pl.col("position").is_in(POSITIONS)
    )
    baseline = store.read_table("proj_baseline").filter(~pl.col("is_future"))
    rows = []
    for lg in leagues.iter_rows(named=True):
        lid, layout = lg["league_id"], lg["roster_positions"]
        teams = lg["num_teams"] + cons.extra_teams
        size = len(lineup_slots(layout)) + layout.count("BN")
        sf = "SUPER_FLEX" in layout
        for season, last_week in LAST_WEEK.items():
            values = preseason_values(cons, lid, season, points, baseline)
            this = points.filter((pl.col("league_id") == lid) & (pl.col("season") == season))
            games: dict[str, list[tuple[int, float]]] = defaultdict(list)
            positions = {}
            for r in this.sort("week").iter_rows(named=True):
                games[r["gsis_id"]].append((r["week"], r["points"]))
                positions[r["gsis_id"]] = r["position"]
            for d in range(DRAFTS):
                rng = np.random.default_rng([int(lid) % 2**32, season, d, ord(cons.name)])
                initial = draft(values, teams, size, sf, rng)
                weekly = season_rosters(initial, values, games, positions, cons, last_week, rng)
                for week, rosters in weekly.items():
                    for t, roster in enumerate(rosters):
                        rows += [(cons.name, lid, season, week, d * 100 + t, g) for g in roster]
    return pl.DataFrame(
        rows,
        schema=["construction", "league_id", "season", "week", "team", "gsis_id"],
        orient="row",
    )


def real_rosters() -> pl.DataFrame:
    """2026 weeks 1 to 6 as the leagues actually rostered them."""
    ids = (
        store.read_table("id_map")
        .select("sleeper_id", pl.col("gsis_id").str.strip_chars())
        .filter(pl.col("gsis_id").is_not_null())
    )
    return (
        store.read_table("matchup_players", "raw")
        .filter(pl.col("week") <= LAST_WEEK[2026])
        .join(ids, on="sleeper_id")
        .select(
            pl.lit("real").alias("construction"),
            "league_id",
            pl.lit(2026).alias("season"),
            "week",
            pl.col("roster_id").alias("team"),
            "gsis_id",
        )
    )


# ---------------------------------------------------------------- scoring


def score_rosters(
    rosters: pl.DataFrame, uni: pl.DataFrame, cands: list[str], ref: str = REF
) -> pl.DataFrame:
    """One row per roster-week and candidate: regret, regret by position, band squared errors
    against the reference on the union of both bands."""
    layouts = {
        r["league_id"]: lineup_slots(r["roster_positions"])
        for r in store.read_table("leagues", "raw").iter_rows(named=True)
    }
    groups = (
        rosters.join(uni, on=["league_id", "gsis_id", "season", "week"])
        .group_by("construction", "league_id", "season", "week", "team")
        .agg("gsis_id", "position", "points", *cands)
    )
    out = []
    for r in groups.iter_rows(named=True):
        slots, ids, pos = layouts[r["league_id"]], r["gsis_id"], r["position"]
        pts = dict(zip(ids, r["points"], strict=True))
        pos_of = dict(zip(ids, pos, strict=True))
        best = auto_lineup(
            [Player(i, p, v) for i, p, v in zip(ids, pos, r["points"], strict=True)], slots
        )
        per = {}
        for c in cands:
            proj = dict(zip(ids, r[c], strict=True))
            chosen = auto_lineup(
                [Player(i, p, proj[i]) for i, p in zip(ids, pos, strict=True)], slots
            )
            regret = best.total - sum(pts[i] for i in chosen.players)
            assert regret >= -1e-9, regret
            by_pos = {
                f"r_{p}": sum(pts[i] for i in best.players if pos_of[i] == p)
                - sum(pts[i] for i in chosen.players if pos_of[i] == p)
                for p in POSITIONS
            }
            band: set[str] = set()
            if chosen.slots:
                slot, last = chosen.slots[-1]
                band = {
                    i
                    for i in ids
                    if pos_of[i] in ELIGIBLE[slot] and abs(proj[i] - proj[last]) <= BAND
                }
            per[c] = (regret, by_pos, band, proj)
        ref_band, ref_proj = per[ref][2], per[ref][3]
        for c, (regret, by_pos, band, proj) in per.items():
            both = band | ref_band
            out.append(
                {
                    **{k: r[k] for k in ("construction", "league_id", "season", "week", "team")},
                    "cand": c,
                    "regret": regret,
                    **by_pos,
                    "band_n": len(both),
                    "band_se": sum((pts[i] - proj[i]) ** 2 for i in both),
                    "band_se_ref": sum((pts[i] - ref_proj[i]) ** 2 for i in both),
                }
            )
    return pl.DataFrame(out)


def t_of(diff: np.ndarray) -> float:
    if len(diff) < 3 or diff.std(ddof=1) == 0:
        return 0.0  # the reference against itself
    return float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff))))


def weekly(scored: pl.DataFrame, uni: pl.DataFrame, ref: str = REF) -> pl.DataFrame:
    """Per construction, league, candidate, season and week: mean regret, the reference's, band
    and all-row squared error sums."""
    regret = scored.group_by("construction", "league_id", "cand", "season", "week").agg(
        pl.col("regret").mean(),
        *[pl.col(f"r_{p}").mean() for p in POSITIONS],
        pl.col("band_n").sum(),
        pl.col("band_se").sum(),
        pl.col("band_se_ref").sum(),
    )
    ref_rows = regret.filter(pl.col("cand") == ref).select(
        "construction",
        "league_id",
        "season",
        "week",
        pl.col("regret").alias("regret_ref"),
        *[pl.col(f"r_{p}").alias(f"r_{p}_ref") for p in POSITIONS],
    )
    cands = scored["cand"].unique().to_list()
    se = uni.group_by("league_id", "season", "week").agg(
        pl.len().alias("all_n"),
        ((pl.col("points") - pl.col(ref)) ** 2).sum().alias("all_se_ref"),
        *[((pl.col("points") - pl.col(c)) ** 2).sum().alias(f"se_{c}") for c in cands],
    )
    se = se.unpivot(
        index=["league_id", "season", "week", "all_n", "all_se_ref"],
        on=[f"se_{c}" for c in cands],
        variable_name="cand",
        value_name="all_se",
    ).with_columns(pl.col("cand").str.strip_prefix("se_"))
    return regret.join(ref_rows, on=["construction", "league_id", "season", "week"]).join(
        se, on=["league_id", "season", "week", "cand"]
    )


def league_names() -> dict[str, str]:
    leagues = store.read_table("leagues", "raw")
    return dict(zip(leagues["league_id"], leagues["league_key"], strict=True))


def summary(wk: pl.DataFrame) -> pl.DataFrame:
    names = league_names()
    rows = []
    for (cons, lid, cand), g in wk.group_by(
        "construction", "league_id", "cand", maintain_order=True
    ):
        g = g.sort("season", "week")
        d_reg = (g["regret_ref"] - g["regret"]).to_numpy()
        band_mse_ref = (g["band_se_ref"] / g["band_n"]).to_numpy()
        band_mse = (g["band_se"] / g["band_n"]).to_numpy()
        all_mse = (g["all_se"] / g["all_n"]).to_numpy()
        all_mse_ref = (g["all_se_ref"] / g["all_n"]).to_numpy()
        seasons = {
            s: t_of((gs["regret_ref"] - gs["regret"]).to_numpy())
            for (s,), gs in g.group_by("season", maintain_order=True)
        }
        rows.append(
            {
                "cons": cons,
                "league": names[lid],
                "cand": cand,
                "weeks": g.height,
                "regret": round(float(g["regret"].mean()), 3),
                "d_regret": round(float(d_reg.mean()), 3),
                "t_regret": round(t_of(d_reg), 2),
                **{f"t_{s}": round(t, 2) for s, t in sorted(seasons.items())},
                "QB_d": round(float((g["r_QB_ref"] - g["r_QB"]).mean()), 3),
                "QB_t": round(t_of((g["r_QB_ref"] - g["r_QB"]).to_numpy()), 2),
                "band_rmse": round(float(np.sqrt(g["band_se"].sum() / g["band_n"].sum())), 3),
                "band_rmse_ref": round(
                    float(np.sqrt(g["band_se_ref"].sum() / g["band_n"].sum())), 3
                ),
                "t_band": round(t_of(band_mse_ref - band_mse), 2),
                "rmse": round(float(np.sqrt(g["all_se"].sum() / g["all_n"].sum())), 4),
                "t_rmse": round(t_of(all_mse_ref - all_mse), 2),
            }
        )
    return pl.DataFrame(rows)


def by_position(wk: pl.DataFrame) -> pl.DataFrame:
    """Regret split by position (hindsight points minus chosen points at that position)."""
    names = league_names()
    rows = []
    for (cons, lid, cand), g in wk.group_by(
        "construction", "league_id", "cand", maintain_order=True
    ):
        for p in POSITIONS:
            d = (g[f"r_{p}_ref"] - g[f"r_{p}"]).to_numpy()
            rows.append(
                {
                    "cons": cons,
                    "league": names[lid],
                    "cand": cand,
                    "pos": p,
                    "regret": round(float(g[f"r_{p}"].mean()), 3),
                    "d": round(float(d.mean()), 3),
                    "t": round(t_of(d), 2),
                }
            )
    return pl.DataFrame(rows)


def verdict(table: pl.DataFrame, cons: str, ref: str = REF) -> dict[str, str]:
    out = {}
    for (cand,), g in table.filter(pl.col("cons") == cons).group_by("cand"):
        if cand == ref:
            continue
        season_ts = [v for c in g.columns if c.startswith("t_20") for v in g[c].to_list()]
        wins = (
            (g["d_regret"] > 0).all() and (g["t_regret"].abs() >= 2).any() and min(season_ts) > -1
        )
        out[cand] = "WINS" if wins else "no"
    return out


def self_check(uni: pl.DataFrame, rosters: pl.DataFrame) -> None:
    """Scoring the actual points as a projection must give zero regret everywhere."""
    sample = rosters.filter(pl.col("week") == 3)
    oracle = uni.with_columns(pl.col("points").alias("oracle"))
    scored = score_rosters(sample, oracle, [REF, "oracle"])
    assert scored.filter(pl.col("cand") == "oracle")["regret"].abs().max() < 1e-9
    assert scored.filter(pl.col("cand") == REF)["regret"].mean() > 0


def main() -> None:
    args = dict(arg.split("=", 1) for arg in sys.argv[1:])
    ref = args.pop("--ref", REF)  # another candidate as the reference, e.g. a null average
    files = args
    uni, cands = with_candidates(universe(), files)
    rosters = pl.concat(
        [*(built_rosters(c, uni) for c in CONSTRUCTIONS), real_rosters()], how="vertical_relaxed"
    )
    self_check(uni, rosters)
    cover = (
        rosters.join(uni, on=["league_id", "gsis_id", "season", "week"])
        .group_by("construction")
        .agg(pl.len().alias("player_weeks_in_play"))
    )
    print(cover)
    wk = weekly(score_rosters(rosters, uni, cands, ref), uni, ref)
    table = summary(wk)
    print(f"\npositive d_regret / t: candidate's regret lower than {ref}'s (points per team-week)")
    print(table.sort("cons", "league", "cand"))
    print("\nregret by position, construction A (hindsight minus chosen points at the position)")
    print(by_position(wk).filter(pl.col("cons") == "A").sort("league", "cand", "pos"))
    for cons in ("A", "B", "real"):
        print(f"verdict {cons}: {verdict(table, cons, ref)}")


if __name__ == "__main__":
    main()
