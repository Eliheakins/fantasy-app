from __future__ import annotations

import re
from pathlib import Path

from schemas.api import PbpShard

PBP_SHARD_PATTERN = re.compile(r"^nfl_pbp_(\d{4})\.parquet$")
CFB_PBP_SHARD_PATTERN = re.compile(r"^cfb_pbp_(\d{4})\.parquet$")


def parse_int_csv_env(raw: str) -> list[int]:
    raw = raw.strip()
    if not raw:
        return []
    years: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        years.append(int(part, 10))
    return years


def discover_pbp_shards_local(data_dir: Path, *, pattern: re.Pattern[str]) -> list[PbpShard]:
    if not data_dir.is_dir():
        return []

    shards: list[PbpShard] = []
    for file_path in data_dir.iterdir():
        if not file_path.is_file():
            continue
        m = pattern.match(file_path.name)
        if not m:
            continue
        year = int(m.group(1))
        path = f"/data/{file_path.name}"
        shards.append(PbpShard(year=year, path=path))

    return sorted(shards, key=lambda s: s.year)


def discover_nfl_pbp_shards_local(data_dir: Path) -> list[PbpShard]:
    return discover_pbp_shards_local(data_dir, pattern=PBP_SHARD_PATTERN)


def discover_cfb_pbp_shards_local(data_dir: Path) -> list[PbpShard]:
    return discover_pbp_shards_local(data_dir, pattern=CFB_PBP_SHARD_PATTERN)


def discover_pbp_shards_r2(public_base: str, years: list[int], *, prefix: str) -> list[PbpShard]:
    base = public_base.rstrip("/")
    out = [PbpShard(year=y, path=f"{base}/{prefix}_{y}.parquet") for y in years]
    return sorted(out, key=lambda s: s.year)


def discover_nfl_pbp_shards_r2(public_base: str, years: list[int]) -> list[PbpShard]:
    return discover_pbp_shards_r2(public_base, years, prefix="nfl_pbp")


def discover_cfb_pbp_shards_r2(public_base: str, years: list[int]) -> list[PbpShard]:
    return discover_pbp_shards_r2(public_base, years, prefix="cfb_pbp")
