"""The refresh: every stage in order, each with a timeout, retries on network stages, and a rule for
what a failure does.

A required stage that fails stops the run: the stages after it are recorded as skipped, because they
would compute from half-updated inputs. An optional stage that fails is recorded and the run goes
on. Either way the run ends through `refresh_report`, which exits 1 when any stage failed, so the
log and the service show it.

`make refresh` runs this inside `python -m fantasy._lock`, which holds the pipeline lock for the
whole run. Each stage still goes through `run_recorded`, which records its own outcome.

Run: uv run python -m fantasy.pipeline
"""

import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fantasy import refresh_queue, releases, store
from fantasy._lock import NOT_PUBLISHED_EXIT, RUN_ID_ENV, new_run_id
from fantasy._runs import SOFT_EXIT_ENV, SOFT_FAILURE_EXIT, read_runs, record_run
from fantasy._runs import TABLE as RUNS_TABLE
from fantasy.stages import refresh_report

# The whole refresh took about 95 s on the Mac; a hung download must not hold the lock for long.
STAGE_TIMEOUT_S = 600.0
RUN_TIMEOUT_S = 20 * 60.0
NETWORK_RETRIES = 2
RETRY_BACKOFF_S = 30.0
# NOT_PUBLISHED_EXIT (EX_TEMPFAIL, in _lock): a required stage failed and nothing was published.
# The server's service retries on this code only; exit 1 (an optional stage failed, the data was
# published) is not retried, because the run is done. A retry keeps the run id (_lock), so
# store.with_archive replaces the failed run's archive rows instead of adding to them.


@dataclass(frozen=True)
class Stage:
    name: str
    module: str
    required: bool = True  # a failure stops the run
    network: bool = False  # a failure is retried
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class Outcome:
    ok: bool
    error: str | None = None
    soft: bool = False  # the stage recorded a soft failure itself: retry it, then let the run go on


Runner = Callable[[Stage], Outcome]

# Order is the dependency order. The optional stages are the ones the simulation skips, without
# error, when their table is missing (see src/fantasy/stages/CLAUDE.md).
STAGES: tuple[Stage, ...] = (
    Stage("backup", "fantasy.stages.backup"),
    Stage("sync_sleeper", "fantasy.stages.sync_sleeper", network=True),
    Stage("news_archive", "fantasy.stages.news_archive", required=False),
    Stage("sleeper_projections", "fantasy.stages.sleeper_projections", False, True),
    Stage("outside_projections", "fantasy.stages.outside_projections", False, True),
    Stage("ingest_nfl", "fantasy.stages.ingest_nfl", network=True),
    Stage("crosswalk", "fantasy.stages.crosswalk"),
    Stage("score", "fantasy.stages.score"),
    Stage("prop_points", "fantasy.stages.prop_points", required=False),
    Stage("streaming", "fantasy.stages.streaming", required=False),
    Stage("project", "fantasy.stages.project"),
    Stage("learn", "fantasy.stages.learn"),
    Stage("availability", "fantasy.stages.availability", required=False),
    Stage("distributions", "fantasy.stages.distributions"),
    Stage("injuries", "fantasy.stages.injuries", required=False),
    Stage("outlook", "fantasy.stages.outlook", required=False),
    Stage("simulate", "fantasy.stages.simulate"),
    Stage("digest", "fantasy.stages.digest", required=False),
    Stage("market_values", "fantasy.stages.market_values", False, True),
    Stage("stat_data", "nfl_stat.pipeline.cli", False, True, ("--refresh",)),
)


def argv_for(stage: Stage) -> list[str]:
    run_recorded = "fantasy.stages.run_recorded"
    return [sys.executable, "-m", run_recorded, stage.name, stage.module, *stage.args]


def run_command(argv: Sequence[str], timeout: float = STAGE_TIMEOUT_S) -> Outcome:
    """Run one command; a timeout kills it and counts as a failure."""
    try:
        done = subprocess.run(
            list(argv), timeout=timeout, check=False, env={**os.environ, SOFT_EXIT_ENV: "1"}
        )
    except subprocess.TimeoutExpired:
        return Outcome(False, f"timed out after {timeout:g}s")
    if done.returncode == 0:
        return Outcome(True)
    if done.returncode == SOFT_FAILURE_EXIT:
        return Outcome(False, "soft failure", soft=True)
    return Outcome(False, f"exit code {done.returncode}")


def _attempt(stage: Stage, runner: Runner, sleep: Callable[[float], None]) -> Outcome:
    outcome = runner(stage)
    for _ in range(NETWORK_RETRIES if stage.network else 0):
        if outcome.ok:
            break
        sleep(RETRY_BACKOFF_S)
        outcome = runner(stage)
    return outcome


def _child_recorded(stage: Stage, since: str, data_dir: Path | None) -> bool:
    """Whether run_recorded already wrote a failed row for this stage since `since`."""
    try:
        table = read_runs(data_dir)
    except FileNotFoundError:
        return False
    mine = table.filter((table["stage"] == stage.name) & (table["finished_at"] >= since))
    return bool((mine["status"] == "failed").any())


def _note(
    stage: Stage,
    error: str | None,
    data_dir: Path | None,
    duration_s: float | None,
    since: str | None = None,
) -> None:
    """Record a failure the stage itself could not (killed, timed out, never started); a failure
    the child recorded keeps its own, more exact error."""
    if since and _child_recorded(stage, since, data_dir):
        return
    record_run(
        stage.name,
        "failed",
        error,
        data_dir,
        run_id=os.environ.get(RUN_ID_ENV) or None,
        duration_s=duration_s,
    )


def execute(
    stages: Sequence[Stage],
    runner: Runner,
    data_dir: Path | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    run_timeout: float = RUN_TIMEOUT_S,
) -> dict[str, str]:
    """Run the stages; returns each stage's result: ok, failed or skipped."""
    results: dict[str, str] = {}
    started = clock()
    stopped_because: str | None = None
    for stage in stages:
        if stopped_because is None and clock() - started > run_timeout:
            stopped_because = f"run exceeded {run_timeout:g}s"
        if stopped_because is not None:
            _note(stage, f"skipped: {stopped_because}", data_dir, None)
            results[stage.name] = "skipped"
            continue
        began = clock()
        began_at = datetime.now(UTC).isoformat(timespec="seconds")
        outcome = _attempt(stage, runner, sleep)
        if outcome.ok or outcome.soft:  # a soft failure is already recorded and never stops the run
            results[stage.name] = "ok"
            continue
        _note(stage, outcome.error, data_dir, clock() - began, began_at)
        results[stage.name] = "failed"
        if stage.required:
            stopped_because = f"{stage.name} failed"
    return results


@contextmanager
def _building(release: Path) -> Iterator[None]:
    """Point every table lookup, here and in the stage processes that inherit the variable, at the
    release being built."""
    previous = os.environ.get(store.RELEASE_ENV)
    os.environ[store.RELEASE_ENV] = str(release)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(store.RELEASE_ENV, None)
        else:
            os.environ[store.RELEASE_ENV] = previous


def refresh(stages: Sequence[Stage], runner: Runner, **options: Any) -> tuple[dict[str, str], bool]:
    """Build the next release, and publish it only if every required stage succeeded. A failed
    run leaves the current release serving; its run records are carried over so the banner shows
    the failure. Works on the project data folder (the stages do too)."""
    releases.migrate()
    for reason in refresh_queue.consume():  # this run serves every request made so far
        print(f"requested: {reason}")
    release = releases.start(os.environ.get(RUN_ID_ENV) or new_run_id())
    with _building(release):
        results = execute(stages, runner, **options)
    published = all(results[s.name] == "ok" for s in stages if s.required)
    if published:
        releases.publish(release)
        releases.prune()
    elif (release / "derived" / f"{RUNS_TABLE}.parquet").exists():
        releases.carry_over(RUNS_TABLE, "derived", release)
    return results, published


def main() -> int:
    started = datetime.now(UTC).isoformat(timespec="seconds")
    _, published = refresh(STAGES, lambda stage: run_command(argv_for(stage)))
    code = refresh_report.main(["--since", started])
    if published:
        return code
    print("NOT PUBLISHED: a required stage failed, so the data readers see is unchanged")
    return NOT_PUBLISHED_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
