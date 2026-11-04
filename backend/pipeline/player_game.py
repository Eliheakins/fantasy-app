"""
Tier 1: one row per player per game with the official counting totals.

Source is nflverse's weekly player stats, whose totals match the official lines (unlike sums over
play-by-play rows, which count sack yardage against the passer). Situational splits still need the
play-level shards; this table answers questions that have no down, quarter or weather filter.
"""

from __future__ import annotations

from pathlib import Path

import nflreadpy as nfl
import polars as pl

from pipeline.atomic import atomic_path

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
    if values.is_nan().any() or not (values == values.round()).all():
        raise ValueError(f"{column} has fractional or NaN values; refusing to truncate them")
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
    """Download and normalize the requested seasons."""
    return normalize_player_game(nfl.load_player_stats(years, summary_level="week"))


def merge_player_game(existing: pl.DataFrame | None, new: pl.DataFrame) -> pl.DataFrame:
    """
    Add `new` to the table already on disk, replacing only the seasons it contains.

    A partial rebuild (`--years 2026`) must not drop 2021-2025, which live in this one file.
    """
    if existing is None:
        return new
    if existing.columns != new.columns:
        raise ValueError(
            "The existing player_game.parquet has different columns; rebuild all seasons to replace it"
        )
    kept = existing.filter(~pl.col("season").is_in(new["season"].unique().implode()))
    return pl.concat([kept, new]).sort(["season", "gsis_id", "week"])


def read_player_game(data_dir: Path) -> pl.DataFrame | None:
    """The table already on disk, or None before the first build."""
    path = data_dir / PLAYER_GAME_FILENAME
    return pl.read_parquet(path) if path.is_file() else None


def write_player_game(
    df: pl.DataFrame, data_dir: Path, *, row_group_size: int = ROW_GROUP_SIZE
) -> Path:
    """Write atomically so a reader never sees a half-written file."""
    target = data_dir / PLAYER_GAME_FILENAME
    with atomic_path(target) as tmp:
        df.write_parquet(tmp, compression="zstd", row_group_size=row_group_size, statistics=True)
    return target
