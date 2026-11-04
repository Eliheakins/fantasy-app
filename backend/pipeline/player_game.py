"""
Tier 1: one row per player per game with the official counting totals.

Source is nflverse's weekly player stats, whose totals match the official lines (unlike sums over
play-by-play rows, which count sack yardage against the passer). Situational splits still need the
play-level shards; this table answers questions that have no down, quarter or weather filter.
"""

from __future__ import annotations

import os
from pathlib import Path

import nflreadpy as nfl
import polars as pl

PLAYER_GAME_FILENAME = "player_game.parquet"
# Small row groups let a reader fetch only the seasons and players it needs.
ROW_GROUP_SIZE = 10_000

_RENAMES = {"player_id": "gsis_id", "player_display_name": "full_name"}
_SEASON_TYPES = ["REG", "POST"]

_TEXT = ["gsis_id", "full_name", "position", "team", "opponent_team", "season_type"]
_COUNTS = [
    "season",
    "week",
    "completions",
    "attempts",
    "passing_yards",
    "passing_tds",
    "passing_interceptions",
    "sacks_suffered",
    "sack_yards_lost",
    "carries",
    "rushing_yards",
    "rushing_tds",
    "receptions",
    "targets",
    "receiving_yards",
    "receiving_tds",
    "receiving_yards_after_catch",
]
_EPA = ["passing_epa", "rushing_epa", "receiving_epa"]

PLAYER_GAME_COLUMNS = [
    "gsis_id",
    "full_name",
    "position",
    "team",
    "opponent_team",
    "season",
    "week",
    "season_type",
    *_COUNTS[2:],
    *_EPA,
]


def _as_int32(df: pl.DataFrame, column: str) -> pl.Expr:
    """Cast a count to Int32, refusing to silently drop a fractional part."""
    values = df[column].drop_nulls().cast(pl.Float64)
    if not (values == values.round()).all():
        raise ValueError(f"{column} has fractional values; refusing to truncate them")
    return pl.col(column).cast(pl.Int32)


def normalize_player_game(df: pl.DataFrame) -> pl.DataFrame:
    """Keep the tier-1 columns, give them the app's names and types, and sort for range reads."""
    source = {new: old for old, new in _RENAMES.items()}
    wanted = [source.get(c, c) for c in PLAYER_GAME_COLUMNS]
    missing = [c for c in wanted if c not in df.columns]
    if missing:
        raise ValueError(f"nflverse player stats lack expected columns: {missing}")

    out = df.select(wanted).rename(_RENAMES)
    out = out.filter(pl.col("gsis_id").is_not_null() & pl.col("season_type").is_in(_SEASON_TYPES))
    out = out.with_columns(
        [_as_int32(out, c) for c in _COUNTS]
        + [pl.col(c).cast(pl.Utf8) for c in _TEXT]
        # Missing EPA (a player who never passed) stays null; 0.0 would be a real value.
        + [pl.col(c).cast(pl.Float64) for c in _EPA]
    )
    return out.select(PLAYER_GAME_COLUMNS).sort(["season", "gsis_id", "week"])


def build_player_game(years: list[int]) -> pl.DataFrame:
    return normalize_player_game(nfl.load_player_stats(years, summary_level="week"))


def write_player_game(
    df: pl.DataFrame, data_dir: Path, *, row_group_size: int = ROW_GROUP_SIZE
) -> Path:
    """Write atomically so a reader never sees a half-written file."""
    target = data_dir / PLAYER_GAME_FILENAME
    tmp = data_dir / f".{PLAYER_GAME_FILENAME}.tmp"
    df.write_parquet(tmp, compression="zstd", row_group_size=row_group_size, statistics=True)
    os.replace(tmp, target)
    return target
