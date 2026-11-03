from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from services.player_catalog import (
    get_player_row,
    load_player_index_from_path,
    player_dictionary,
    search_players_by_name,
)


@pytest.fixture
def index() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "gsis_id": ["1", "2", "3"],
            "full_name": ["A.J. Brown", "AJ Green", "Patrick Mahomes"],
            "position": ["WR", "WR", "QB"],
            "team": ["PHI", "CIN", "KC"],
        }
    )


def test_load_player_index_round_trips_a_parquet_file(tmp_path: Path, index: pl.DataFrame):
    path = tmp_path / "player_index.parquet"
    index.write_parquet(path)

    assert load_player_index_from_path(path).height == 3


def test_load_player_index_raises_when_file_is_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="Player index not found"):
        load_player_index_from_path(tmp_path / "nope.parquet")


def test_search_treats_the_query_as_literal_text_not_a_pattern(index: pl.DataFrame):
    assert [p.gsis_id for p in search_players_by_name(index, "a.j")] == ["1"]


def test_search_returns_nothing_for_blank_query(index: pl.DataFrame):
    assert search_players_by_name(index, "   ") == []


def test_search_respects_the_limit(index: pl.DataFrame):
    assert len(search_players_by_name(index, "a", limit=2)) == 2


def test_get_player_row_strips_whitespace_around_the_id(index: pl.DataFrame):
    player = get_player_row(index, "  3 ")

    assert player is not None
    assert player.full_name == "Patrick Mahomes"


def test_get_player_row_returns_none_for_blank_or_unknown_id(index: pl.DataFrame):
    assert get_player_row(index, "") is None
    assert get_player_row(index, "999") is None


def test_player_dictionary_works_without_position_and_team_columns():
    df = pl.DataFrame({"gsis_id": ["1", "2"], "full_name": ["Pat Mahomes", None]})

    rows = player_dictionary(df)

    assert [(r.gsis_id, r.search_key, r.position, r.team) for r in rows] == [
        ("1", "pat mahomes", None, None)
    ]
