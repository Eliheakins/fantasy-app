"""The one place player stats and rosters are fetched from nflverse, for both halves."""

from __future__ import annotations

import nflreadpy as nfl
import polars as pl


def player_stats(seasons: list[int]) -> pl.DataFrame:
    """One row per player and week (nflreadpy's default level, passed explicitly)."""
    return nfl.load_player_stats(seasons, summary_level="week")


def rosters(seasons: list[int]) -> pl.DataFrame:
    """One row per player and season."""
    return nfl.load_rosters(seasons)


def rosters_weekly(seasons: list[int]) -> pl.DataFrame:
    """One row per player and week."""
    return nfl.load_rosters_weekly(seasons)
