"""Recompute standings from matchup scores and compare with Sleeper's record and points for.

Run: uv run python -m fantasy.stages.validate_standings
"""

import polars as pl

from fantasy import store
from fantasy.sim.schedule import standings

POINTS_TOLERANCE = 0.011


def flagged(computed: pl.DataFrame, sleeper: pl.DataFrame) -> pl.DataFrame:
    """Every team from either side with `record_off`, `points_off` (a team missing on one side is
    off on both) and `points_gap`."""
    gap = (pl.col("points_for") - pl.col("points_for_sleeper")).abs()
    record_off = (
        (pl.col("wins") != pl.col("wins_sleeper"))
        | (pl.col("losses") != pl.col("losses_sleeper"))
        | (pl.col("ties") != pl.col("ties_sleeper"))
    )
    return computed.join(
        sleeper, on=["league_id", "roster_id"], how="full", suffix="_sleeper", coalesce=True
    ).with_columns(
        record_off.fill_null(True).alias("record_off"),
        (gap > POINTS_TOLERANCE).fill_null(True).alias("points_off"),
        gap.alias("points_gap"),
    )


def compare(computed: pl.DataFrame, sleeper: pl.DataFrame) -> pl.DataFrame:
    return flagged(computed, sleeper).filter(pl.col("record_off") | pl.col("points_off"))


def run() -> None:
    leagues = store.read_table("leagues", "raw")
    matchups = store.read_table("matchups", "raw")
    teams = store.read_table("league_teams", "raw").select(
        "league_id", "roster_id", "wins", "losses", "ties", "points_for"
    )
    for row in leagues.iter_rows(named=True):
        through = int(row["current_week"]) - 1
        league_matchups = matchups.filter(pl.col("league_id") == row["league_id"])
        computed = standings(league_matchups, through)
        sleeper = teams.filter(pl.col("league_id") == row["league_id"])
        flags = flagged(computed, sleeper)
        records_off = int(flags["record_off"].sum())
        points_off = int(flags["points_off"].sum())
        gap = flags.select(pl.col("points_gap").max()).item()
        total = sleeper.height
        print(
            f"{row['league_key']} through week {through}: records match {total - records_off} of "
            f"{total}; points for exact {total - points_off} of {total}, largest gap {gap:.2f}"
        )


if __name__ == "__main__":
    run()
