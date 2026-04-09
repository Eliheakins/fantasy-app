#!/usr/bin/env python3
"""
CLI for building NFL/CFB Parquet shards, player index, and Rosetta layer.

Run: ``python scripts/build_data.py`` (adds backend dir to sys.path) or
``python -m pipeline.cli`` from ``backend/`` with PYTHONPATH=.
"""

from __future__ import annotations

import argparse
import gc
import os
from pathlib import Path

from pipeline.college_data import build_cfb_stitched_for_year
from pipeline.nfl_pipeline import build_stitched_for_year, create_player_index
from pipeline.rosetta_layer import build_rosetta_layer

_backend_root = Path(__file__).resolve().parent.parent
_default_data = _backend_root / "data"


def data_output_dir() -> Path:
    """Resolved output directory (DATA_LOCAL_DIR or backend/data)."""
    override = os.environ.get("DATA_LOCAL_DIR", "").strip()
    return Path(override).resolve() if override else _default_data.resolve()


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


DEFAULT_YEARS = [2021, 2022, 2023, 2024, 2025]


def run_build(
    data_dir: Path,
    years: list[int],
    *,
    build_nfl: bool,
    build_cfb: bool,
    build_player_index: bool,
    build_rosetta: bool,
) -> None:
    data_dir = Path(data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    if build_nfl:
        for year in years:
            shard = build_stitched_for_year(year)
            path = data_dir / f"nfl_pbp_{year}.parquet"
            shard.write_parquet(path)
            print(f"✅ Shard saved: {path} ({shard.height} rows)")
            del shard
            _maybe_gc()

    if build_cfb:
        for year in years:
            shard = build_cfb_stitched_for_year(year)
            path = data_dir / f"cfb_pbp_{year}.parquet"
            shard.write_parquet(path)
            print(f"✅ Shard saved: {path} ({shard.height} rows)")
            del shard
            _maybe_gc()

    if build_player_index:
        create_player_index(data_dir, years)

    if build_rosetta:
        build_rosetta_layer(data_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build NFL/CFB PBP Parquet shards, player index, and Rosetta gold layer.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help=f"Output directory (default: DATA_LOCAL_DIR env or {_default_data})",
    )
    parser.add_argument(
        "--years",
        type=str,
        default=None,
        help=f"Comma-separated seasons (default: {','.join(map(str, DEFAULT_YEARS))})",
    )
    parser.add_argument(
        "--rosetta-only",
        action="store_true",
        help="Only run Rosetta (player_hub, gold, manifests); assumes Parquet shards already exist.",
    )
    parser.add_argument(
        "--skip-rosetta",
        action="store_true",
        help="Only build Parquet shards (+ player index); skip DuckDB/Rosetta materialization.",
    )
    parser.add_argument(
        "--skip-nfl",
        action="store_true",
        help="Skip NFL PBP shards (and player index, which uses NFL rosters).",
    )
    parser.add_argument(
        "--skip-cfb",
        action="store_true",
        help="Skip CFB PBP shards.",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir).resolve() if args.data_dir else data_output_dir()
    years = _parse_years(args.years) if args.years else list(DEFAULT_YEARS)

    if args.rosetta_only and args.skip_rosetta:
        parser.error("--rosetta-only and --skip-rosetta are mutually exclusive")

    if args.rosetta_only:
        build_nfl = build_cfb = build_player_index = False
        build_rosetta = True
    else:
        build_nfl = not args.skip_nfl
        build_cfb = not args.skip_cfb
        build_rosetta = not args.skip_rosetta
        build_player_index = build_nfl

    if not build_nfl and not build_cfb and not build_rosetta:
        parser.error("Nothing to do: enable at least one of NFL, CFB, or Rosetta")

    print(f"📂 Data directory: {data_dir}")
    print(f"📅 Years: {years}")
    print(
        f"🔧 Steps: nfl={build_nfl} cfb={build_cfb} "
        f"player_index={build_player_index} rosetta={build_rosetta}\n"
    )

    run_build(
        data_dir,
        years,
        build_nfl=build_nfl,
        build_cfb=build_cfb,
        build_player_index=build_player_index,
        build_rosetta=build_rosetta,
    )
    print("\n✅ build_data finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
