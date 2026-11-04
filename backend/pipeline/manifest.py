"""Build and write the manifest by looking at what is actually in the data folder."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

from schemas.manifest import MANIFEST_FILENAME, FileEntry, Manifest, SeasonEntry

SHARD_PATTERN = re.compile(r"^nfl_pbp_(\d{4})\.parquet$")
PLAYER_INDEX_FILENAME = "player_index.parquet"


def _summarize_shard(path: Path, season: int) -> SeasonEntry:
    try:
        df = pl.read_parquet(path, columns=["week", "defenders_in_box"])
    except pl.exceptions.ColumnNotFoundError as e:
        raise ValueError(f"{path.name} lacks the columns the manifest needs: {e}") from e
    return SeasonEntry(
        season=season,
        path=path.name,
        rows=df.height,
        max_week=df["week"].max(),
        has_participation=df["defenders_in_box"].null_count() < df.height,
    )


def build_manifest(data_dir: Path, *, built_at: datetime | None = None) -> Manifest:
    """Describe every shard in `data_dir`, not only the ones the current run rebuilt."""
    shards = sorted(
        (int(m.group(1)), p) for p in data_dir.iterdir() if (m := SHARD_PATTERN.match(p.name))
    )
    index_path = data_dir / PLAYER_INDEX_FILENAME
    return Manifest(
        built_at=(built_at or datetime.now(UTC)).isoformat(),
        nflreadpy_version=version("nflreadpy"),
        seasons=[_summarize_shard(p, season) for season, p in shards],
        player_index=(
            FileEntry(path=index_path.name, rows=pq.read_metadata(index_path).num_rows)
            if index_path.is_file()
            else None
        ),
    )


def write_manifest(manifest: Manifest, data_dir: Path) -> Path:
    """Write atomically, so the API never reads a half-written file."""
    target = data_dir / MANIFEST_FILENAME
    tmp = data_dir / f".{MANIFEST_FILENAME}.tmp"
    tmp.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return target
