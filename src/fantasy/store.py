"""Parquet store: atomic writes, schema checks, in-memory DuckDB views.

Parquet files under data/ are the source of truth. Each table has one file at
data/<area>/<name>.parquet, where area is raw, derived or archive. Stages register their
tables in SCHEMAS; reads and writes assert the columns and dtypes match.
"""

import os
import re
from pathlib import Path

import duckdb
import polars as pl

from fantasy.config import ROOT

DATA_DIR = ROOT / "data"
AREAS = ("raw", "derived", "archive")
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

# table name -> {column: dtype}. Stages add their tables here as they are built.
SCHEMAS: dict[str, dict[str, pl.DataType | type[pl.DataType]]] = {}


def table_path(name: str, area: str = "derived", data_dir: Path = DATA_DIR) -> Path:
    if not _NAME.match(name):
        raise ValueError(f"bad table name {name!r}: use lowercase letters, digits, underscores")
    if area not in AREAS:
        raise ValueError(f"bad area {area!r}: expected one of {AREAS}")
    return data_dir / area / f"{name}.parquet"


def check_schema(name: str, df: pl.DataFrame) -> None:
    if name not in SCHEMAS:
        raise ValueError(f"table {name!r} has no registered schema in store.SCHEMAS")
    expected = SCHEMAS[name]
    actual = dict(df.schema)
    if list(actual) != list(expected):
        raise ValueError(f"{name}: columns {list(actual)} != expected {list(expected)}")
    wrong = {c: (actual[c], t) for c, t in expected.items() if actual[c] != t}
    if wrong:
        raise ValueError(f"{name}: wrong dtypes {wrong} (actual, expected)")


def write_table(
    name: str, df: pl.DataFrame, area: str = "derived", data_dir: Path = DATA_DIR
) -> Path:
    check_schema(name, df)
    path = table_path(name, area, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    try:
        df.write_parquet(tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def read_table(name: str, area: str = "derived", data_dir: Path = DATA_DIR) -> pl.DataFrame:
    path = table_path(name, area, data_dir)
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run the stage that writes {name!r}")
    df = pl.read_parquet(path)
    check_schema(name, df)
    return df


def connect(data_dir: Path = DATA_DIR) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with one view per parquet file, named after the table."""
    con = duckdb.connect(":memory:")
    seen: dict[str, Path] = {}
    for area in AREAS:
        for path in sorted((data_dir / area).glob("*.parquet")):
            if path.stem in seen:
                raise ValueError(f"table {path.stem!r} is in two areas: {seen[path.stem]}, {path}")
            seen[path.stem] = path
            escaped = str(path).replace("'", "''")
            con.execute(f"CREATE VIEW \"{path.stem}\" AS SELECT * FROM read_parquet('{escaped}')")
    return con
