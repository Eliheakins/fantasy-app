from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from pydantic import ValidationError

from pipeline.players import PLAYERS_FILENAME, build_players, write_players_file
from schemas.players import PlayersFile


def _index() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "gsis_id": ["00-0033873", " 00-0030506 ", None, "00-0000001", "00-0000002"],
            "full_name": ["Patrick Mahomes", "Travis Kelce", "No Id", None, "  "],
            "position": ["QB", "TE", "WR", "RB", "K"],
            "team": ["KC", "KC", "NYJ", "DEN", None],
            "headshot_url": ["https://x/p.png", None, None, None, None],
            "birth_date": [date(1995, 9, 17), None, None, None, None],
            "years_exp": [8, 11, None, None, None],
        },
        schema_overrides={"years_exp": pl.Int32},
    )


def test_players_keep_only_rows_with_an_id_and_a_name_and_count_the_rest():
    players, skipped = build_players(_index())

    assert [p.full_name for p in players] == ["Patrick Mahomes", "Travis Kelce"]
    assert skipped == 3


def test_a_player_carries_the_fields_the_app_shows():
    players, _ = build_players(_index())

    assert players[0].model_dump() == {
        "gsis_id": "00-0033873",
        "full_name": "Patrick Mahomes",
        "position": "QB",
        "team": "KC",
        "headshot_url": "https://x/p.png",
        "birth_date": "1995-09-17",
        "years_exp": 8,
    }


def test_ids_and_names_are_trimmed_and_missing_optional_values_are_null():
    players, _ = build_players(_index())

    assert players[1].gsis_id == "00-0030506"
    assert players[1].headshot_url is None
    assert players[1].birth_date is None


def test_an_index_without_the_optional_columns_still_builds():
    players, skipped = build_players(pl.DataFrame({"gsis_id": ["a"], "full_name": ["A B"]}))

    assert [p.team for p in players] == [None]
    assert skipped == 0


def test_an_index_without_ids_or_names_is_an_error_not_an_empty_file():
    with pytest.raises(ValueError, match="gsis_id"):
        build_players(pl.DataFrame({"full_name": ["A B"]}))


def test_the_file_is_written_atomically_and_reads_back(tmp_path: Path):
    _index().write_parquet(tmp_path / "player_index.parquet")

    entry, skipped = write_players_file(tmp_path)

    assert entry.path == PLAYERS_FILENAME
    assert entry.rows == 2
    assert skipped == 3
    loaded = PlayersFile.model_validate_json((tmp_path / PLAYERS_FILENAME).read_text())
    assert [p.gsis_id for p in loaded.players] == ["00-0033873", "00-0030506"]
    assert list(tmp_path.glob("*.tmp")) == []


def test_without_a_player_index_there_is_nothing_to_write(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="player_index"):
        write_players_file(tmp_path)


def test_the_players_schema_rejects_empty_ids_and_unknown_versions():
    with pytest.raises(ValidationError):
        PlayersFile.model_validate(
            {"schema_version": 1, "players": [{"gsis_id": "", "full_name": "A"}]}
        )
    with pytest.raises(ValidationError):
        PlayersFile.model_validate({"schema_version": 2, "players": []})
