"""Recompute standings from matchup scores and compare with Sleeper's record and points for.

Run: uv run python -m fantasy.stages.validate_standings
"""

import polars as pl

from fantasy import store
from fantasy.sim.schedule import standings

POINTS_TOLERANCE = 0.011


def compare(computed: pl.DataFrame, sleeper: pl.DataFrame) -> pl.DataFrame:
    joined = computed.join(
        sleeper, on=["league_id", "roster_id"], how="full", suffix="_sleeper", coalesce=True
    )
    off = (
        (pl.col("wins") != pl.col("wins_sleeper"))
        | (pl.col("losses") != pl.col("losses_sleeper"))
        | (pl.col("ties") != pl.col("ties_sleeper"))
        | ((pl.col("points_for") - pl.col("points_for_sleeper")).abs() > POINTS_TOLERANCE)
    )
    return joined.filter(off.fill_null(True))


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
        bad = compare(computed, sleeper)
        joined = computed.join(sleeper, on=["league_id", "roster_id"], suffix="_sleeper")
        records_off = joined.filter(
            (pl.col("wins") != pl.col("wins_sleeper"))
            | (pl.col("losses") != pl.col("losses_sleeper"))
            | (pl.col("ties") != pl.col("ties_sleeper"))
        ).height
        gap = (joined["points_for"] - joined["points_for_sleeper"]).abs().max()
        total = sleeper.height
        print(
            f"{row['league_key']} through week {through}: records match {total - records_off} of "
            f"{total}; points for exact {total - bad.height} of {total}, largest gap {gap:.2f}"
        )


if __name__ == "__main__":
    run()
