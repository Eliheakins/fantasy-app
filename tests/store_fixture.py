"""Helpers that build a tiny parquet store and point `store.read_table` at it."""

from pathlib import Path

import polars as pl
import pytest

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


def use_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect default-directory reads (the DATA_DIR default is bound at import) to tmp_path."""
    original = store.read_table
    monkeypatch.setattr(
        store,
        "read_table",
        lambda name, area="derived", data_dir=tmp_path: original(name, area, data_dir),
    )
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
