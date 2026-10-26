"""Questionable players and the swap at inactives: start by p * E, or by E with a bench swap?

Today a Questionable (or Doubtful) player's lineup value is p * E (chance of playing times points
when he plays), so he starts only if that beats the bench. A manager can instead start him and,
when the inactives come out 90 minutes before his kickoff, swap him for a bench player whose game
has not started yet. Policies, each scored on actual lineup points:
  A       start by p * E, no swap (the app before the swap plan).
  A+plan  start by p * E; an inactive flagged starter is replaced by the bench player the app's
          plan names for him (`sim.lineup.swap_plan`: kickoff order, best eligible bench player
          kicking off after his inactives release, each promised once). What the app supports.
  A+s     start by p * E, re-set the whole lineup at each inactives release (a manager who also
          starts a benched flagged player once he is active; the plan does not advise that).
  B       start by E; at each flagged player's inactives release, if he is inactive, re-set the
          lineup with every player whose game has started locked (`lineup_with_locks`).
  C       B for flagged starters the swap plan covers, A (p * E) for the others (reference: it
          shipped in the first round and was withdrawn after review).

Rosters, slots and the hindsight-best lineup come from `research/regret.py` (constructions A and
B, 2024 and 2025 weeks 1 to 17; the real 2026 rosters for weeks 1 to 6). Its population (players
with a `proj_learned` row) is extended with every Questionable and Doubtful skill player-week in
`nfl_injuries`, including those who sat (actual 0). Out players stay out of the population (their
manager knows), as do unflagged players with no game.
  E: `proj_learned` (points when he plays). A flagged player who sat has no row for that game, so
     he takes his latest earlier `proj_learned` row of the season (rows with none are dropped,
     counted).
  p: the availability classifier (`stages/availability.py`), walk-forward by season (fit on
     seasons before, predict the season). A flagged player outside its universe takes the rate
     of his status and practice among the training rows.
  Inactive: no snaps row (any phase) and no `player_points` row for the game.
  Kickoffs: `nfl_schedules` (US Eastern).

Paired per week: per construction, league and week, the mean over every team-week of policy minus
A points, t over weeks. Ship rule (fixed before the first run): B or C ships if its actual lineup
points are higher in both leagues, pooled weekly |t| >= 2 in at least one, and no league-season
t <= -1, in both roster constructions A and B. The same rule is reported for A+plan and A+s.

Run from the repo root:  OMP_NUM_THREADS=3 uv run python research/questionable_swap_check.py
"""

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
import regret as r  # noqa: E402

from fantasy import store  # noqa: E402
from fantasy.sim.lineup import (  # noqa: E402
    INACTIVES_LEAD,
    Lineup,
    Player,
    auto_lineup,
    lineup_slots,
    lineup_with_locks,
    swap_plan,
)
from fantasy.stages import availability as av  # noqa: E402

FLAGS = ("Questionable", "Doubtful")
INACTIVES = INACTIVES_LEAD
POLICIES = ("A", "A+plan", "A+s", "B", "C")
SEASONS = tuple(r.LAST_WEEK)
KEY3 = ["gsis_id", "season", "week"]


@dataclass(frozen=True)
class Slot:
    """One rostered player-game in a team-week."""

    id: str
    position: str
    e: float  # points when he plays
    p: float  # chance of playing (1 for unflagged players)
    flagged: bool
    active: bool
    points: float
    kick: datetime


# ---------------------------------------------------------------- inputs


def chance_of_playing() -> pl.DataFrame:
    """gsis_id, season, week, p for every flagged skill player-week, walk-forward by season."""
    rows = av.build_rows()
    out = []
    for season in SEASONS:
        train, test = (
            rows.filter(pl.col("season") < season),
            rows.filter((pl.col("season") == season) & pl.col("status").is_in(FLAGS)),
        )
        pred = av.fit_predict(av.design(train), train["played"].to_numpy(), av.design(test))
        out.append(test.select(*KEY3, pl.Series("p_clf", pred)))
        rate = train.group_by("status", "practice").agg(pl.col("played").mean().alias("p_rate"))
        out.append(rate.with_columns(pl.lit(season).alias("season")))
    clf = pl.concat([o for o in out if "p_clf" in o.columns])
    rates = pl.concat([o for o in out if "p_rate" in o.columns])
    flagged = flagged_reports()
    return (
        flagged.join(clf.unique(KEY3), on=KEY3, how="left")
        .join(rates, on=["season", "status", "practice"], how="left")
        .with_columns(
            pl.col("p_clf").is_not_null().alias("from_classifier"),
            pl.coalesce("p_clf", "p_rate").alias("p"),
        )
        .select(*KEY3, "status", "team", "position", "p", "from_classifier")
    )


def flagged_reports() -> pl.DataFrame:
    """Questionable and Doubtful skill player-weeks in the scored seasons."""
    in_scope = pl.any_horizontal(
        [(pl.col("season") == s) & (pl.col("week") <= wk) for s, wk in r.LAST_WEEK.items()]
    )
    return (
        store.read_table("nfl_injuries", "raw")
        .filter(
            (pl.col("game_type") == "REG")
            & pl.col("report_status").is_in(FLAGS)
            & pl.col("position").is_in(r.POSITIONS)
            & in_scope
        )
        .unique(KEY3, keep="first", maintain_order=True)
        .select(
            *KEY3,
            "team",
            "position",
            pl.col("report_status").alias("status"),
            pl.when(pl.col("practice_status").str.contains("Did Not|DNP"))
            .then(pl.lit("dnp"))
            .when(pl.col("practice_status").str.contains("Limited"))
            .then(pl.lit("limited"))
            .otherwise(pl.lit("full"))
            .alias("practice"),
        )
    )


def kickoffs() -> pl.DataFrame:
    """team, season, week, kick (naive US Eastern)."""
    games = store.read_table("nfl_schedules", "raw").filter(pl.col("game_type") == "REG")
    kick = (pl.col("gameday") + " " + pl.col("gametime")).str.to_datetime("%Y-%m-%d %H:%M")
    both = [
        games.select(pl.col(side).alias("team"), "season", "week", kick.alias("kick"))
        for side in ("home_team", "away_team")
    ]
    return pl.concat(both)


def population() -> tuple[pl.DataFrame, dict[str, int]]:
    """regret.py's universe plus flagged player-weeks, with e, p, flagged, active, kick."""
    learned = store.read_table("proj_learned").filter(~pl.col("is_future"))
    uni = r.universe().join(
        learned.select(*r.KEY, "team"), on=r.KEY, how="left"
    )  # KEY, position, learned, points, team
    chance = chance_of_playing()
    leagues = store.read_table("leagues", "raw")["league_id"].to_list()
    flagged = pl.concat([chance.with_columns(pl.lit(lid).alias("league_id")) for lid in leagues])
    points = store.read_table("player_points").filter(pl.col("season_type") == "REG")
    extra = flagged.join(uni.select(r.KEY), on=r.KEY, how="anti")
    prior = learned.select(*r.KEY, pl.col("projection").alias("learned")).sort("week")
    extra = (
        extra.sort("week")
        .join_asof(
            prior,
            on="week",
            by=["league_id", "gsis_id", "season"],
            strategy="backward",
            allow_exact_matches=False,
        )
        .join(points.select(*r.KEY, "points"), on=r.KEY, how="left")
    )
    counts = {
        "flagged rows (per league)": flagged.height // len(leagues),
        "flagged rows already in the universe": (flagged.height - extra.height) // len(leagues),
        "added, no earlier projection (dropped)": int(extra["learned"].null_count())
        // len(leagues),
        "p from the classifier": int(chance["from_classifier"].sum()),
    }
    extra = extra.filter(pl.col("learned").is_not_null()).with_columns(
        pl.col("points").fill_null(0.0)
    )
    snapped = store.read_table("nfl_snaps", "raw").filter(pl.col("gsis_id").is_not_null())
    snapped = snapped.select(KEY3).unique().with_columns(pl.lit(True).alias("snap_row"))
    played = points.select(*r.KEY).with_columns(pl.lit(True).alias("point_row"))
    full = (
        pl.concat(
            [
                uni.select(*r.KEY, "position", "team", "learned", "points"),
                extra.select(*r.KEY, "position", "team", "learned", "points"),
            ]
        )
        .join(flagged.select(*r.KEY, "p"), on=r.KEY, how="left")
        .join(snapped, on=KEY3, how="left")
        .join(played, on=r.KEY, how="left")
        .join(kickoffs(), on=["team", "season", "week"], how="left")
        .with_columns(
            pl.col("p").is_not_null().alias("flagged"),
            pl.col("p").fill_null(1.0),
            (pl.col("snap_row").fill_null(False) | pl.col("point_row").fill_null(False)).alias(
                "active"
            ),
        )
    )
    counts["flagged rows who sat"] = int(
        full.filter(pl.col("flagged") & ~pl.col("active")).height // len(leagues)
    )
    counts["rows without a kickoff"] = int(full["kick"].null_count())
    return full.drop("snap_row", "point_row"), counts


# ---------------------------------------------------------------- policies


def _lineup(players: list[Slot], values: dict[str, float], slots: list[str]) -> Lineup:
    return auto_lineup([Player(p.id, p.position, values[p.id]) for p in players], slots)


def plan_for(players: list[Slot], values: dict[str, float], lineup: Lineup) -> dict[str, str]:
    """The app's swap plan (`sim.lineup.swap_plan`): kickoff order, no bench player reused."""
    pool = [Player(p.id, p.position, values[p.id]) for p in players]
    flagged = {p.id for p in players if p.flagged}
    return swap_plan(lineup, pool, flagged, {p.id: p.kick for p in players}, set())


def opening_values(players: list[Slot], policy: str, slots: list[str]) -> dict[str, float]:
    """Values the lineup is first set by. C keeps E only for flagged starters the swap plan
    covers (each bench player promised once)."""
    full = {p.id: p.e for p in players}
    discounted = {p.id: p.p * p.e for p in players}
    if policy in ("A", "A+plan", "A+s"):
        return discounted
    if policy == "B":
        return full
    values = dict(full)
    while True:  # each pass moves a flagged starter to p * E, so this ends
        lineup = _lineup(players, values, slots)
        plan = plan_for(players, values, lineup)
        uncovered = [
            x
            for x in players
            if x.flagged and x.id in lineup.players and values[x.id] == x.e and x.id not in plan
        ]
        if not uncovered:
            return values
        for x in uncovered:
            values[x.id] = discounted[x.id]


def play_week(players: list[Slot], policy: str, slots: list[str]) -> tuple[float, frozenset[str]]:
    """Actual points of the lineup the policy ends with, and that lineup."""
    values = opening_values(players, policy, slots)
    lineup = _lineup(players, values, slots)
    if policy == "A":
        return sum(p.points for p in players if p.id in lineup.players), lineup.players
    if policy == "A+plan":  # each inactive flagged starter is replaced by his planned player
        plan = plan_for(players, values, lineup)
        inactive = {p.id for p in players if p.flagged and not p.active}
        final = {plan.get(i, i) if i in inactive else i for i in lineup.players}
        final = frozenset(i for i in final if i not in inactive)
        return sum(p.points for p in players if p.id in final), final
    gone: set[str] = set()
    for release in sorted({p.kick - INACTIVES for p in players if p.flagged}):
        news = [p for p in players if p.flagged and p.kick - INACTIVES == release]
        for p in news:
            if p.active:
                values[p.id] = p.e
            else:
                gone.add(p.id)
        pool = [Player(p.id, p.position, values[p.id]) for p in players if p.id not in gone]
        locked = {p.id for p in players if p.kick <= release}
        lineup = lineup_with_locks(pool, slots, locked, set(lineup.players) - gone)
    return sum(p.points for p in players if p.id in lineup.players), lineup.players


def score(rosters: pl.DataFrame, pop: pl.DataFrame) -> pl.DataFrame:
    """Per roster-week: points and regret of each policy, flags rostered, lineups differ."""
    layouts = {
        row["league_id"]: lineup_slots(row["roster_positions"])
        for row in store.read_table("leagues", "raw").iter_rows(named=True)
    }
    cols = ["gsis_id", "position", "learned", "p", "flagged", "active", "points", "kick"]
    groups = (
        rosters.join(pop, on=["league_id", "gsis_id", "season", "week"])
        .group_by("construction", "league_id", "season", "week", "team")
        .agg(*cols)
    )
    out = []
    for g in groups.iter_rows(named=True):
        slots = layouts[g["league_id"]]
        players = [
            Slot(i, pos, e, p, f, a, pts, k or datetime.max - INACTIVES)
            for i, pos, e, p, f, a, pts, k in zip(*(g[c] for c in cols), strict=True)
        ]
        best = auto_lineup([Player(p.id, p.position, p.points) for p in players], slots).total
        row = {k: g[k] for k in ("construction", "league_id", "season", "week", "team")}
        row["n_flagged"] = sum(p.flagged for p in players)
        if row["n_flagged"] == 0:
            pts = auto_lineup([Player(p.id, p.position, p.e) for p in players], slots)
            total = sum(p.points for p in players if p.id in pts.players)
            row |= {f"pts_{k}": total for k in POLICIES} | {f"diff_{k}": False for k in POLICIES}
        else:
            results = {k: play_week(players, k, slots) for k in POLICIES}
            row |= {f"pts_{k}": v[0] for k, v in results.items()}
            row |= {f"diff_{k}": v[1] != results["A"][1] for k, v in results.items()}
        row["best"] = best
        out.append(row)
    return pl.DataFrame(out)


# ---------------------------------------------------------------- summary


def summary(scored: pl.DataFrame) -> pl.DataFrame:
    names = r.league_names()
    weekly = scored.group_by("construction", "league_id", "season", "week").agg(
        pl.len().alias("n"),
        *[(pl.col(f"pts_{k}") - pl.col("pts_A")).mean().alias(f"d_{k}") for k in POLICIES],
    )
    rows = []
    for (cons, lid), g in scored.group_by("construction", "league_id", maintain_order=True):
        wk = weekly.filter((pl.col("construction") == cons) & (pl.col("league_id") == lid))
        for k in POLICIES[1:]:
            d = wk.sort("season", "week")[f"d_{k}"].to_numpy()
            seasons = {
                s: r.t_of(gs[f"d_{k}"].to_numpy())
                for (s,), gs in wk.group_by("season", maintain_order=True)
            }
            rows.append(
                {
                    "cons": cons,
                    "league": names[lid],
                    "policy": k,
                    "team_weeks": g.height,
                    "with_flag": int((g["n_flagged"] > 0).sum()),
                    "changed": int(g[f"diff_{k}"].sum()),
                    "pts_A": round(float(g["pts_A"].mean()), 3),
                    "pts": round(float(g[f"pts_{k}"].mean()), 3),
                    "regret_A": round(float((g["best"] - g["pts_A"]).mean()), 3),
                    "regret": round(float((g["best"] - g[f"pts_{k}"]).mean()), 3),
                    "d_pts": round(float(np.mean(d)), 4),
                    "t": round(r.t_of(d), 2),
                    **{f"t_{s}": round(t, 2) for s, t in sorted(seasons.items())},
                    "d_changed": round(
                        float((g[f"pts_{k}"] - g["pts_A"]).filter(g[f"diff_{k}"]).mean() or 0.0),
                        2,
                    ),
                }
            )
    return pl.DataFrame(rows)


def versus(scored: pl.DataFrame, cand: str, ref: str) -> pl.DataFrame:
    """Mean points of `cand` minus `ref` per team-week and the pooled weekly t."""
    names = r.league_names()
    weekly = scored.group_by("construction", "league_id", "season", "week").agg(
        (pl.col(f"pts_{cand}") - pl.col(f"pts_{ref}")).mean().alias("d")
    )
    rows = []
    for (cons, lid), g in weekly.group_by("construction", "league_id", maintain_order=True):
        d = g.sort("season", "week")["d"].to_numpy()
        rows.append(
            {
                "cons": cons,
                "league": names[lid],
                "d_pts": round(float(d.mean()), 4),
                "t": round(r.t_of(d), 2),
            }
        )
    return pl.DataFrame(rows).sort("cons", "league")


def verdict(table: pl.DataFrame, policy: str) -> str:
    ok = []
    for cons in ("A", "B"):
        g = table.filter((pl.col("cons") == cons) & (pl.col("policy") == policy))
        season_ts = [v for c in g.columns if c.startswith("t_20") for v in g[c].drop_nulls()]
        ok.append(
            bool((g["d_pts"] > 0).all()) and bool((g["t"].abs() >= 2).any()) and min(season_ts) > -1
        )
    return "SHIPS" if all(ok) else f"no (construction A {ok[0]}, B {ok[1]})"


def self_check() -> None:
    """A Doubtful starter who sits is swapped for the bench player of a later game under B,
    not under A; C keeps A's choice when the only bench player's game has started."""
    sunday = datetime(2026, 9, 13, 13, 0)
    star = Slot("q", "WR", 20.0, 0.3, True, False, 0.0, sunday)
    bench_late = Slot("b", "WR", 8.0, 1.0, False, True, 9.0, sunday + timedelta(hours=3))
    bench_early = Slot("b", "WR", 8.0, 1.0, False, True, 9.0, sunday - timedelta(days=3))
    slots = ["WR"]
    assert play_week([star, bench_late], "A", slots)[0] == 9.0  # 0.3 * 20 < 8: bench starts
    assert play_week([star, bench_late], "B", slots)[0] == 9.0  # starts q, swapped at inactives
    assert play_week([star, bench_early], "B", slots)[0] == 0.0  # no swap possible: 0
    assert play_week([star, bench_early], "C", slots)[0] == 9.0  # no option: p * E
    active = Slot("q", "WR", 20.0, 0.3, True, True, 25.0, sunday)
    assert play_week([active, bench_late], "B", slots)[0] == 25.0
    assert play_week([active, bench_late], "A", slots)[0] == 9.0
    assert play_week([active, bench_late], "A+s", slots)[0] == 25.0  # known active at release
    assert play_week([active, bench_late], "A+plan", slots)[0] == 9.0  # the plan only swaps out
    likely = Slot("q", "WR", 20.0, 0.5, True, False, 0.0, sunday)  # 0.5 * 20 > 8: q starts
    assert play_week([likely, bench_late], "A+plan", slots)[0] == 9.0
    assert play_week([likely, bench_early], "A+plan", slots)[0] == 0.0
    # two flagged starters, one bench option: only the earlier game is covered
    late = Slot("q2", "WR", 20.0, 0.5, True, False, 0.0, sunday + timedelta(hours=3))
    last = Slot("b", "WR", 8.0, 1.0, False, True, 9.0, sunday + timedelta(hours=7))
    assert play_week([likely, late, last], "A+plan", ["WR", "WR"])[0] == 9.0


def main() -> None:
    self_check()
    pop, counts = population()
    for k, v in counts.items():
        print(f"{k}: {v}")
    uni = pop.select(*r.KEY, "position", "learned", "points")
    rosters = pl.concat(
        [*(r.built_rosters(c, uni) for c in r.CONSTRUCTIONS), r.real_rosters()],
        how="vertical_relaxed",
    )
    scored = score(rosters, pop)
    table = summary(scored).sort("cons", "league", "policy")
    print("\nd_pts and t: policy minus A, actual lineup points per team-week (paired by week)")
    print("changed: team-weeks whose final lineup differs from A's; d_changed: mean gain there")
    print(table)
    for policy in ("A+plan", "A+s", "B", "C"):
        print(f"verdict {policy}: {verdict(table, policy)}")
    for cand, ref in (("C", "A+s"), ("A+plan", "A+s"), ("C", "A+plan")):
        print(f"\n{cand} minus {ref}")
        print(versus(scored, cand, ref))


if __name__ == "__main__":
    pl.Config(tbl_rows=60, tbl_cols=30, tbl_width_chars=250)
    main()
