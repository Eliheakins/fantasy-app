from __future__ import annotations

from pathlib import Path

from services.shard_catalog import discover_nfl_pbp_shards_local


def test_lists_nfl_shards_sorted_by_year_and_ignores_other_entries(tmp_path: Path):
    for name in [
        "nfl_pbp_2023.parquet",
        "nfl_pbp_2021.parquet",
        "player_index.parquet",
        "nfl_pbp_20.parquet",
        "notes.txt",
    ]:
        (tmp_path / name).touch()
    (tmp_path / "nfl_pbp_2099.parquet").mkdir()

    shards = discover_nfl_pbp_shards_local(tmp_path)

    assert [(s.year, s.path) for s in shards] == [
        (2021, "/data/nfl_pbp_2021.parquet"),
        (2023, "/data/nfl_pbp_2023.parquet"),
    ]


def test_returns_empty_list_for_missing_directory(tmp_path: Path):
    assert discover_nfl_pbp_shards_local(tmp_path / "missing") == []
