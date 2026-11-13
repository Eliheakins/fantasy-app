from pathlib import Path

import polars as pl

from fantasy import archive_tables, store


def _seed(data_dir: Path) -> None:
    """An existing archive: one other table, as on a server that already ran."""
    name = "proj_snapshots"
    store.write_table(name, pl.DataFrame(schema=store.SCHEMAS[name]), "archive", data_dir)


def test_writes_a_missing_new_table_empty_next_to_existing_ones(tmp_path: Path) -> None:
    _seed(tmp_path)
    assert archive_tables.ensure(("market_values_history",), tmp_path) == ["market_values_history"]
    table = store.read_archive("market_values_history", tmp_path)
    assert table.height == 0
    assert dict(table.schema) == dict(store.SCHEMAS["market_values_history"])


def test_never_touches_an_existing_table(tmp_path: Path) -> None:
    _seed(tmp_path)
    name = "market_values_history"
    schema = store.SCHEMAS[name]
    row = pl.DataFrame([[None] * len(schema)], schema=schema, orient="row")
    store.write_table(name, row, "archive", tmp_path)
    assert archive_tables.ensure((name,), tmp_path) == []
    assert store.read_archive(name, tmp_path).height == 1


def test_leaves_an_empty_archive_alone(tmp_path: Path) -> None:
    """A fresh server: an empty table there would make every other archive table read as missing."""
    assert archive_tables.ensure(("market_values_history",), tmp_path) == []
    assert not store.table_path("market_values_history", "archive", tmp_path).exists()
