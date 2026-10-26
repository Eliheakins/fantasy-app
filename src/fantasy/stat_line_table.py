"""The `stat_line` table: q = P(stat line | played) for each game the learned projection covers.

`learn` writes it after `proj_learned` when `stat_line_model` is on (the projection then carries q)
and deletes it when the switch is off. Readers key on the table, not on the config, so flipping the
switch without rerunning `learn` never divides a projection without q by q. Kept apart from
`stages/stat_line.py` so the simulation does not import the classifier.
"""

import warnings
from pathlib import Path

import polars as pl

from fantasy import store

NAME = "stat_line"


def sync(chance: pl.DataFrame | None, data_dir: Path | None = None) -> None:
    """Write the table (gsis_id, season, week, q), or delete it when `chance` is None."""
    root = store.DATA_DIR if data_dir is None else data_dir
    if chance is None:
        store.table_path(NAME, "derived", root).unlink(missing_ok=True)
        return
    store.write_table(NAME, chance.select(*store.SCHEMAS[NAME]), "derived", root)


def stored(data_dir: Path | None = None) -> pl.DataFrame | None:
    """The table when the learned projections are in use and carry q: it exists and is at least
    as new as `proj_learned`. A table older than `proj_learned` belongs to an earlier run: warned
    about and ignored."""
    root = store.DATA_DIR if data_dir is None else data_dir
    path = store.table_path(NAME, "derived", root)
    if store.projection_name(root) != "proj_learned" or not path.exists():
        return None
    learned = store.table_path("proj_learned", "derived", root)
    if path.stat().st_mtime_ns < learned.stat().st_mtime_ns:
        warnings.warn(
            "the stat_line table is older than proj_learned; ignored (rerun learn)", stacklevel=2
        )
        return None
    return store.read_table(NAME, "derived", root)


def _with_q(frame: pl.DataFrame, chance: pl.DataFrame, on: list[str]) -> pl.DataFrame:
    joined = frame.join(chance.select(*on, "q"), on=on, how="left")
    missing = int(joined["q"].null_count())
    if missing:
        raise ValueError(f"{missing} projection rows have no stat-line chance")
    return joined


def scale(frame: pl.DataFrame, chance: pl.DataFrame, on: list[str]) -> pl.DataFrame:
    """`frame` with its projection multiplied by q (joined on `on`); every row must have one."""
    return _with_q(frame, chance, on).with_columns(pl.col("projection") * pl.col("q")).drop("q")


def divide(frame: pl.DataFrame, chance: pl.DataFrame, on: list[str]) -> pl.DataFrame:
    """`frame` with q taken back out of its projection: E[points | stat line]."""
    return _with_q(frame, chance, on).with_columns(pl.col("projection") / pl.col("q")).drop("q")
