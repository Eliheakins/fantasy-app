"""Outcome of each `make refresh` step, appended to the `refresh_runs` table.

`run_stage` runs a stage module as `python -m` would and records ok or failed. A stage that
fails soft (catches its error so later stages still run) calls `note_soft_failure`, which
turns that run into a failed row while the exit code stays zero.
"""

import runpy
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from fantasy import store

TABLE = "refresh_runs"
MAX_ERROR_CHARS = 300

_soft_failures: list[str] = []


def note_soft_failure(error: str) -> None:
    """Called where a stage swallows an error: the current run is recorded as failed."""
    _soft_failures.append(error)


def record_run(
    stage: str,
    status: str,
    error: str | None,
    data_dir: Path | None = None,
    now: datetime | None = None,
) -> None:
    finished = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    new = pl.DataFrame(
        [
            {
                "stage": stage,
                "finished_at": finished,
                "status": status,
                "error": error and error[:MAX_ERROR_CHARS],
            }
        ],
        schema=store.SCHEMAS[TABLE],
    )
    # read, append, rewrite: a row can be lost if two refreshes overlap (accepted)
    try:
        old = store.read_table(TABLE, "derived", data_dir)
    except FileNotFoundError:
        old = new.clear()
    store.write_table(TABLE, pl.concat([old, new]), "derived", data_dir)


def latest_runs(data_dir: Path | None = None) -> pl.DataFrame:
    """The newest row of each stage (finished_at is one ISO format in UTC, so it sorts)."""
    try:
        table = store.read_table(TABLE, "derived", data_dir)
    except FileNotFoundError:
        return pl.DataFrame(schema=store.SCHEMAS[TABLE])
    return table.sort("finished_at").group_by("stage", maintain_order=True).last().sort("stage")


def _record(stage: str, status: str, error: str | None, data_dir: Path | None) -> None:
    try:
        record_run(stage, status, error, data_dir)
    except Exception as err:  # a bookkeeping failure must not fail the refresh step itself
        print(f"warning: could not record the {stage} run: {err!r}", file=sys.stderr)


def run_stage(
    stage: str, module: str, args: Sequence[str] = (), data_dir: Path | None = None
) -> int:
    """Run `module` as __main__ with `args`, record the outcome and return its exit code."""
    _soft_failures.clear()  # per run; the list is also emptied after recording below
    saved_argv = sys.argv
    sys.argv = [module, *args]
    code: int | str | None = 0
    try:
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    except SystemExit as stop:
        code = stop.code
    except BaseException as err:
        _record(stage, "failed", repr(err), data_dir)
        raise
    finally:
        sys.argv = saved_argv
    if isinstance(code, str):
        print(code, file=sys.stderr)
    exit_code = code if isinstance(code, int) else (0 if code is None else 1)
    if exit_code:
        _record(stage, "failed", f"exit code {exit_code}", data_dir)
    elif _soft_failures:
        _record(stage, "failed", "; ".join(_soft_failures), data_dir)
    else:
        _record(stage, "ok", None, data_dir)
    _soft_failures.clear()
    return exit_code
