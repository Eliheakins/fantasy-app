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
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from fantasy import store

LOCK_NAME = ".pipeline.lock"
HELD_ENV = "FANTASY_PIPELINE_LOCK_HELD"
RUN_ID_ENV = "FANTASY_RUN_ID"
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


def hold_and_run(argv: Sequence[str], data_dir: Path | None = None) -> int:
    """Run `argv` while holding the lock; the child sees HELD_ENV and one shared run id."""
    with pipeline_lock(data_dir):
        env = {
            **os.environ,
            HELD_ENV: "1",
            RUN_ID_ENV: os.environ.get(RUN_ID_ENV) or new_run_id(),
        }
        return subprocess.run(list(argv), env=env, check=False).returncode


def main(argv: Sequence[str]) -> int:
    if not argv:
        print("usage: python -m fantasy._lock <command> [args...]", file=sys.stderr)
        return 2
    return hold_and_run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
