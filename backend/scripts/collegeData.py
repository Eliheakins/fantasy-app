"""
College football PBP → NFL-shaped Parquet shards for DuckDB-WASM parity.

Loads sportsdataverse release Parquet (not cfbfastR-py URLs), filters to pass/rush
plays, renames columns to match `nfl_pipeline.PBP_COLS`, and adds null participation
/ zeroed NGS columns so schemas align with `nfl_pbp_*.parquet`.
"""

from __future__ import annotations

import polars as pl

from nfl_pipeline import (
    EXPECTED_RUN_YARDS_ALIAS,
    NGS_PASS,
    NGS_REC,
    NGS_RUSH,
    PART_COLS,
    PBP_COLS,
)

CFB_PBP_PARQUET = (
    "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
    "cfbfastR_cfb_pbp/play_by_play_{season}.parquet"
)

# Prune at read time — every column referenced in `_stitch_cfb` must appear here.
CFB_READ_COLS = [
    "game_id",
    "play_number",
    "season",
    "year",
    "week",
    "season_type",
    "pos_team",
    "def_pos_team",
    "home",
    "away",
    "down",
    "distance",
    "yards_to_goal",
    "period",
    "TimeSecsRem",
    "score_diff",
    "Goal_To_Go",
    "pass",
    "rush",
    "yards_gained",
    "completion",
    "pass_attempt",
    "int",
    "sack",
    "touchdown",
    "pass_td",
    "rush_td",
    "EPA",
    "success",
    "wpa",
    "completion_player_id",
    "completion_player",
    "rush_player_id",
    "rush_player",
    "reception_player_id",
    "reception_player",
    "receiver_player_name",
    "firstD_by_kickoff",
    "firstD_by_poss",
    "firstD_by_penalty",
    "firstD_by_yards",
]


def _cfb_url(season: int) -> str:
    return CFB_PBP_PARQUET.format(season=season)


def _float_id_to_utf8(col: str, alias: str) -> pl.Expr:
    return (
        pl.when(pl.col(col).is_not_null())
        .then(pl.col(col).cast(pl.Int64).cast(pl.Utf8))
        .otherwise(None)
        .alias(alias)
    )


def _season_type_nfl() -> pl.Expr:
    st = pl.col("season_type")
    return (
        pl.when(st.is_null())
        .then(pl.lit("REG"))
        .when(st.str.to_lowercase() == "regular")
        .then(pl.lit("REG"))
        .when(st.str.to_lowercase() == "postseason")
        .then(pl.lit("POST"))
        .otherwise(st.str.to_uppercase())
        .alias("season_type")
    )


def _stitch_cfb(raw: pl.DataFrame) -> pl.DataFrame:
    p = pl.col("pass").fill_null(0)
    r = pl.col("rush").fill_null(0)
    scrimmage = raw.filter((p > 0) | (r > 0))

    play_type = (
        pl.when(p > 0)
        .then(pl.lit("pass"))
        .when(r > 0)
        .then(pl.lit("run"))
        .otherwise(pl.lit("pass"))
        .alias("play_type")
    )

    first_down = (
        (pl.col("firstD_by_kickoff").fill_null(0) > 0)
        | (pl.col("firstD_by_poss").fill_null(0) > 0)
        | (pl.col("firstD_by_penalty").fill_null(0) > 0)
        | (pl.col("firstD_by_yards").fill_null(0) > 0)
    ).cast(pl.Int8)

    posteam_type = (
        pl.when(pl.col("pos_team") == pl.col("home"))
        .then(pl.lit("home"))
        .when(pl.col("pos_team") == pl.col("away"))
        .then(pl.lit("away"))
        .otherwise(None)
        .alias("posteam_type")
    )

    season_col = pl.col("season") if "season" in scrimmage.columns else pl.col("year")

    complete = pl.col("completion").fill_null(0)
    att = pl.col("pass_attempt").fill_null(0)

    out = scrimmage.select(
        [
            (pl.col("game_id").cast(pl.Int64) * 1_000_000 + pl.col("play_number").cast(pl.Int64)).alias(
                "play_id"
            ),
            pl.col("game_id").cast(pl.Utf8).alias("old_game_id"),
            pl.col("game_id").cast(pl.Utf8).alias("game_id"),
            season_col.cast(pl.Int32).alias("season"),
            pl.col("week").cast(pl.Int32),
            _season_type_nfl(),
            pl.col("pos_team").alias("posteam"),
            pl.col("def_pos_team").alias("defteam"),
            posteam_type,
            pl.col("down").alias("down"),
            pl.col("distance").alias("ydstogo"),
            pl.col("yards_to_goal").alias("yardline_100"),
            pl.col("period").alias("qtr"),
            pl.col("TimeSecsRem").alias("game_seconds_remaining"),
            pl.col("score_diff").alias("score_differential"),
            pl.col("Goal_To_Go").fill_null(False).alias("goal_to_go"),
            play_type,
            first_down.alias("first_down"),
            pl.col("yards_gained").alias("yards_gained"),
            pl.lit(None).cast(pl.Float64).alias("air_yards"),
            pl.lit(None).cast(pl.Float64).alias("yards_after_catch"),
            complete.cast(pl.Int32).alias("complete_pass"),
            (att - complete).clip(lower_bound=0).cast(pl.Int32).alias("incomplete_pass"),
            pl.col("int").fill_null(0).alias("interception"),
            pl.lit(None).cast(pl.Float64).alias("fumble_lost"),
            pl.col("sack").fill_null(0).alias("sack"),
            pl.lit(None).cast(pl.Float64).alias("qb_hit"),
            pl.col("touchdown").fill_null(0).alias("touchdown"),
            pl.col("pass_td").fill_null(0).alias("pass_touchdown"),
            pl.col("rush_td").fill_null(0).alias("rush_touchdown"),
            pl.col("EPA").alias("epa"),
            pl.lit(None).cast(pl.Float64).alias("qb_epa"),
            pl.col("success").alias("success"),
            pl.lit(None).cast(pl.Float64).alias("cpoe"),
            pl.lit(None).cast(pl.Float64).alias("xpass"),
            pl.lit(None).cast(pl.Float64).alias("xyac_epa"),
            _float_id_to_utf8("completion_player_id", "passer_player_id"),
            pl.col("completion_player").alias("passer_player_name"),
            _float_id_to_utf8("rush_player_id", "rusher_player_id"),
            pl.col("rush_player").alias("rusher_player_name"),
            _float_id_to_utf8("reception_player_id", "receiver_player_id"),
            pl.coalesce(
                [pl.col("reception_player"), pl.col("receiver_player_name")]
            ).alias("receiver_player_name"),
            pl.col("wpa").alias("wpa"),
            pl.lit(None).cast(pl.Float64).alias("vegas_wpa"),
            pl.lit(None).cast(pl.Float64).alias("temp"),
            pl.lit(None).cast(pl.Float64).alias("wind"),
        ]
    )

    out = out.with_columns(
        [
            pl.lit("").alias("offense_personnel"),
            pl.lit(0).cast(pl.Int32).alias("defenders_in_box"),
            pl.lit(0).cast(pl.Int32).alias("number_of_pass_rushers"),
        ]
    )

    for c in NGS_PASS + NGS_REC:
        out = out.with_columns(pl.lit(0.0).alias(c))

    rush_stats = [s for s in NGS_RUSH if s != "expected_rush_yards"]
    for c in rush_stats:
        out = out.with_columns(pl.lit(0.0).alias(c))
    out = out.with_columns(pl.lit(0.0).alias(EXPECTED_RUN_YARDS_ALIAS))

    out = out.with_columns((pl.col("yardline_100") <= 20).alias("is_red_zone"))

    ordered = [
        *PBP_COLS,
        *PART_COLS,
        *NGS_PASS,
        *NGS_REC,
        "avg_time_to_los",
        EXPECTED_RUN_YARDS_ALIAS,
        "efficiency",
        "is_red_zone",
    ]
    return out.select(ordered)


def build_cfb_stitched_for_year(year: int) -> pl.DataFrame:
    """Download one CFB season from sportsdataverse and return an NFL-shaped frame."""
    url = _cfb_url(year)
    print(f"CFB PBP {year} (sportsdataverse Parquet)…")
    schema = pl.scan_parquet(url).collect_schema()
    names = set(schema.names())
    cols = [c for c in CFB_READ_COLS if c in names]
    missing = [c for c in CFB_READ_COLS if c not in names]
    if missing:
        print(f"⚠️  CFB Parquet missing columns (omitted): {missing}")
    need = {"game_id", "play_number", "pass", "rush"}
    if not need.issubset(names):
        raise ValueError(f"CFB PBP for {year} missing required columns (have keys: {sorted(names)[:20]}…)")
    raw = pl.read_parquet(url, columns=cols)
    return _stitch_cfb(raw)


if __name__ == "__main__":
    sample = build_cfb_stitched_for_year(2024)
    print(sample.schema)
    print(sample.head(3))
