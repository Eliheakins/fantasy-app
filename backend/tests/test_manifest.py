from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from pipeline.manifest import build_manifest, write_manifest
from schemas.manifest import MANIFEST_FILENAME, Manifest, read_manifest

BUILT_AT = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def _write_shard(data_dir: Path, season: int, weeks: list[int], box: list[int | None]) -> None:
    pl.DataFrame(
        {
            "season": [season] * len(weeks),
            "week": weeks,
            "season_type": ["REG"] * len(weeks),
            "defenders_in_box": box,
        },
        schema_overrides={"defenders_in_box": pl.Int32},
    ).write_parquet(data_dir / f"nfl_pbp_{season}.parquet")


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    _write_shard(tmp_path, 2025, [1, 2, 3], [6, 7, 5])
    _write_shard(tmp_path, 2026, [1, 8, 9], [None, None, None])
    return tmp_path


def test_manifest_lists_every_shard_in_season_order_with_its_facts(data_dir: Path):
    manifest = build_manifest(data_dir, built_at=BUILT_AT)

    assert [s.season for s in manifest.seasons] == [2025, 2026]
    latest = manifest.seasons[-1]
    assert (latest.path, latest.rows, latest.max_week) == ("nfl_pbp_2026.parquet", 3, 9)
    assert manifest.built_at == "2026-11-04T12:00:00+00:00"


def test_participation_flag_is_true_only_when_some_values_exist(data_dir: Path):
    manifest = build_manifest(data_dir, built_at=BUILT_AT)

    assert [s.has_participation for s in manifest.seasons] == [True, False]


def test_data_through_names_the_latest_season_and_week(data_dir: Path):
    assert build_manifest(data_dir, built_at=BUILT_AT).data_through == "2026 week 9"


def test_data_through_is_none_without_shards(tmp_path: Path):
    assert build_manifest(tmp_path, built_at=BUILT_AT).data_through is None


def test_player_index_is_listed_when_present(data_dir: Path):
    pl.DataFrame({"gsis_id": ["1", "2"]}).write_parquet(data_dir / "player_index.parquet")

    manifest = build_manifest(data_dir, built_at=BUILT_AT)

    assert manifest.player_index is not None
    assert (manifest.player_index.path, manifest.player_index.rows) == ("player_index.parquet", 2)


def test_other_files_are_ignored(data_dir: Path):
    (data_dir / "notes.txt").touch()
    (data_dir / "nfl_pbp_20.parquet").touch()

    assert [s.season for s in build_manifest(data_dir, built_at=BUILT_AT).seasons] == [2025, 2026]


def test_a_shard_missing_required_columns_names_the_file(tmp_path: Path):
    pl.DataFrame({"season": [2024]}).write_parquet(tmp_path / "nfl_pbp_2024.parquet")

    with pytest.raises(ValueError, match="nfl_pbp_2024.parquet"):
        build_manifest(tmp_path, built_at=BUILT_AT)


def test_write_then_read_round_trips_and_leaves_no_temp_file(data_dir: Path):
    manifest = build_manifest(data_dir, built_at=BUILT_AT)

    write_manifest(manifest, data_dir)

    assert read_manifest(data_dir) == manifest
    assert sorted(p.name for p in data_dir.glob("manifest*")) == [MANIFEST_FILENAME]


def test_read_returns_none_when_there_is_no_manifest(tmp_path: Path):
    assert read_manifest(tmp_path) is None


def test_read_raises_a_readable_error_for_an_invalid_manifest(tmp_path: Path):
    (tmp_path / MANIFEST_FILENAME).write_text('{"seasons": "nope"}')

    with pytest.raises(ValueError, match=MANIFEST_FILENAME):
        read_manifest(tmp_path)


def test_the_fixture_manifest_used_by_the_frontend_tests_is_valid():
    path = Path(__file__).parent / "eval" / "manifest.fixture.json"

    manifest = Manifest.model_validate_json(path.read_text())

    assert [s.season for s in manifest.seasons][-1] == 2026
    assert manifest.data_through == "2026 week 9"


def test_manifest_schema_version_is_recorded():
    assert Manifest(built_at="x", nflreadpy_version="1", seasons=[]).schema_version == 1
