"""Weekly pairings, standings and playoff seeding for a Sleeper league.

Standings are recomputed from matchup scores, so they can be checked against Sleeper's own.
Seeding is wins, then points for, then roster id (Sleeper's default; the real tiebreak setting
has no field to read, see decisions.md). The 6-team bracket is assumed to give seeds 1 and 2 a
bye in week 1 of the playoffs and not to re-seed; both are unverified assumptions.
"""

import polars as pl

PAIR_KEYS = ["league_id", "week", "matchup_id"]


def pairings(matchups: pl.DataFrame) -> pl.DataFrame:
    """One row per matchup: league_id, week, roster_a, roster_b (a < b)."""
    return (
        matchups.filter(pl.col("matchup_id").is_not_null())
        .group_by(PAIR_KEYS)
        .agg(pl.col("roster_id").sort().alias("rosters"))
        .filter(pl.col("rosters").list.len() == 2)
        .select(
            "league_id",
            "week",
            pl.col("rosters").list.get(0).alias("roster_a"),
            pl.col("rosters").list.get(1).alias("roster_b"),
        )
        .sort("league_id", "week", "roster_a")
    )


def standings(matchups: pl.DataFrame, through_week: int) -> pl.DataFrame:
    """Record and points for from completed weeks (1 through `through_week`)."""
    played = matchups.filter((pl.col("week") <= through_week) & pl.col("matchup_id").is_not_null())
    games = played.join(played, on=PAIR_KEYS, suffix="_opp").filter(
        pl.col("roster_id") != pl.col("roster_id_opp")
    )
    return (
        games.group_by("league_id", "roster_id")
        .agg(
            (pl.col("points") > pl.col("points_opp")).sum().cast(pl.Int64).alias("wins"),
            (pl.col("points") < pl.col("points_opp")).sum().cast(pl.Int64).alias("losses"),
            (pl.col("points") == pl.col("points_opp")).sum().cast(pl.Int64).alias("ties"),
            pl.col("points").sum().alias("points_for"),
        )
        .sort("league_id", "roster_id")
    )
