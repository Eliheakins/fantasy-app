"""
NFL-only stitch: nflverse PBP + participation + Next Gen Stats.

Used by `build_data.py` for chunked Parquet output (`nfl_pbp_YYYY.parquet`).

Joins:
  A) Participation on (old_game_id, play_id)
  B) NGS passing / receiving / rushing on (season, week, season_type, player_gsis_id ↔ role id)
"""

from __future__ import annotations

from pathlib import Path

import nflreadpy as nfl
import polars as pl

from nfl_stat.core.seasons import roster_season
from nfl_stat.pipeline import nflverse
from nfl_stat.pipeline.atomic import atomic_path
from nfl_stat.pipeline.pbp_source import ensure_pbp
from nfl_stat.pipeline.players import merge_player_index, read_player_index

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

# After join: expose NGS rushing expected yards under the prompt's name
EXPECTED_RUN_YARDS_ALIAS = "expected_run_yards"

NGS_COLS = [*NGS_PASS, *NGS_REC, "avg_time_to_los", EXPECTED_RUN_YARDS_ALIAS, "efficiency"]
PART_DTYPES: dict[str, pl.DataType | type[pl.DataType]] = {
    "offense_personnel": pl.Utf8,
    "defenders_in_box": pl.Int32,
    "number_of_pass_rushers": pl.Int32,
}


def _load_pbp_parquet_pruned(year: int) -> pl.DataFrame:
    """Read PBP from the shared local copy (`pbp_source`), keeping only the PBP_COLS columns."""
    path = ensure_pbp(year)
    names = set(pl.scan_parquet(path).collect_schema().names())
    cols = [c for c in PBP_COLS if c in names]
    missing = [c for c in PBP_COLS if c not in names]
    if missing:
        print(f"⚠️  PBP file missing columns (omitted): {missing}")
    if "play_type" not in cols:
        raise ValueError(f"PBP file for {year} has no play_type column ({path})")
    return pl.read_parquet(path, columns=cols)


def create_player_index(data_dir: Path, years: list[int]) -> None:
    """One row per player (latest season seen, across builds) in player_index.parquet."""
    print("Building player index…")
    rosters = nflverse.rosters(years)
    player_index = rosters.select(
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
    ).with_columns(pl.col("gsis_id").cast(pl.Utf8), pl.col("season").cast(pl.Int32))
    out_path = data_dir / "player_index.parquet"
    merged = merge_player_index(read_player_index(out_path), player_index)
    with atomic_path(out_path) as tmp:
        merged.write_parquet(tmp)
    print(f"✅ Player index: {out_path}")


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
    max_part_season = roster_season() - 1
    if year > max_part_season:
        print(f"Skipping participation for {year} (max participation season {max_part_season}).")
        return pbp.with_columns([pl.lit(None, dtype=PART_DTYPES[c]).alias(c) for c in PART_COLS])

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
        print(f"⚠️  NGS {label} missing stats (left null): {miss_s}")
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


def finalize_columns(out: pl.DataFrame) -> pl.DataFrame:
    """
    Cast to storage types.

    Missing participation and NGS values stay null. Filling them with 0 would turn "not measured"
    into a real value, and averages and filters would then count it.
    """
    casts: list[pl.Expr] = [
        pl.col(c).cast(dtype) for c, dtype in PART_DTYPES.items() if c in out.columns
    ]
    casts += [pl.col(c).cast(pl.Float64) for c in NGS_COLS if c in out.columns]
    casts += [pl.col(c).cast(pl.Int32) for c in ("season", "week") if c in out.columns]
    casts += [
        pl.col(c).cast(pl.Utf8)
        for c in ("passer_player_id", "rusher_player_id", "receiver_player_id")
        if c in out.columns
    ]
    return out.with_columns(casts) if casts else out


def null_report(df: pl.DataFrame) -> dict[str, float]:
    """Share of missing values for each participation and NGS column present in the frame."""
    if df.height == 0:
        return {}
    return {c: df[c].null_count() / df.height for c in [*PART_COLS, *NGS_COLS] if c in df.columns}


def format_null_report(report: dict[str, float]) -> str:
    """One line per column, most-missing first, for the end of a season build."""
    lines = [
        f"  {c}: {rate:.0%} missing" for c, rate in sorted(report.items(), key=lambda x: -x[1])
    ]
    return "\n".join(lines)


def build_stitched_for_year(year: int) -> pl.DataFrame:
    """One season at a time; release raw PBP and each NGS frame before loading the next."""
    print(f"PBP {year} (nflverse Parquet, pruned columns)…")
    pbp_raw = _load_pbp_parquet_pruned(year)
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

    return finalize_columns(pbp)
