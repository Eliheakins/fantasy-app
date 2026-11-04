"""The data folder's table of contents: what was built, from what, and how current it is."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

MANIFEST_FILENAME = "manifest.json"
SCHEMA_VERSION = 1

# A plain Parquet file name: no directories, no URL, nothing that could leave the data folder.
FILE_NAME_PATTERN = r"^[\w.-]+\.parquet$"


class SeasonEntry(BaseModel):
    season: int
    path: str = Field(
        ...,
        pattern=FILE_NAME_PATTERN,
        description="File name, relative to the data folder or CDN base",
    )
    rows: int
    max_week: int | None = Field(
        None, description="Latest week in the shard (playoffs continue past 18)"
    )
    has_participation: bool = Field(..., description="False when no play has participation data")


class FileEntry(BaseModel):
    path: str = Field(..., pattern=FILE_NAME_PATTERN)
    rows: int


class Manifest(BaseModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    built_at: str
    nflreadpy_version: str
    seasons: list[SeasonEntry]
    player_index: FileEntry | None = None
    player_game: FileEntry | None = Field(
        None, description="Tier-1 table: one row per player per game, official counting totals"
    )

    @property
    def data_through(self) -> str | None:
        """Human label for how current the data is, e.g. "2026 week 9"."""
        if not self.seasons:
            return None
        latest = self.seasons[-1]
        if latest.max_week is None:
            return str(latest.season)
        return f"{latest.season} week {latest.max_week}"


def read_manifest(data_dir: Path) -> Manifest | None:
    """The manifest in `data_dir`, or None if the data has not been built yet."""
    path = data_dir / MANIFEST_FILENAME
    if not path.is_file():
        return None
    try:
        return Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as e:
        raise ValueError(f"{MANIFEST_FILENAME} is invalid, rebuild the data: {e}") from e
