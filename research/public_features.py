"""Permitted stand-ins for the features a public build may not use (research only, 2026-11-05).

Built from nflverse play-by-play (CC BY 4.0) and player stats only:
  involvement  per player-game: (dropbacks + designed carries + targets) / team plays, the
               stand-in for Pro-Football-Reference snap share (`nfl_snaps.offense_pct`)
  advanced     per player-game: average depth of target, air-yards share, expected YAC and YAC
               over expected on catches, EPA per target, per carry and per dropback, rush success
               rate, CPOE and air yards per attempt; the stand-in for PFR advanced stats and Next
               Gen Stats (`nfl_advanced`). The learned model lags them like `nfl_advanced`.
  role_rank    per team game: each player's rank at his position by weighted involvement
               (half-life 4 games) among the players who played for the team in its last
               ROLE_WINDOW games, all strictly before the game; the stand-in for the depth chart
               (ESPN-scraped from 2025, so unusable for the current season).
Pass rate over expected is already a permitted feature (`nfl_team_pace.pass_oe`, from pbp).
`tests/test_public_features.py` checks that nothing from the target game reaches role_rank.
"""

import polars as pl

from fantasy.stages.lags import EXTRA_HALF_LIFE
from fantasy.store import DATA_DIR, week_index

KEY = ["gsis_id", "season", "week"]
ROLE_WINDOW = 3  # team games looked back for the candidates of a role rank
POSITION_MAP = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE"}
PBP_COLUMNS = [
    "season", "week", "season_type", "posteam", "pass", "rush", "qb_dropback", "pass_attempt",
    "sack", "complete_pass", "passer_id", "rusher_id", "receiver_id", "air_yards",
    "yards_after_catch", "xyac_mean_yardage", "epa", "success", "cpoe",
]  # fmt: skip
ADV_COLUMNS = [
    "pbp_adot", "pbp_air_share", "pbp_xyac", "pbp_yacoe", "pbp_rec_epa",
    "pbp_rush_epa", "pbp_rush_succ", "pbp_cpoe", "pbp_pass_ay", "pbp_pass_epa",
]  # fmt: skip


def read_plays(seasons: list[int]) -> pl.DataFrame:
    """Regular-season offensive plays (pass or rush with a posteam) from the shared pbp cache."""
    parts = []
    for season in seasons:
        path = DATA_DIR / "raw" / "pbp" / f"{season}.parquet"
        if path.exists():
            parts.append(pl.read_parquet(path, columns=PBP_COLUMNS))
    plays = pl.concat(parts, how="vertical_relaxed").filter(
        (pl.col("season_type") == "REG")
        & ((pl.col("pass") == 1) | (pl.col("rush") == 1))
        & pl.col("posteam").is_not_null()
    )
    return plays.with_columns(pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64))


def player_games(plays: pl.DataFrame) -> pl.DataFrame:
    """KEY, team, inv (involvement share) and ADV_COLUMNS per player-game."""
    team = ["season", "week", "posteam"]
    totals = plays.group_by(team).agg(
        pl.len().alias("_plays"),
        pl.col("air_yards").filter(pl.col("pass_attempt") == 1).sum().alias("_team_air"),
    )
    is_target = (pl.col("pass_attempt") == 1) & (pl.col("sack") != 1) & pl.col("receiver_id").is_not_null()
    is_catch = is_target & (pl.col("complete_pass") == 1)
    rec = (
        plays.filter(is_target)
        .group_by(*team, pl.col("receiver_id").alias("gsis_id"))
        .agg(
            pl.len().alias("_tgt"),
            pl.col("air_yards").mean().alias("pbp_adot"),
            pl.col("air_yards").sum().alias("_air"),
            pl.col("xyac_mean_yardage").filter(is_catch).mean().alias("pbp_xyac"),
            (pl.col("yards_after_catch") - pl.col("xyac_mean_yardage"))
            .filter(is_catch)
            .mean()
            .alias("pbp_yacoe"),
            pl.col("epa").mean().alias("pbp_rec_epa"),
        )
    )
    is_carry = (pl.col("rush") == 1) & pl.col("rusher_id").is_not_null()
    rush = (
        plays.filter(is_carry)
        .group_by(*team, pl.col("rusher_id").alias("gsis_id"))
        .agg(
            pl.len().alias("_car"),
            pl.col("epa").mean().alias("pbp_rush_epa"),
            pl.col("success").mean().alias("pbp_rush_succ"),
        )
    )
    dropback = (pl.col("qb_dropback") == 1) & pl.col("passer_id").is_not_null()
    passes = (
        plays.filter(dropback)
        .group_by(*team, pl.col("passer_id").alias("gsis_id"))
        .agg(
            pl.len().alias("_db"),
            pl.col("cpoe").mean().alias("pbp_cpoe"),
            pl.col("air_yards").filter(pl.col("pass_attempt") == 1).mean().alias("pbp_pass_ay"),
            pl.col("epa").mean().alias("pbp_pass_epa"),
        )
    )
    keys = [*team, "gsis_id"]
    joined = rec.join(rush, on=keys, how="full", coalesce=True).join(
        passes, on=keys, how="full", coalesce=True
    )
    return (
        joined.join(totals, on=team, how="left")
        .with_columns(
            (
                pl.sum_horizontal(pl.col("_tgt", "_car", "_db").fill_null(0)) / pl.col("_plays")
            ).alias("inv"),
            (pl.col("_air") / pl.col("_team_air")).alias("pbp_air_share"),
        )
        .rename({"posteam": "team"})
        .select(*KEY, "team", "inv", *ADV_COLUMNS)
        .unique(KEY, keep="first", maintain_order=True)
    )


def with_positions(games: pl.DataFrame, stats: pl.DataFrame) -> pl.DataFrame:
    """Skill player-games only, with position from nflverse player stats (FB counts as RB)."""
    positions = (
        stats.filter(pl.col("position").is_in(list(POSITION_MAP)))
        .select(
            pl.col("player_id").alias("gsis_id"),
            pl.col("position").replace_strict(POSITION_MAP).alias("position"),
        )
        .unique("gsis_id", keep="last", maintain_order=True)
    )
    return games.join(positions, on="gsis_id", how="inner")


def role_rank(usage: pl.DataFrame, schedule: pl.DataFrame) -> pl.DataFrame:
    """KEY, depth_rank for every candidate of every scheduled team game.

    usage: KEY, team, position, inv per player-game. schedule: team, season, week (every team
    game, played or not). A candidate played for the team in one of its last ROLE_WINDOW games
    before the target game and has not played for another team since; his rank at his position is
    by his weighted involvement through his last game before the target game (1 = most)."""
    sched = (
        schedule.select("team", "season", "week")
        .unique()
        .sort("team", "season", "week")
        .with_columns(pl.int_range(pl.len()).over("team").alias("g"), week_index().alias("t"))
    )
    state = (
        usage.sort("gsis_id", "season", "week")
        .with_columns(
            pl.col("inv").forward_fill().ewm_mean(half_life=EXTRA_HALF_LIFE).over("gsis_id").alias("inv_ewm"),
            week_index().alias("t"),
        )
        .with_columns(pl.col("t").shift(-1).over("gsis_id").alias("next_t"))
        .join(sched.select("team", "season", "week", "g"), on=["team", "season", "week"], how="inner")
        .select("gsis_id", "team", "position", "g", "next_t", "inv_ewm")
    )
    target = sched.select("team", "season", "week", pl.col("g").alias("g_target"), pl.col("t").alias("t_target"))
    cand = (
        target.join(state, on="team", how="inner")
        .filter((pl.col("g") < pl.col("g_target")) & (pl.col("g") >= pl.col("g_target") - ROLE_WINDOW))
        .sort("g")
        .unique(["team", "season", "week", "gsis_id"], keep="last")
        # his next game after the latest one with this team came before the target: he moved on
        .filter(pl.col("next_t").is_null() | (pl.col("next_t") >= pl.col("t_target")))
    )
    return cand.with_columns(
        pl.col("inv_ewm")
        .rank(method="ordinal", descending=True)
        .over("team", "season", "week", "position")
        .cast(pl.Float64)
        .alias("depth_rank")
    ).select(*KEY, "team", "depth_rank")


def build(seasons: list[int], stats: pl.DataFrame, schedule: pl.DataFrame) -> dict[str, pl.DataFrame]:
    """involvement (KEY, team, position, inv), advanced (KEY, ADV_COLUMNS) and role (KEY,
    depth_rank) tables."""
    games = with_positions(player_games(read_plays(seasons)), stats)
    return {
        "involvement": games.select(*KEY, "team", "position", "inv"),
        "advanced": games.select(*KEY, *ADV_COLUMNS),
        # pbp writes the Raiders as LV in every season; the schedule keeps OAK to 2019
        "role": role_rank(
            games.select(*KEY, "team", "position", "inv"),
            schedule.with_columns(pl.col("team").replace("OAK", "LV")),
        ).drop("team"),
    }
