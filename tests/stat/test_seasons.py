from pathlib import Path

import pytest

from fantasy.config import load_config
from nfl_stat.core import seasons
from nfl_stat.core.seasons import (
    FANTASY_FIRST_SEASON,
    NFLVERSE_PBP_FIRST_SEASON,
    STAT_SHARDS_FIRST_SEASON,
    current_season,
)


def test_the_pinned_season_in_config_wins_over_the_nflverse_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(seasons, "get_current_season", lambda: 2030)
    config = tmp_path / "config.toml"
    config.write_text("season = 2026\n")

    assert current_season(config) == 2026


def test_without_a_pin_the_nflverse_clock_decides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(seasons, "get_current_season", lambda: 2030)
    config = tmp_path / "config.toml"
    config.write_text("n_sims = 5\n")

    assert current_season(config) == 2030
    assert current_season(tmp_path / "missing.toml") == 2030


def test_a_pin_that_is_not_a_year_is_rejected(tmp_path: Path):
    config = tmp_path / "config.toml"
    config.write_text('season = "2026"\n')

    with pytest.raises(ValueError, match="season"):
        current_season(config)


def test_fantasy_config_season_comes_from_the_shared_function():
    assert load_config().season == current_season()


def test_first_season_constants_keep_their_values():
    assert (FANTASY_FIRST_SEASON, STAT_SHARDS_FIRST_SEASON, NFLVERSE_PBP_FIRST_SEASON) == (
        2018,
        2021,
        1999,
    )
