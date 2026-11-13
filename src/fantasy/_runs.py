"""Outcome of each `make refresh` step, appended to the `refresh_runs` table.

`run_stage` runs a stage module as `python -m` would and records ok or failed. A stage that
fails soft (catches its error so later stages still run) calls `note_soft_failure`, which
turns that run into a failed row while the exit code stays zero.
"""

import os
import runpy
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from fantasy import store
from fantasy._lock import RUN_ID_ENV, pipeline_lock

TABLE = "refresh_runs"
MAX_ERROR_CHARS = 300
# The pipeline sets this so a soft failure exits SOFT_FAILURE_EXIT and gets retried; a lone stage
# (make backup) leaves it unset and still exits 0. 65 is free: _lock uses 0, 1 and 75.
SOFT_EXIT_ENV = "FANTASY_SOFT_EXIT"
SOFT_FAILURE_EXIT = 65

_soft_failures: list[str] = []


def parse_utc(stamp: str) -> datetime:
    """An ISO timestamp, read as UTC when it carries no zone."""
    parsed = datetime.fromisoformat(stamp)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def note_soft_failure(error: str) -> None:
    """Called where a stage swallows an error: the current run is recorded as failed."""
    _soft_failures.append(error)


def record_run(
    stage: str,
    status: str,
    error: str | None,
    data_dir: Path | None = None,
    now: datetime | None = None,
    run_id: str | None = None,
    duration_s: float | None = None,
) -> None:
    finished = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    new = pl.DataFrame(
        [
            {
                "stage": stage,
                "finished_at": finished,
                "status": status,
                "error": error and error[:MAX_ERROR_CHARS],
                "run_id": run_id,
                "duration_s": duration_s,
            }
        ],
        schema=store.SCHEMAS[TABLE],
    )
    with pipeline_lock(data_dir):  # read, append, rewrite must not interleave with another record
        try:
            old = read_runs(data_dir)
        except FileNotFoundError:
            old = new.clear()
        store.write_table(TABLE, pl.concat([old, new]), "derived", data_dir)


def read_runs(data_dir: Path | None) -> pl.DataFrame:
    """The table, also when it was written before run_id and duration_s existed (they read null)."""
    path = store.table_path(TABLE, "derived", data_dir)
    if not path.exists():
        raise FileNotFoundError(path)
    schema = store.SCHEMAS[TABLE]
    old = pl.read_parquet(path)
    absent = [
        pl.lit(None, dtype=dtype).alias(name)
        for name, dtype in schema.items()
        if name not in old.columns
    ]
    return old.with_columns(absent).select(list(schema))


def latest_runs(data_dir: Path | None = None) -> pl.DataFrame:
    """The newest row of each stage (finished_at is one ISO format in UTC, so it sorts)."""
    try:
        table = read_runs(data_dir)
    except FileNotFoundError:
        return pl.DataFrame(schema=store.SCHEMAS[TABLE])
    return table.sort("finished_at").group_by("stage", maintain_order=True).last().sort("stage")


def _record(
    stage: str, status: str, error: str | None, data_dir: Path | None, duration_s: float
) -> None:
    try:
        run_id = (
            os.environ.get(RUN_ID_ENV) or None
        )  # set by `make refresh`, absent for a lone stage
        record_run(stage, status, error, data_dir, run_id=run_id, duration_s=duration_s)
    except Exception as err:  # noqa: BLE001 - bookkeeping must not fail the refresh step itself
        print(f"warning: could not record the {stage} run: {err!r}", file=sys.stderr)


def run_stage(
    stage: str, module: str, args: Sequence[str] = (), data_dir: Path | None = None
) -> int:
    """Run `module` as __main__ with `args`, record the outcome and return its exit code."""
    _soft_failures.clear()  # per run; the list is also emptied after recording below
    started = time.monotonic()
    saved_argv = sys.argv
    sys.argv = [module, *args]
    code: int | str | None = 0
    try:
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    except SystemExit as stop:
        code = stop.code
    except BaseException as err:
        _record(stage, "failed", repr(err), data_dir, time.monotonic() - started)
        raise
    finally:
        sys.argv = saved_argv
    if isinstance(code, str):
        print(code, file=sys.stderr)
    message = code if isinstance(code, str) else None
    exit_code = code if isinstance(code, int) else (0 if code is None else 1)
    elapsed = time.monotonic() - started
    if exit_code:
        _record(stage, "failed", message or f"exit code {exit_code}", data_dir, elapsed)
    elif _soft_failures:
        _record(stage, "failed", "; ".join(_soft_failures), data_dir, elapsed)
        exit_code = SOFT_FAILURE_EXIT if os.environ.get(SOFT_EXIT_ENV) else 0
    else:
        _record(stage, "ok", None, data_dir, elapsed)
    _soft_failures.clear()
    return exit_code
