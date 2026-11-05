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


def _two_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(store.SCHEMAS, "demo_a", {"x": pl.Int64})
    monkeypatch.setitem(store.SCHEMAS, "demo_b", {"x": pl.Int64})


def test_write_tables_replaces_every_table_and_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _two_tables(monkeypatch)
    store.write_tables({"demo_a": pl.DataFrame({"x": [1]})}, data_dir=tmp_path)

    store.write_tables(
        {"demo_a": pl.DataFrame({"x": [2]}), "demo_b": pl.DataFrame({"x": [3]})},
        data_dir=tmp_path,
    )

    assert store.read_table("demo_a", data_dir=tmp_path)["x"].to_list() == [2]
    assert store.read_table("demo_b", data_dir=tmp_path)["x"].to_list() == [3]
    assert not list(tmp_path.rglob("*.tmp"))


def test_write_tables_keeps_the_old_files_when_a_later_table_fails_to_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _two_tables(monkeypatch)
    store.write_tables({"demo_a": pl.DataFrame({"x": [1]})}, data_dir=tmp_path)
    real_write = pl.DataFrame.write_parquet
    calls: list[object] = []

    def flaky(self: pl.DataFrame, file: object, *args: object, **kwargs: object) -> None:
        calls.append(file)
        if len(calls) == 2:
            raise OSError("disk full")
        real_write(self, file, *args, **kwargs)  # type: ignore[arg-type]

    with monkeypatch.context() as patch, pytest.raises(OSError, match="disk full"):
        patch.setattr(pl.DataFrame, "write_parquet", flaky)
        store.write_tables(
            {"demo_a": pl.DataFrame({"x": [2]}), "demo_b": pl.DataFrame({"x": [3]})},
            data_dir=tmp_path,
        )

    assert store.read_table("demo_a", data_dir=tmp_path)["x"].to_list() == [1]
    assert not store.table_path("demo_b", data_dir=tmp_path).exists()
    assert not list(tmp_path.rglob("*.tmp"))
