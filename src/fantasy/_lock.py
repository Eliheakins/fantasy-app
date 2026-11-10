"""One lock for every process that rewrites the data tables: a refresh, the live score tick and the
manual refresh button. A kernel file lock, so a crashed holder never leaves it stuck.

`pipeline_lock` is not reentrant: a second acquire in the same process waits for the first.
`hold_and_run` is for `make refresh`: it holds the lock for the whole run and marks the stages it
starts, which then skip their own short locks instead of waiting on their parent.

Run: uv run python -m fantasy._lock <command> [args...]
"""

import fcntl
import os
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from fantasy import store

LOCK_NAME = ".pipeline.lock"
HELD_ENV = "FANTASY_PIPELINE_LOCK_HELD"
RUN_ID_ENV = store.RUN_ID_ENV
NOT_PUBLISHED_EXIT = 75  # a required stage failed and nothing was published: systemd retries
PUBLISHED_EXITS = (0, 1)  # 1: an optional stage failed but the data was published
# A retry of a failed run keeps its run id (so the archive appends once per run) for this long
RETRY_FILE = ".retry_run_id"
RETRY_WINDOW_S = 3 * 3600
RUN_ID_FORMAT = "%Y%m%dT%H%M%SZ"  # UTC, so ids sort in the order the runs started


class PipelineBusy(RuntimeError):
    """Another process holds the pipeline lock."""


def new_run_id() -> str:
    return datetime.now(UTC).strftime(RUN_ID_FORMAT)


@contextmanager
def pipeline_lock(data_dir: Path | None = None, blocking: bool = True) -> Iterator[None]:
    """Hold the lock for the block. With `blocking=False`, raise PipelineBusy instead of waiting."""
    if os.environ.get(HELD_ENV) == "1":  # a parent process holds it for this whole run
        yield
        return
    path = store.resolve(data_dir) / LOCK_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:  # closing the file releases the lock
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as err:
            raise PipelineBusy("another refresh is running") from err
        yield


def _run_id_to_use(retry_file: Path) -> str:
    """The id of the last run that did not finish published, if recent (a systemd retry or a rerun
    soon after), else a new one."""
    try:
        if time.time() - retry_file.stat().st_mtime < RETRY_WINDOW_S:
            return retry_file.read_text().strip() or new_run_id()
    except FileNotFoundError:
        pass
    return new_run_id()


def hold_and_run(argv: Sequence[str], data_dir: Path | None = None) -> int:
    """Run `argv` while holding the lock; the child sees HELD_ENV and one shared run id.

    The id is written to RETRY_FILE before the run and removed once the run published, so a run
    that failed, crashed or timed out is retried under the same id."""
    with pipeline_lock(data_dir):
        retry_file = store.resolve(data_dir) / RETRY_FILE
        run_id = os.environ.get(RUN_ID_ENV) or _run_id_to_use(retry_file)
        retry_file.write_text(run_id)
        env = {**os.environ, HELD_ENV: "1", RUN_ID_ENV: run_id}
        code = subprocess.run(list(argv), env=env, check=False).returncode
        if code in PUBLISHED_EXITS:
            retry_file.unlink(missing_ok=True)
        return code


def main(argv: Sequence[str]) -> int:
    if not argv:
        print("usage: python -m fantasy._lock <command> [args...]", file=sys.stderr)
        return 2
    return hold_and_run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
