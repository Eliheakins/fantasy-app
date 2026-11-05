"""The one owner of "which season is it" and of the first-season constants."""

from __future__ import annotations

import tomllib
from pathlib import Path

from nflreadpy.utils_date import get_current_season

from nfl_stat.core.config import REPO_ROOT

CONFIG_PATH = REPO_ROOT / "config.toml"

# Three different concepts, not one value:
FANTASY_FIRST_SEASON = 2018  # first season the fantasy projections train on and score from
STAT_SHARDS_FIRST_SEASON = 2021  # first season the stat app builds shards for
NFLVERSE_PBP_FIRST_SEASON = 1999  # earliest season nflverse publishes play-by-play


def current_season(config_path: Path = CONFIG_PATH) -> int:
    """The season both halves work on: `season` in config.toml if set, else nflreadpy's clock.

    The pin is bumped by hand, so in the off-season (nflreadpy rolls over at the Thursday after
    Labor Day) it stays on the finished season until it is edited. In-season the two agree.
    """
    pinned = tomllib.loads(config_path.read_text()).get("season") if config_path.exists() else None
    if pinned is None:
        return get_current_season()
    if not isinstance(pinned, int) or isinstance(pinned, bool):
        raise ValueError(f"{config_path}: season must be a year, not {pinned!r}")
    return pinned


def roster_season() -> int:
    """nflverse's roster-year clock (rolls over March 15), for data availability checks."""
    return get_current_season(roster=True)
