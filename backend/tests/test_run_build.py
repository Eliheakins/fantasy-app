from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from pipeline import cli
from pipeline.player_game import PLAYER_GAME_COLUMNS, write_player_game
from schemas.manifest import read_manifest


def _shard(season: int) -> pl.DataFrame:
    return pl.DataFrame(
        {"season": [season], "week": [1], "season_type": ["REG"], "defenders_in_box": [6]},
        schema_overrides={"defenders_in_box": pl.Int32},
    )


def _games(season: int) -> pl.DataFrame:
    row: dict[str, list] = {c: [0] for c in PLAYER_GAME_COLUMNS}
    row.update(
        gsis_id=["g1"],
        full_name=["A B"],
        position=["QB"],
        team=["KC"],
        opponent_team=["DET"],
        season=[season],
        week=[1],
        season_type=["REG"],
        passing_epa=[None],
        rushing_epa=[None],
        receiving_epa=[None],
    )
    epa = {c: pl.Float64 for c in ("passing_epa", "rushing_epa", "receiving_epa")}
    return pl.DataFrame(row, schema_overrides=epa)


@pytest.fixture
def stubbed_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "build_stitched_for_year", _shard)
    monkeypatch.setattr(
        cli,
        "create_player_index",
        lambda data_dir, years: pl.DataFrame({"gsis_id": ["g1"]}).write_parquet(
            data_dir / "player_index.parquet"
        ),
    )
    monkeypatch.setattr(
        cli, "build_player_game", lambda years: pl.concat([_games(y) for y in years])
    )


def test_a_partial_build_keeps_the_other_seasons_in_the_player_game_table(
    tmp_path: Path, stubbed_network: None
):
    write_player_game(pl.concat([_games(2021), _games(2022)]), tmp_path)

    cli.run_build(tmp_path, [2026])

    seasons = pl.read_parquet(tmp_path / "player_game.parquet")["season"].to_list()
    assert seasons == [2021, 2022, 2026]


def test_rebuilding_a_season_replaces_its_rows_instead_of_duplicating_them(
    tmp_path: Path, stubbed_network: None
):
    cli.run_build(tmp_path, [2025, 2026])
    cli.run_build(tmp_path, [2026])

    assert pl.read_parquet(tmp_path / "player_game.parquet")["season"].to_list() == [2025, 2026]


def test_the_manifest_describes_the_shards_even_if_the_player_game_build_fails(
    tmp_path: Path, stubbed_network: None, monkeypatch: pytest.MonkeyPatch
):
    def boom(years: list[int]) -> pl.DataFrame:
        raise RuntimeError("network down")

    monkeypatch.setattr(cli, "build_player_game", boom)

    with pytest.raises(RuntimeError, match="network down"):
        cli.run_build(tmp_path, [2026])

    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert [s.season for s in manifest.seasons] == [2026]


def test_a_finished_build_leaves_no_temporary_files(tmp_path: Path, stubbed_network: None):
    cli.run_build(tmp_path, [2025, 2026])

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "manifest.json",
        "nfl_pbp_2025.parquet",
        "nfl_pbp_2026.parquet",
        "player_game.parquet",
        "player_index.parquet",
    ]


def test_the_manifest_lists_the_player_game_table_after_a_full_build(
    tmp_path: Path, stubbed_network: None
):
    cli.run_build(tmp_path, [2026])

    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.player_game is not None
    assert manifest.player_game.rows == 1
