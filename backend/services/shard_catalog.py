from __future__ import annotations

import re
from pathlib import Path

from schemas.api import PbpShard

PBP_SHARD_PATTERN = re.compile(r"^nfl_pbp_(\d{4})\.parquet$")


def discover_nfl_pbp_shards_local(data_dir: Path) -> list[PbpShard]:
    if not data_dir.is_dir():
        return []

    shards: list[PbpShard] = []
    for file_path in data_dir.iterdir():
        if not file_path.is_file():
            continue
        m = PBP_SHARD_PATTERN.match(file_path.name)
        if not m:
            continue
        shards.append(PbpShard(year=int(m.group(1)), path=f"/data/{file_path.name}"))

    return sorted(shards, key=lambda s: s.year)
