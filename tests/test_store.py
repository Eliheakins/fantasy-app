from pathlib import Path

import polars as pl
import pytest

from fantasy import store


@pytest.fixture(autouse=True)
def demo_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(store.SCHEMAS, "demo", {"player_id": pl.String, "points": pl.Float64})


def demo_frame() -> pl.DataFrame:
    return pl.DataFrame({"player_id": ["a", "b"], "points": [1.5, 2.5]})


def test_round_trip(tmp_path: Path) -> None:
    store.write_table("demo", demo_frame(), data_dir=tmp_path)
    assert store.read_table("demo", data_dir=tmp_path).equals(demo_frame())


def test_wrong_column_fails_loudly(tmp_path: Path) -> None:
    bad = demo_frame().rename({"points": "pts"})
    with pytest.raises(ValueError, match="columns"):
        store.write_table("demo", bad, data_dir=tmp_path)


def test_wrong_dtype_fails_loudly(tmp_path: Path) -> None:
    bad = demo_frame().with_columns(pl.col("points").cast(pl.Int64))
    with pytest.raises(ValueError, match="dtypes"):
        store.write_table("demo", bad, data_dir=tmp_path)


def test_unregistered_table_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no registered schema"):
        store.write_table("nope", demo_frame(), data_dir=tmp_path)


def test_failed_write_leaves_no_temp_file(tmp_path: Path) -> None:
    bad = demo_frame().rename({"points": "pts"})
    with pytest.raises(ValueError):
        store.write_table("demo", bad, data_dir=tmp_path)
    assert not list(tmp_path.rglob("*.tmp"))
    assert not list(tmp_path.rglob("*.parquet"))


def test_bad_table_name_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bad table name"):
        store.table_path("../x", data_dir=tmp_path)


def test_duckdb_views_read_the_files(tmp_path: Path) -> None:
    store.write_table("demo", demo_frame(), data_dir=tmp_path)
    con = store.connect(tmp_path)
    assert con.execute("SELECT sum(points) FROM demo").fetchone() == (4.0,)
