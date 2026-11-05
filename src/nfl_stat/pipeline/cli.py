#!/usr/bin/env python3
"""
CLI for building the NFL play-by-play Parquet shards and the player index.

Run: ``uv run python -m nfl_stat.pipeline.cli`` (``make stat-data``).
"""

from __future__ import annotations

import argparse
import gc
import os
from pathlib import Path

from nfl_stat.core.config import DEFAULT_DATA_DIR
from nfl_stat.core.seasons import STAT_SHARDS_FIRST_SEASON as FIRST_SEASON
from nfl_stat.core.seasons import current_season
from nfl_stat.pipeline.atomic import atomic_path
from nfl_stat.pipeline.manifest import build_manifest, write_manifest
from nfl_stat.pipeline.nfl_pipeline import (
    build_stitched_for_year,
    create_player_index,
    format_null_report,
    null_report,
)
from nfl_stat.pipeline.player_game import (
    build_player_game,
    merge_player_game,
    read_player_game,
    write_player_game,
)
from nfl_stat.pipeline.players import write_players_file


def data_output_dir() -> Path:
    return DEFAULT_DATA_DIR.resolve()


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


def default_years() -> list[int]:
    """Every season from FIRST_SEASON through the current one, so a new season needs no code edit."""
    return list(range(FIRST_SEASON, max(FIRST_SEASON, current_season()) + 1))


def run_build(data_dir: Path, years: list[int]) -> None:
    data_dir = Path(data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    for year in years:
        shard = build_stitched_for_year(year)
        path = data_dir / f"nfl_pbp_{year}.parquet"
        with atomic_path(path) as tmp:
            shard.write_parquet(tmp)
        print(f"✅ Shard saved: {path} ({shard.height} rows)")
        report = format_null_report(null_report(shard))
        if report:
            print(f"Missing values (kept as null):\n{report}")
        del shard
        _maybe_gc()

    create_player_index(data_dir, years)

    # Describe what is on disk before the later steps, so a failure there still leaves a
    # manifest that matches the shards.
    _write_manifest(data_dir)

    players_file, skipped = write_players_file(data_dir)
    print(f"✅ Players: {players_file.rows} in players.json, {skipped} skipped (no id or name)")
    _write_manifest(data_dir)

    merged = merge_player_game(
        read_player_game(data_dir),
        build_player_game(years),
    )
    write_player_game(merged, data_dir)
    print(f"✅ Player-game table: {merged.height} rows")

    _write_manifest(data_dir)


def _write_manifest(data_dir: Path) -> None:
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
        help=f"Output directory (default: {DEFAULT_DATA_DIR})",
    )
    which = parser.add_mutually_exclusive_group()
    which.add_argument(
        "--years",
        type=str,
        default=None,
        help=f"Comma-separated seasons (default: {FIRST_SEASON} through the current season)",
    )
    which.add_argument(
        "--refresh",
        action="store_true",
        help="Rebuild only the current season (the weekly update); other seasons are kept",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir).resolve() if args.data_dir else data_output_dir()
    if args.refresh:
        years = [current_season()]
    else:
        years = _parse_years(args.years) if args.years else default_years()

    print(f"📂 Data directory: {data_dir}")
    print(f"📅 Years: {years}\n")

    run_build(data_dir, years)
    print("\n✅ build_data finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
