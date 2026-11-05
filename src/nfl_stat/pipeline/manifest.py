"""Build and write the manifest by looking at what is actually in the data folder."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import cast

import polars as pl
import pyarrow.parquet as pq
from pydantic import ValidationError

from nfl_stat.pipeline.atomic import atomic_path
from nfl_stat.pipeline.player_game import PLAYER_GAME_FILENAME
from nfl_stat.pipeline.players import PLAYER_INDEX_FILENAME, PLAYERS_FILENAME
from nfl_stat.schemas.manifest import (
    MANIFEST_FILENAME,
    FileEntry,
    JsonFileEntry,
    Manifest,
    SeasonEntry,
)
from nfl_stat.schemas.players import PlayersFile

SHARD_PATTERN = re.compile(r"^nfl_pbp_(\d{4})\.parquet$")


def _summarize_shard(path: Path, season: int) -> SeasonEntry:
    try:
        df = pl.read_parquet(path, columns=["week", "defenders_in_box"])
    except pl.exceptions.ColumnNotFoundError as e:
        raise ValueError(f"{path.name} lacks the columns the manifest needs: {e}") from e
    return SeasonEntry(
        season=season,
        path=path.name,
        rows=df.height,
        max_week=cast(int | None, df["week"].max()),  # an int column
        # A real play always has at least one defender in the box. Shards built before missing
        # values were kept null hold 0 instead, so a column of zeros also means "no data".
        has_participation=bool((df["defenders_in_box"] > 0).any()),
    )


def _file_entry(path: Path) -> FileEntry | None:
    if not path.is_file():
        return None
    return FileEntry(path=path.name, rows=pq.read_metadata(path).num_rows)


def _players_entry(path: Path) -> JsonFileEntry | None:
    if not path.is_file():
        return None
    try:
        players = PlayersFile.model_validate_json(path.read_text(encoding="utf-8")).players
    except (ValidationError, UnicodeDecodeError) as e:
        raise ValueError(f"{path.name} is invalid, rebuild the data: {e}") from e
    return JsonFileEntry(path=path.name, rows=len(players))


def build_manifest(data_dir: Path, *, built_at: datetime | None = None) -> Manifest:
    """Describe every shard in `data_dir`, not only the ones the current run rebuilt."""
    shards = sorted(
        (int(m.group(1)), p) for p in data_dir.iterdir() if (m := SHARD_PATTERN.match(p.name))
    )
    # A shard with no plays (built before a season's first game) is not a season yet.
    seasons = [s for s in (_summarize_shard(p, season) for season, p in shards) if s.rows > 0]
    return Manifest(
        built_at=(built_at or datetime.now(UTC)).isoformat(),
        nflreadpy_version=version("nflreadpy"),
        seasons=seasons,
        player_index=_file_entry(data_dir / PLAYER_INDEX_FILENAME),
        player_game=_file_entry(data_dir / PLAYER_GAME_FILENAME),
        players=_players_entry(data_dir / PLAYERS_FILENAME),
    )


def write_manifest(manifest: Manifest, data_dir: Path) -> Path:
    """Write atomically, so the API never reads a half-written file."""
    target = data_dir / MANIFEST_FILENAME
    with atomic_path(target) as tmp:
        tmp.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return target
