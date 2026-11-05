"""One local copy of each season's nflverse play-by-play, shared by the team pace and efficiency
stages and the stat build: `data/raw/pbp/<season>.parquet`, the full nflverse file (raw nflverse
data only, never served: the stat mount covers `data/stat` alone).

A season is complete once its file was written on or after March 1 of the next year (after its
last games); that file is kept for good. Any other file (the season in progress, or a past season
fetched mid-season) is refreshed when older than TTL_HOURS: nflverse updates the file about nightly after games, and the Tuesday,
Friday and Sunday refreshes are at least a day apart, so each gets new data while a rerun within
the same morning (or `make refresh` followed by `make stat-data-refresh`) reuses the file.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import polars as pl
import requests

from nfl_stat.core.config import REPO_ROOT
from nfl_stat.core.seasons import NFLVERSE_PBP_FIRST_SEASON as FIRST_SEASON
from nfl_stat.core.seasons import current_season
from nfl_stat.pipeline.atomic import atomic_path

# Same release host as nflreadpy downloader; override with NFLVERSE_DOWNLOAD_BASE.
_DEFAULT_NFLVERSE_DL = "https://github.com/nflverse/nflverse-data/releases/download/"
COMPLETE_AFTER = (3, 1)  # month, day of the year after the season: the file is final from then
PBP_DIR = REPO_ROOT / "data" / "raw" / "pbp"
TTL_HOURS = 12.0
TIMEOUT_SECONDS = 120
CHUNK_BYTES = 1 << 20


def get_nfl_url(year: int, kind: str) -> str:
    """Public nflverse-data release URL (same paths as nflreadpy `downloader.download`)."""
    base = os.environ.get("NFLVERSE_DOWNLOAD_BASE", _DEFAULT_NFLVERSE_DL).strip()
    if not base.startswith(("https://", "http://")):
        raise ValueError(
            f"NFLVERSE_DOWNLOAD_BASE must start with https:// or http://, got {base!r}"
        )
    if not base.endswith("/"):
        base = f"{base}/"
    if kind == "pbp":
        rel = f"pbp/play_by_play_{year}.parquet"
    else:
        raise ValueError(f"Unknown nflverse asset kind {kind!r} (supported: 'pbp')")
    return urljoin(base, rel)


def pbp_path(season: int) -> Path:
    return PBP_DIR / f"{season}.parquet"


def _fetch(season: int, dest: Path) -> None:
    """Download the season's file to `dest`. Failures raise ConnectionError chained to the
    requests error, as nflreadpy's downloader does, so a 404 stays recognisable."""
    url = get_nfl_url(season, "pbp")
    try:
        # GitHub's release CDN answers Polars' remote range requests with 501: download whole.
        with requests.get(url, stream=True, timeout=TIMEOUT_SECONDS) as response:
            response.raise_for_status()
            with dest.open("wb") as out:
                for chunk in response.iter_content(chunk_size=CHUNK_BYTES):
                    out.write(chunk)
    except requests.exceptions.RequestException as error:
        raise ConnectionError(f"Failed to download {url}: {error}") from error


def _is_fresh(path: Path, season: int) -> bool:
    if not path.exists():
        return False
    written = path.stat().st_mtime
    if written >= datetime(season + 1, *COMPLETE_AFTER).timestamp():
        return True  # written after the season ended
    return 0 <= (time.time() - written) / 3600 < TTL_HOURS  # a future mtime is not fresh


def ensure_pbp(season: int) -> Path:
    """The local file for the season, downloaded (atomically) first if missing or not fresh."""
    current = current_season()
    if not FIRST_SEASON <= season <= current:  # the message nflreadpy gives; callers match it
        raise ValueError(f"Season must be between {FIRST_SEASON} and {current}")
    path = pbp_path(season)
    if _is_fresh(path, season):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_path(path) as tmp:
        _fetch(season, tmp)
        try:
            pl.scan_parquet(tmp).collect_schema()
        except Exception as error:  # an HTML error page must not become the cache
            raise ValueError(f"download for {season} is not a readable parquet file") from error
    return path


def read_pbp(season: int, columns: list[str] | None = None) -> pl.DataFrame:
    """The season's play-by-play, all columns or only `columns` (lower memory)."""
    return pl.read_parquet(ensure_pbp(season), columns=columns)
