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


ALL_PLAY_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "league_id": pl.String,
    "roster_id": pl.Int64,
    "weeks": pl.Int64,
    "wins": pl.Int64,
    "losses": pl.Int64,
    "ties": pl.Int64,
    "ap_wins": pl.Int64,
    "ap_losses": pl.Int64,
    "ap_ties": pl.Int64,
}


def completed(matchups: pl.DataFrame, through_week: int) -> pl.DataFrame:
    """Matchup rows of weeks 1 through `through_week` that count: with a matchup id and points,
    and not a week where every score is 0 (a failed sync)."""
    played = matchups.filter(
        (pl.col("week") <= through_week)
        & pl.col("matchup_id").is_not_null()
        & pl.col("points").is_not_null()
    )
    live = played.group_by("league_id", "week").agg(pl.col("points").abs().sum().alias("total"))
    return played.join(live.filter(pl.col("total") > 0), on=["league_id", "week"]).drop("total")


def all_play(matchups: pl.DataFrame, through_week: int) -> pl.DataFrame:
    """Actual record and all-play record (each team against every other team's score, each week)
    over the `completed` weeks."""
    played = completed(matchups, through_week)
    pairs = played.join(played, on=["league_id", "week"], suffix="_opp").filter(
        pl.col("roster_id") != pl.col("roster_id_opp")
    )
    won = pl.col("points") > pl.col("points_opp")
    lost = pl.col("points") < pl.col("points_opp")
    tied = pl.col("points") == pl.col("points_opp")
    actual = pl.col("matchup_id") == pl.col("matchup_id_opp")

    def count(e: pl.Expr) -> pl.Expr:
        return e.sum().cast(pl.Int64)

    out = pairs.group_by("league_id", "roster_id").agg(
        pl.col("week").n_unique().cast(pl.Int64).alias("weeks"),
        count(won & actual).alias("wins"),
        count(lost & actual).alias("losses"),
        count(tied & actual).alias("ties"),
        count(won).alias("ap_wins"),
        count(lost).alias("ap_losses"),
        count(tied).alias("ap_ties"),
    )
    return out.select(*ALL_PLAY_SCHEMA).sort("league_id", "roster_id")
