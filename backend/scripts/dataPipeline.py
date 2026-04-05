"""
Master data stitcher for The Bridge: PBP + participation + Next Gen Stats → lean Parquet shards.

Joins:
  A) Participation on (old_game_id, play_id)
  B) NGS passing / receiving / rushing on (season, week, season_type, player_gsis_id ↔ role id)
"""

from __future__ import annotations

from pathlib import Path

import nflreadpy as nfl
import polars as pl
from nflreadpy.utils_date import get_current_season

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
YEARS = [2021, 2022, 2023, 2024, 2025]

# --- PBP (lean) + join keys + advanced --------------------------------------
PBP_COLS = [
    "play_id",
    "old_game_id",
    "game_id",
    "season",
    "week",
    "season_type",
    "posteam",
    "defteam",
    "posteam_type",
    "down",
    "ydstogo",
    "yardline_100",
    "qtr",
    "game_seconds_remaining",
    "score_differential",
    "goal_to_go",
    "play_type",
    "first_down",
    "yards_gained",
    "air_yards",
    "yards_after_catch",
    "complete_pass",
    "incomplete_pass",
    "interception",
    "fumble_lost",
    "sack",
    "qb_hit",
    "touchdown",
    "pass_touchdown",
    "rush_touchdown",
    "epa",
    "qb_epa",
    "success",
    "cpoe",
    "xpass",
    "xyac_epa",
    "passer_player_id",
    "passer_player_name",
    "rusher_player_id",
    "rusher_player_name",
    "receiver_player_id",
    "receiver_player_name",
    "wpa",
    "vegas_wpa",
    "temp",
    "wind",
]

PART_COLS = ["offense_personnel", "defenders_in_box", "number_of_pass_rushers"]

NGS_KEYS = ["season", "week", "season_type", "player_gsis_id"]
NGS_PASS = ["avg_time_to_throw", "avg_intended_air_yards", "passer_rating"]
NGS_REC = ["avg_separation", "avg_cushion", "avg_expected_yac"]
NGS_RUSH = ["avg_time_to_los", "expected_rush_yards", "efficiency"]

# After join: expose NGS rushing expected yards under the prompt’s name
EXPECTED_RUN_YARDS_ALIAS = "expected_run_yards"


def create_player_index() -> None:
    """One row per player (latest season) in player_index.parquet."""
    print("Building player index…")
    rosters = nfl.load_rosters(YEARS)
    player_index = (
        rosters.select(
            [
                "gsis_id",
                "full_name",
                "position",
                "team",
                "headshot_url",
                "birth_date",
                "years_exp",
                "season",
            ]
        )
        .sort("season", descending=True)
        .unique(subset=["gsis_id"], keep="first")
        .drop("season")
    )
    player_index = player_index.with_columns(pl.col("gsis_id").cast(pl.Utf8))
    player_index.write_parquet(DATA_DIR / "player_index.parquet")
    print(f"✅ Player index: {DATA_DIR / 'player_index.parquet'}")


def _prepare_pbp_base(df: pl.DataFrame) -> pl.DataFrame:
    available = [c for c in PBP_COLS if c in df.columns]
    missing = [c for c in PBP_COLS if c not in df.columns]
    if missing:
        print(f"⚠️  PBP missing columns (omitted): {missing}")
    out = df.select(available).filter(pl.col("play_type").is_in(["pass", "run"]))
    out = out.with_columns(
        [
            pl.col("play_id").cast(pl.Int64),
            pl.col("season").cast(pl.Int32),
            pl.col("week").cast(pl.Int32),
        ]
    )
    if "old_game_id" in out.columns:
        out = out.with_columns(pl.col("old_game_id").cast(pl.Utf8))
    if "game_id" in out.columns:
        out = out.with_columns(pl.col("game_id").cast(pl.Utf8))
    if "season_type" in out.columns:
        out = out.with_columns(pl.col("season_type").cast(pl.Utf8))
    for role in ("passer_player_id", "rusher_player_id", "receiver_player_id"):
        if role in out.columns:
            out = out.with_columns(pl.col(role).cast(pl.Utf8))
    return out


def _join_participation(pbp: pl.DataFrame) -> pl.DataFrame:
    max_part_season = get_current_season(roster=True) - 1
    part_years = [y for y in YEARS if y <= max_part_season]
    if not part_years:
        print("Skipping participation (no seasons ≤ max release).")
        return pbp.with_columns([pl.lit(None).alias(c) for c in PART_COLS])

    need = ["old_game_id", "play_id", *PART_COLS]
    print(f"Loading participation {part_years}…")
    part = nfl.load_participation(part_years)
    have = [c for c in need if c in part.columns]
    miss = [c for c in need if c not in part.columns]
    if miss:
        raise ValueError(f"Participation missing columns: {miss}")

    part = part.select(have).with_columns(
        [
            pl.col("play_id").cast(pl.Int64),
            pl.col("old_game_id").cast(pl.Utf8),
        ]
    )
    if "old_game_id" not in pbp.columns:
        raise ValueError("PBP needs old_game_id to join participation.")

    return pbp.join(part, on=["old_game_id", "play_id"], how="left")


def _prepare_ngs_slice(df: pl.DataFrame, stat_names: list[str], label: str) -> pl.DataFrame:
    cols = [c for c in NGS_KEYS if c in df.columns]
    stats = [s for s in stat_names if s in df.columns]
    miss_k = [c for c in NGS_KEYS if c not in df.columns]
    miss_s = [s for s in stat_names if s not in df.columns]
    if miss_k:
        raise ValueError(f"NGS {label} missing keys: {miss_k}")
    if miss_s:
        print(f"⚠️  NGS {label} missing stats (filled later): {miss_s}")
    sub = df.select(cols + stats).unique()
    sub = sub.with_columns(
        [
            pl.col("player_gsis_id").cast(pl.Utf8),
            pl.col("season").cast(pl.Int32),
            pl.col("week").cast(pl.Int32),
            pl.col("season_type").cast(pl.Utf8),
        ]
    )
    return sub


def _join_ngs_weekly(
    pbp: pl.DataFrame,
    ngs: pl.DataFrame,
    role_col: str,
    stat_cols: list[str],
    label: str,
    *,
    rename_expected_rush: bool = False,
) -> pl.DataFrame:
    sub = _prepare_ngs_slice(ngs, stat_cols, label)
    if rename_expected_rush and "expected_rush_yards" in sub.columns:
        sub = sub.rename({"expected_rush_yards": EXPECTED_RUN_YARDS_ALIAS})
    left_on = ["season", "week", "season_type", role_col]
    right_on = ["season", "week", "season_type", "player_gsis_id"]
    out = pbp.join(sub, left_on=left_on, right_on=right_on, how="left")
    if "player_gsis_id" in out.columns:
        out = out.drop("player_gsis_id")
    return out


def _fill_and_cast(out: pl.DataFrame) -> pl.DataFrame:
    """Null-safe defaults for participation + NGS numerics; empty string for personnel."""
    exprs: list[pl.Expr] = []
    if "offense_personnel" in out.columns:
        exprs.append(pl.col("offense_personnel").fill_null(""))
    for c in ("defenders_in_box", "number_of_pass_rushers"):
        if c in out.columns:
            exprs.append(pl.col(c).fill_null(0))
    for c in NGS_PASS + NGS_REC + ["avg_time_to_los", EXPECTED_RUN_YARDS_ALIAS, "efficiency"]:
        if c in out.columns:
            exprs.append(pl.col(c).fill_null(0))
    if exprs:
        out = out.with_columns(exprs)

    out = out.with_columns(
        [
            pl.col("season").cast(pl.Int32),
            pl.col("week").cast(pl.Int32),
        ]
    )
    for role in ("passer_player_id", "rusher_player_id", "receiver_player_id"):
        if role in out.columns:
            out = out.with_columns(pl.col(role).cast(pl.Utf8))
    return out


def build_stitched_shards() -> pl.DataFrame:
    print(f"Streaming PBP {YEARS}…")
    pbp_raw = nfl.load_pbp(YEARS)
    pbp = _prepare_pbp_base(pbp_raw)
    if "season_type" not in pbp.columns:
        raise ValueError("PBP is missing season_type — required for NGS weekly joins.")

    pbp = _join_participation(pbp)

    print("Loading NGS (passing / receiving / rushing)…")
    ngs_pass = nfl.load_nextgen_stats(YEARS, stat_type="passing")
    ngs_rec = nfl.load_nextgen_stats(YEARS, stat_type="receiving")
    ngs_rush = nfl.load_nextgen_stats(YEARS, stat_type="rushing")

    pbp = _join_ngs_weekly(pbp, ngs_pass, "passer_player_id", NGS_PASS, "passing")
    pbp = _join_ngs_weekly(pbp, ngs_rec, "receiver_player_id", NGS_REC, "receiving")
    pbp = _join_ngs_weekly(
        pbp,
        ngs_rush,
        "rusher_player_id",
        NGS_RUSH,
        "rushing",
        rename_expected_rush=True,
    )

    pbp = pbp.with_columns((pl.col("yardline_100") <= 20).alias("is_red_zone"))

    pbp = _fill_and_cast(pbp)
    return pbp


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    stitched = build_stitched_shards()

    for year in YEARS:
        shard = stitched.filter(pl.col("season") == year)
        path = DATA_DIR / f"nfl_pbp_{year}.parquet"
        shard.write_parquet(path)
        print(f"✅ Shard saved: {path} ({shard.height} rows)")

    create_player_index()


if __name__ == "__main__":
    main()
