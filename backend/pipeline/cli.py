#!/usr/bin/env python3
"""
CLI for building the NFL play-by-play Parquet shards and the player index.

Run: ``uv run python backend/scripts/build_data.py`` (adds backend dir to sys.path).
"""

from __future__ import annotations

import argparse
import gc
import os
from pathlib import Path

from nflreadpy.utils_date import get_current_season

from pipeline.manifest import build_manifest, write_manifest
from pipeline.nfl_pipeline import (
    build_stitched_for_year,
    create_player_index,
    format_null_report,
    null_report,
)

_backend_root = Path(__file__).resolve().parent.parent
_default_data = _backend_root / "data"


def data_output_dir() -> Path:
    return _default_data.resolve()


def _maybe_gc() -> None:
    if os.environ.get("PIPELINE_GC", "1").strip().lower() not in ("0", "false", "no"):
        gc.collect()


def _parse_years(raw: str) -> list[int]:
    years: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        years.append(int(part, 10))
    if not years:
        raise ValueError("No years parsed (expected comma-separated integers, e.g. 2022,2023,2024)")
    return years


FIRST_SEASON = 2021


def default_years() -> list[int]:
    """Every season from FIRST_SEASON through the current one, so a new season needs no code edit."""
    return list(range(FIRST_SEASON, max(FIRST_SEASON, get_current_season()) + 1))


def run_build(data_dir: Path, years: list[int]) -> None:
    data_dir = Path(data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    for year in years:
        shard = build_stitched_for_year(year)
        path = data_dir / f"nfl_pbp_{year}.parquet"
        shard.write_parquet(path)
        print(f"✅ Shard saved: {path} ({shard.height} rows)")
        print(f"Missing values (kept as null):\n{format_null_report(null_report(shard))}")
        del shard
        _maybe_gc()

    create_player_index(data_dir, years)

    manifest = build_manifest(data_dir)
    write_manifest(manifest, data_dir)
    print(f"✅ Manifest: {len(manifest.seasons)} seasons, data through {manifest.data_through}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build NFL play-by-play Parquet shards and the player index.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help=f"Output directory (default: {_default_data})",
    )
    parser.add_argument(
        "--years",
        type=str,
        default=None,
        help=f"Comma-separated seasons (default: {FIRST_SEASON} through the current season)",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir).resolve() if args.data_dir else data_output_dir()
    years = _parse_years(args.years) if args.years else default_years()

    print(f"📂 Data directory: {data_dir}")
    print(f"📅 Years: {years}\n")

    run_build(data_dir, years)
    print("\n✅ build_data finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
