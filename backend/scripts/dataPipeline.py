"""
Master data stitcher for The Bridge: PBP + participation + Next Gen Stats → lean Parquet shards.

Processes one NFL season at a time so peak memory stays low (e.g. small cloud instances).

Joins:
  A) Participation on (old_game_id, play_id)
  B) NGS passing / receiving / rushing on (season, week, season_type, player_gsis_id ↔ role id)
"""

from __future__ import annotations

import gc
import os
from pathlib import Path

import nflreadpy as nfl
import polars as pl
from nflreadpy.utils_date import get_current_season

# Same env as the API (`DATA_LOCAL_DIR` in render.yaml → `/data` on Render).
# Default: backend/data locally.
_backend_root = Path(__file__).resolve().parent.parent
_default_data = _backend_root / "data"
_data_override = os.environ.get("DATA_LOCAL_DIR", "").strip()
DATA_DIR = Path(_data_override).resolve() if _data_override else _default_data
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


def _join_participation_for_year(pbp: pl.DataFrame, year: int) -> pl.DataFrame:
    max_part_season = get_current_season(roster=True) - 1
    if year > max_part_season:
        print(f"Skipping participation for {year} (max participation season {max_part_season}).")
        return pbp.with_columns([pl.lit(None).alias(c) for c in PART_COLS])

    need = ["old_game_id", "play_id", *PART_COLS]
    print(f"Loading participation for {year}…")
    part = nfl.load_participation([year])
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


def build_stitched_for_year(year: int) -> pl.DataFrame:
    """One season at a time; release raw PBP and each NGS frame before loading the next."""
    print(f"PBP {year}…")
    pbp_raw = nfl.load_pbp([year])
    pbp = _prepare_pbp_base(pbp_raw)
    del pbp_raw
    if "season_type" not in pbp.columns:
        raise ValueError("PBP is missing season_type — required for NGS weekly joins.")

    pbp = _join_participation_for_year(pbp, year)

    print(f"NGS passing {year}…")
    ngs = nfl.load_nextgen_stats([year], stat_type="passing")
    pbp = _join_ngs_weekly(pbp, ngs, "passer_player_id", NGS_PASS, "passing")
    del ngs

    print(f"NGS receiving {year}…")
    ngs = nfl.load_nextgen_stats([year], stat_type="receiving")
    pbp = _join_ngs_weekly(pbp, ngs, "receiver_player_id", NGS_REC, "receiving")
    del ngs

    print(f"NGS rushing {year}…")
    ngs = nfl.load_nextgen_stats([year], stat_type="rushing")
    pbp = _join_ngs_weekly(
        pbp,
        ngs,
        "rusher_player_id",
        NGS_RUSH,
        "rushing",
        rename_expected_rush=True,
    )
    del ngs

    pbp = pbp.with_columns((pl.col("yardline_100") <= 20).alias("is_red_zone"))

    return _fill_and_cast(pbp)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for year in YEARS:
        shard = build_stitched_for_year(year)
        path = DATA_DIR / f"nfl_pbp_{year}.parquet"
        shard.write_parquet(path)
        print(f"✅ Shard saved: {path} ({shard.height} rows)")
        del shard
        if os.environ.get("PIPELINE_GC", "1").strip().lower() not in ("0", "false", "no"):
            gc.collect()

    create_player_index()


if __name__ == "__main__":
    main()
