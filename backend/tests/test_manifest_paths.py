from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.manifest import FileEntry, JsonFileEntry, SeasonEntry


@pytest.mark.parametrize("path", ["nfl_pbp_2026.parquet", "player_game.parquet", "a-b_c.1.parquet"])
def test_plain_parquet_file_names_are_accepted(path: str):
    assert FileEntry(path=path, rows=1).path == path


@pytest.mark.parametrize(
    "path",
    [
        "../secret.parquet",
        "/etc/passwd.parquet",
        "//evil.example/x.parquet",
        "sub/dir.parquet",
        "https://evil.example/x.parquet",
        "file.txt",
        "",
    ],
)
def test_paths_that_could_escape_the_data_folder_are_rejected(path: str):
    with pytest.raises(ValidationError):
        FileEntry(path=path, rows=1)


def test_season_entries_enforce_the_same_rule():
    with pytest.raises(ValidationError):
        SeasonEntry(season=2026, path="../x.parquet", rows=1, max_week=1, has_participation=True)


@pytest.mark.parametrize("path", ["players.json", "a-b_c.1.json"])
def test_plain_json_file_names_are_accepted_for_json_entries(path: str):
    assert JsonFileEntry(path=path, rows=1).path == path


@pytest.mark.parametrize(
    "path",
    [
        "../players.json",
        "/players.json",
        "sub/players.json",
        "https://x/players.json",
        "p.parquet",
        "",
    ],
)
def test_json_entries_reject_paths_that_could_escape_the_data_folder(path: str):
    with pytest.raises(ValidationError):
        JsonFileEntry(path=path, rows=1)
