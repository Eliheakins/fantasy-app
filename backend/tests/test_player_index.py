from __future__ import annotations

from pathlib import Path

import polars as pl

from pipeline.players import merge_player_index, read_player_index


def _index(rows: list[tuple[str | None, str, str, int | None]]) -> pl.DataFrame:
    """(gsis_id, name, team, season) rows."""
    return pl.DataFrame(
        {
            "gsis_id": [r[0] for r in rows],
            "full_name": [r[1] for r in rows],
            "team": [r[2] for r in rows],
            "season": [r[3] for r in rows],
        },
        schema={
            "gsis_id": pl.String,
            "full_name": pl.String,
            "team": pl.String,
            "season": pl.Int32,
        },
    )


def _by_id(df: pl.DataFrame) -> dict[str, tuple[str, int | None]]:
    return {r["gsis_id"]: (r["team"], r["season"]) for r in df.to_dicts()}


def test_a_first_build_is_kept_as_it_is():
    new = _index([("a", "A A", "KC", 2026)])

    assert _by_id(merge_player_index(None, new)) == {"a": ("KC", 2026)}


def test_players_missing_from_a_partial_rebuild_stay_in_the_index():
    existing = _index([("brady", "Tom Brady", "TB", 2022), ("a", "A A", "KC", 2025)])
    new = _index([("a", "A A", "KC", 2026)])

    merged = _by_id(merge_player_index(existing, new))

    assert set(merged) == {"brady", "a"}


def test_the_latest_season_wins_for_a_player_in_both():
    existing = _index([("a", "A A", "DEN", 2025)])
    new = _index([("a", "A A", "LV", 2026)])

    assert _by_id(merge_player_index(existing, new)) == {"a": ("LV", 2026)}


def test_rebuilding_an_older_season_does_not_overwrite_a_newer_row():
    existing = _index([("a", "A A", "LV", 2026)])
    new = _index([("a", "A A", "DEN", 2021)])

    assert _by_id(merge_player_index(existing, new)) == {"a": ("LV", 2026)}


def test_an_index_built_before_the_season_column_existed_is_replaced_by_new_rows():
    old_format = pl.DataFrame(
        {"gsis_id": ["a", "b"], "full_name": ["A A", "B B"], "team": ["DEN", "KC"]}
    )
    new = _index([("a", "A A", "LV", 2026)])

    merged = _by_id(merge_player_index(old_format, new))

    assert merged == {"a": ("LV", 2026), "b": ("KC", None)}


def test_rows_without_an_id_are_dropped():
    new = _index([(None, "No Id", "KC", 2026), ("a", "A A", "KC", 2026)])

    assert set(_by_id(merge_player_index(None, new))) == {"a"}


def test_a_missing_or_corrupt_existing_index_counts_as_no_index(tmp_path: Path):
    assert read_player_index(tmp_path / "player_index.parquet") is None

    (tmp_path / "player_index.parquet").write_bytes(b"not a parquet file")

    assert read_player_index(tmp_path / "player_index.parquet") is None


def test_a_readable_existing_index_is_returned(tmp_path: Path):
    _index([("a", "A A", "KC", 2026)]).write_parquet(tmp_path / "player_index.parquet")

    loaded = read_player_index(tmp_path / "player_index.parquet")

    assert loaded is not None and loaded.height == 1


def test_columns_with_different_integer_widths_still_merge():
    existing = _index([("b", "B B", "KC", 2025)]).with_columns(pl.col("season").cast(pl.Int64))
    new = _index([("a", "A A", "KC", 2026)])

    assert set(_by_id(merge_player_index(existing, new))) == {"a", "b"}
