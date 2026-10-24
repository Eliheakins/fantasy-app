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


def test_write_tables_replaces_nothing_when_one_table_fails_its_schema(
    tmp_path,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    monkeypatch.setattr(
        store,
        "table_path",
        lambda name, area="derived", data_dir=None: tmp_path / f"{name}.parquet",
    )
    good = pl.DataFrame({"x": [1]})
    monkeypatch.setitem(store.SCHEMAS, "t_good", {"x": pl.Int64})
    monkeypatch.setitem(store.SCHEMAS, "t_bad", {"y": pl.Int64})
    with pytest.raises(ValueError):
        store.write_tables({"t_good": good, "t_bad": good})
    assert list(tmp_path.iterdir()) == []
