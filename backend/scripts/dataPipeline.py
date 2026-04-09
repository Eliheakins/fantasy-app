"""
Chunked Parquet writer for The Bridge data directory.

Orchestrates league-specific builders into `DATA_LOCAL_DIR` / `backend/data`.
"""

from __future__ import annotations

import gc
import os
from pathlib import Path

from collegeData import build_cfb_stitched_for_year
from nfl_pipeline import build_stitched_for_year, create_player_index
from rosetta_layer import build_rosetta_layer

# Same env as the API (`DATA_LOCAL_DIR` in render.yaml → `/data` on Render).
# Default: backend/data locally.
_backend_root = Path(__file__).resolve().parent.parent
_default_data = _backend_root / "data"
_data_override = os.environ.get("DATA_LOCAL_DIR", "").strip()
DATA_DIR = Path(_data_override).resolve() if _data_override else _default_data
YEARS = [2021, 2022, 2023, 2024, 2025]


def _maybe_gc() -> None:
    if os.environ.get("PIPELINE_GC", "1").strip().lower() not in ("0", "false", "no"):
        gc.collect()


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for year in YEARS:
        shard = build_stitched_for_year(year)
        path = DATA_DIR / f"nfl_pbp_{year}.parquet"
        shard.write_parquet(path)
        print(f"✅ Shard saved: {path} ({shard.height} rows)")
        del shard
        _maybe_gc()

    for year in YEARS:
        shard = build_cfb_stitched_for_year(year)
        path = DATA_DIR / f"cfb_pbp_{year}.parquet"
        shard.write_parquet(path)
        print(f"✅ Shard saved: {path} ({shard.height} rows)")
        del shard
        _maybe_gc()

    create_player_index(DATA_DIR, YEARS)

    build_rosetta_layer(DATA_DIR)


if __name__ == "__main__":
    main()
