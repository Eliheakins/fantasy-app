"""The opponent-lineup test (`opponent_lineup_check.py`) on YinzBurgh's three ESPN seasons.

Same question and rule: managers set lineups worse than their best by projection; does subtracting
that shortfall predict the score of the skill players they started better than assuming the best
lineup? Rule fixed before the run (as on the 2026 data): a variant ships if its RMSE is lower and
the paired t of squared errors against `best` is -2 or lower. Weeks 4 to 14 of 2023 to 2025
(330 team-weeks), each predicted from the earlier weeks of the same season only. Points are ESPN's
(0.5 PPR, the league's own scoring); the projection is the learned model's pre-game number.
Also: does a manager's shortfall carry from one season to the next (same primary owner)?

    uv run python research/espn_parse.py && uv run python research/espn_lineup_check.py
"""

import numpy as np
import polars as pl

from fantasy import store
from fantasy.sim.lineup import Player, auto_lineup, lineup_slots

SCRATCH = store.ROOT / "research" / "scratch" / "espn"
FIRST_SCORED_WEEK = 4
SHRINK_WEEKS = 3.0
SKILL = ["QB", "RB", "WR", "TE"]
STARTING_SLOTS = (0, 2, 4, 6, 23)  # QB, RB, WR, TE, FLEX


def team_weeks() -> pl.DataFrame:
    leagues = store.read_table("leagues", "raw")
    mine = leagues.filter(pl.col("league_key") == "yinzburgh").row(0, named=True)
    slots = lineup_slots(mine["roster_positions"])
    proj = (
        store.projection_table()
        .filter((pl.col("league_id") == mine["league_id"]) & ~pl.col("is_future"))
        .select("gsis_id", "season", "week", "projection")
    )
    lineups = (
        pl.read_parquet(SCRATCH / "lineups.parquet")
        .filter(pl.col("position").is_in(SKILL) & (pl.col("slot") != 21))
        .join(proj, on=["gsis_id", "season", "week"])
    )
    rows = []
    for (season, week, team), g in lineups.group_by("season", "week", "team_id"):
        pool = [Player(r["gsis_id"], r["position"], r["projection"]) for r in g.iter_rows(named=True)]
        chosen = g.filter(pl.col("slot").is_in(STARTING_SLOTS))
        rows.append(
            {
                "season": season, "week": week, "team_id": team,
                "best": auto_lineup(pool, slots).total,
                "set_proj": float(chosen["projection"].sum()),
                "actual": float(chosen["points"].sum()),
            }
        )  # fmt: skip
    return pl.DataFrame(rows).with_columns((pl.col("best") - pl.col("set_proj")).alias("short"))


def predictions(table: pl.DataFrame) -> pl.DataFrame:
    out = []
    for row in table.filter(pl.col("week") >= FIRST_SCORED_WEEK).iter_rows(named=True):
        earlier = table.filter((pl.col("season") == row["season"]) & (pl.col("week") < row["week"]))
        league_short = float(earlier["short"].mean())  # type: ignore[arg-type]
        mine = earlier.filter(pl.col("team_id") == row["team_id"])["short"]
        team_short = (float(mine.sum()) + SHRINK_WEEKS * league_short) / (mine.len() + SHRINK_WEEKS)
        out.append(
            {**row, "p_best": row["best"], "p_league": row["best"] - league_short,
             "p_team": row["best"] - team_short}
        )  # fmt: skip
    return pl.DataFrame(out)


def report(pred: pl.DataFrame) -> None:
    groups = [(f"{k[0]}", g) for k, g in pred.group_by("season", maintain_order=True)]
    for label, g in [*groups, ("all", pred)]:
        base = (g["actual"] - g["p_best"]).to_numpy() ** 2
        line = [f"{label:>5} n={g.height:3d} shortfall {g['short'].mean():5.2f} "
                f"best rmse {np.sqrt(base.mean()):6.2f}"]  # fmt: skip
        for name in ("league", "team"):
            sq = (g["actual"] - g[f"p_{name}"]).to_numpy() ** 2
            diff = sq - base
            t = diff.mean() / (diff.std(ddof=1) / np.sqrt(diff.size))
            line.append(f"{name} rmse {np.sqrt(sq.mean()):6.2f} (t {t:5.2f})")
        print("  ".join(line))


def across_seasons(table: pl.DataFrame) -> None:
    teams = pl.read_parquet(SCRATCH / "teams.parquet")
    per = (
        table.group_by("season", "team_id").agg(pl.col("short").mean())
        .join(teams, on=["season", "team_id"]).select("owner", "season", "short")
    )  # fmt: skip
    pairs = []
    for a, b in ((2023, 2024), (2024, 2025)):
        x = per.filter(pl.col("season") == a).join(per.filter(pl.col("season") == b), on="owner")
        pairs += list(zip(x["short"], x["short_right"], strict=True))
    first, second = zip(*pairs, strict=True)
    print(f"same owner, next season: n={len(pairs)}, correlation of mean shortfall "
          f"{np.corrcoef(first, second)[0, 1]:.2f}")  # fmt: skip


if __name__ == "__main__":
    weeks = team_weeks()
    print(f"{weeks.height} team-weeks; shortfall median {weeks['short'].median():.2f}, "
          f"90th percentile {weeks['short'].quantile(0.9):.2f}")  # fmt: skip
    report(predictions(weeks))
    across_seasons(weeks)
