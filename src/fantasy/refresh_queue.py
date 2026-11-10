"""Ask for a refresh without running one: a marker file that coalesces requests.

`request_refresh` appends a line to `data/refresh-requested`. On the server a systemd path unit
starts the refresh service when the file exists; the pipeline takes the file at the start of a run
(`consume`), so every request made before then is served by that one run, and a request made while
it runs starts the next. Where there is no systemd (a laptop), run `make refresh` by hand.
"""

import os
from pathlib import Path
from typing import Any

import polars as pl

from fantasy import store
from fantasy._lock import PipelineBusy, pipeline_lock
from fantasy._runs import read_runs

MARKER = "refresh-requested"
TAKEN = MARKER + ".taken"


def _marker(data_dir: Path | None) -> Path:
    return store.resolve(data_dir) / MARKER


def request_refresh(reason: str, data_dir: Path | None = None) -> None:
    """Queue a refresh. Safe from any process; small appends do not interleave."""
    path = _marker(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(" ".join(reason.split()) + "\n")


def consume(data_dir: Path | None = None) -> list[str]:
    """Take every queued reason and clear the queue. A request made during this call lands in a
    fresh marker (the file is renamed first), so none is lost."""
    path = _marker(data_dir)
    taken = path.with_name(TAKEN)
    try:
        os.replace(path, taken)
    except FileNotFoundError:
        return []
    lines = taken.read_text().splitlines()
    taken.unlink()
    return lines


def _queued(data_dir: Path | None) -> int:
    try:
        return len(_marker(data_dir).read_text().splitlines())
    except FileNotFoundError:
        return 0


def _last_run(data_dir: Path | None) -> tuple[str | None, bool | None]:
    """When the newest recorded stage finished, and whether its run had a failed stage."""
    try:
        table = read_runs(data_dir)
    except FileNotFoundError:
        return None, None
    if table.is_empty():
        return None, None
    newest = table.sort("finished_at").row(-1, named=True)
    run_id = newest["run_id"]
    same_run = (
        table.filter(pl.col("run_id") == run_id)
        if run_id is not None
        else table.filter(pl.col("finished_at") == newest["finished_at"])
    )
    return str(newest["finished_at"]), bool((same_run["status"] == "failed").any())


def status(data_dir: Path | None = None) -> dict[str, Any]:
    """idle, queued (a request waits) or running (the pipeline lock is held), and the last run."""
    try:
        with pipeline_lock(data_dir, blocking=False):
            running = False
    except PipelineBusy:
        running = True
    queued = _queued(data_dir)
    finished_at, failed = _last_run(data_dir)
    return {
        "state": "running" if running else "queued" if queued else "idle",
        "queued": queued,
        "last_finished_at": finished_at,
        "last_run_failed": failed,
    }


RECENT_RUNS = 10


def recent_runs(data_dir: Path | None = None, limit: int = RECENT_RUNS) -> list[dict[str, Any]]:
    """The newest runs, newest first: stages, failed stages and total seconds. A stage run on its
    own (no run id) counts as part of "manual"."""
    try:
        table = read_runs(data_dir)
    except FileNotFoundError:
        return []
    if table.is_empty():
        return []
    runs = (
        table.with_columns(pl.col("run_id").fill_null("manual"))
        .group_by("run_id")
        .agg(
            pl.col("finished_at").max().alias("finished_at"),
            pl.len().alias("stages"),
            (pl.col("status") == "failed").sum().alias("failed"),
            pl.col("duration_s").sum().alias("seconds"),
        )
        .sort("finished_at", descending=True)
        .head(limit)
    )
    return [{**row, "seconds": round(float(row["seconds"] or 0.0), 1)} for row in runs.to_dicts()]
