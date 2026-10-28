"""Do managers set lineups worse than their best by projection, and does knowing it help?

Win probability and the season odds give every team its best lineup by projection. A manager who
leaves a bye or an injured player in scores less than that. For each played week of the current
season and each team, the skill players it set are compared with the best lineup its whole roster
could have made, both valued at the pre-game projections (`store.projection_table`).

Held out: each week from the 4th is predicted three ways, using only earlier weeks, and scored
against the points of the skill players the team really started.
  best       the best lineup's projection (what the simulator assumes)
  league     best minus the league's mean shortfall so far
  team       best minus the team's own mean shortfall so far, shrunk toward the league's
Rule, fixed before the run: a variant ships if its RMSE is lower in both leagues and the paired
t-statistic of squared errors against `best` is -2 or lower, pooled over the two leagues.

    uv run python research/opponent_lineup_check.py
"""

import numpy as np
import polars as pl

from fantasy import store
from fantasy.config import load_config
from fantasy.sim.lineup import Player, auto_lineup, lineup_slots
from fantasy.store import SKILL

FIRST_SCORED_WEEK = 4
SHRINK_WEEKS = 3.0  # pseudo-weeks of the league mean in a team's own shortfall


def team_weeks() -> pl.DataFrame:
    """One row per league, week and team: best and set lineup projections and the set points."""
    cfg = load_config()
    leagues = store.read_table("leagues", "raw")
    played = store.read_table("matchup_players", "raw")
    id_map = store.read_table("id_map").select("sleeper_id", "gsis_id")
    proj = (
        store.projection_table()
        .filter((pl.col("season") == cfg.season) & ~pl.col("is_future"))
        .select("league_id", "gsis_id", "position", "week", "projection")
    )
    rows = []
    for league in leagues.iter_rows(named=True):
        slots = lineup_slots(league["roster_positions"])
        frame = (
            played.filter(pl.col("league_id") == league["league_id"])
            .join(id_map, on="sleeper_id")
            .join(
                proj.filter(pl.col("league_id") == league["league_id"]).drop("league_id"),
                on=["gsis_id", "week"],
            )
            .filter(pl.col("position").is_in(SKILL))
        )
        for (week, roster), g in frame.group_by("week", "roster_id"):
            pool = [
                Player(r["gsis_id"], r["position"], r["projection"])
                for r in g.iter_rows(named=True)
            ]
            chosen = g.filter(pl.col("is_starter"))
            rows.append(
                {
                    "league": league["league_key"],
                    "week": int(week),
                    "roster_id": int(roster),
                    "best": auto_lineup(pool, slots).total,
                    "set_proj": float(chosen["projection"].sum()),
                    "actual": float(chosen["points"].sum()),
                }
            )
    return pl.DataFrame(rows).with_columns((pl.col("best") - pl.col("set_proj")).alias("short"))


def predictions(table: pl.DataFrame) -> pl.DataFrame:
    """Each variant's prediction for the weeks from FIRST_SCORED_WEEK, from earlier weeks only."""
    out = []
    for row in table.filter(pl.col("week") >= FIRST_SCORED_WEEK).iter_rows(named=True):
        earlier = table.filter((pl.col("league") == row["league"]) & (pl.col("week") < row["week"]))
        league_short = float(earlier["short"].mean())  # type: ignore[arg-type]
        mine = earlier.filter(pl.col("roster_id") == row["roster_id"])["short"]
        team_short = (float(mine.sum()) + SHRINK_WEEKS * league_short) / (mine.len() + SHRINK_WEEKS)
        out.append(
            {
                **row,
                "p_best": row["best"],
                "p_league": row["best"] - league_short,
                "p_team": row["best"] - team_short,
            }
        )
    return pl.DataFrame(out)


def report(pred: pl.DataFrame) -> None:
    groups = [(k[0], g) for k, g in pred.group_by("league")] + [("both", pred)]
    for label, g in groups:
        base = (g["actual"] - g["p_best"]).to_numpy() ** 2
        line = [f"{label:>10}  n={g.height:3d}  mean shortfall {g['short'].mean():5.2f}"]
        line.append(f"best rmse {np.sqrt(base.mean()):6.2f}")
        for name in ("league", "team"):
            sq = (g["actual"] - g[f"p_{name}"]).to_numpy() ** 2
            diff = sq - base
            t = diff.mean() / (diff.std(ddof=1) / np.sqrt(diff.size))
            line.append(f"{name} rmse {np.sqrt(sq.mean()):6.2f} (t {t:5.2f})")
        print("  ".join(line))


def persistence(table: pl.DataFrame) -> None:
    """Do the same managers fall short week after week? Correlation of odd and even weeks."""
    team = (
        table.with_columns((pl.col("week") % 2).alias("odd"))
        .group_by("league", "roster_id", "odd")
        .agg(pl.col("short").mean())
        .pivot(on="odd", index=["league", "roster_id"], values="short")
    )
    both = team.drop_nulls()
    print(f"split-half correlation of team shortfall: {np.corrcoef(both['0'], both['1'])[0, 1]:.2f}")


if __name__ == "__main__":
    weeks = team_weeks()
    print(
        f"{weeks.height} team-weeks; shortfall median {weeks['short'].median():.2f}, "
        f"90th percentile {weeks['short'].quantile(0.9):.2f}"
    )
    report(predictions(weeks))
    persistence(weeks)
