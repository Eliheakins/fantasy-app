"""Helpers that build a tiny parquet store in a temporary directory."""

from pathlib import Path

import polars as pl

from fantasy import store

RAW = {
    "leagues",
    "league_teams",
    "rosters",
    "matchups",
    "matchup_players",
    "sleeper_players",
    "nfl_injuries",
    "nfl_schedules",
}


def write_rows(tmp_path: Path, name: str, rows: list[dict] | None = None) -> None:
    """Write a table from dict rows; columns a row leaves out are null, no rows is empty."""
    schema = store.SCHEMAS[name]
    blank = dict.fromkeys(schema)
    df = pl.DataFrame([{**blank, **r} for r in rows or []], schema=schema)
    store.write_table(name, df, "raw" if name in RAW else "derived", tmp_path)
