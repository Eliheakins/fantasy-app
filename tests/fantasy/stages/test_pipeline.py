import importlib.util
import os
import sys
from collections.abc import Callable
from pathlib import Path

import polars as pl
import pytest

from fantasy import pipeline, store
from fantasy._lock import NOT_PUBLISHED_EXIT
from fantasy._runs import SOFT_FAILURE_EXIT, record_run
from fantasy.pipeline import Outcome, Stage
from fantasy.stages import refresh_report

OK = Outcome(True)


def rows(data_dir: Path) -> dict[str, dict[str, object]]:
    table = store.read_table("refresh_runs", "derived", data_dir).to_dicts()
    return {str(r["stage"]): r for r in table}


class Script:
    """A runner that answers per stage from a script and remembers every call."""

    def __init__(self, answers: dict[str, list[Outcome]]) -> None:
        self.answers = {name: list(outcomes) for name, outcomes in answers.items()}
        self.calls: list[str] = []

    def __call__(self, stage: Stage) -> Outcome:
        self.calls.append(stage.name)
        queue = self.answers.get(stage.name)
        return queue.pop(0) if queue else OK


def stages(*specs: str) -> tuple[Stage, ...]:
    """'a' is required, 'a?' optional, 'a@' required and network, 'a@?' optional and network."""
    built = []
    for spec in specs:
        name = spec.rstrip("?@")
        built.append(Stage(name, f"m.{name}", required="?" not in spec, network="@" in spec))
    return tuple(built)


def run(
    plan: tuple[Stage, ...], runner: Callable[[Stage], Outcome], data_dir: Path
) -> dict[str, str]:
    return pipeline.execute(plan, runner, data_dir=data_dir, sleep=lambda s: None)


def test_every_stage_runs_in_order_when_all_succeed(tmp_path: Path) -> None:
    runner = Script({})
    result = run(stages("a", "b?", "c"), runner, tmp_path)
    assert runner.calls == ["a", "b", "c"]
    assert set(result.values()) == {"ok"}


def test_a_required_failure_skips_the_rest_and_records_why(tmp_path: Path) -> None:
    runner = Script({"b": [Outcome(False, "exit code 1")]})
    result = run(stages("a", "b", "c", "d?"), runner, tmp_path)
    assert runner.calls == ["a", "b"]
    assert result == {"a": "ok", "b": "failed", "c": "skipped", "d": "skipped"}
    recorded = rows(tmp_path)
    assert recorded["b"]["status"] == "failed"
    assert recorded["b"]["error"] == "exit code 1"
    assert recorded["c"]["status"] == "failed"
    assert str(recorded["c"]["error"]).startswith("skipped: b failed")


def test_an_optional_failure_is_recorded_and_the_run_goes_on(tmp_path: Path) -> None:
    runner = Script({"b": [Outcome(False, "site changed")]})
    result = run(stages("a", "b?", "c"), runner, tmp_path)
    assert runner.calls == ["a", "b", "c"]
    assert result == {"a": "ok", "b": "failed", "c": "ok"}
    assert rows(tmp_path)["b"]["error"] == "site changed"


def test_a_network_stage_is_retried_with_a_backoff_until_it_succeeds(tmp_path: Path) -> None:
    runner = Script({"a": [Outcome(False, "timeout"), Outcome(False, "timeout"), OK]})
    pauses: list[float] = []
    result = pipeline.execute(stages("a@", "b"), runner, data_dir=tmp_path, sleep=pauses.append)
    assert runner.calls == ["a", "a", "a", "b"]
    assert pauses == [pipeline.RETRY_BACKOFF_S] * 2
    assert result == {"a": "ok", "b": "ok"}


def test_retries_give_up_after_the_limit_and_count_as_one_failure(tmp_path: Path) -> None:
    runner = Script({"a": [Outcome(False, "down")] * 5})
    result = run(stages("a@?", "b"), runner, tmp_path)
    assert runner.calls.count("a") == 1 + pipeline.NETWORK_RETRIES
    assert result["a"] == "failed"
    assert result["b"] == "ok"


def test_a_stage_that_is_not_network_is_not_retried(tmp_path: Path) -> None:
    runner = Script({"a": [Outcome(False, "bug")]})
    run(stages("a?"), runner, tmp_path)
    assert runner.calls == ["a"]


def test_the_run_stops_starting_stages_after_the_run_timeout(tmp_path: Path) -> None:
    now = {"t": 0.0}

    def runner(stage: Stage) -> Outcome:
        now["t"] += 700.0  # each stage takes longer than the whole run may
        return OK

    result = pipeline.execute(
        stages("a", "b", "c"),
        runner,
        data_dir=tmp_path,
        sleep=lambda s: None,
        clock=lambda: now["t"],
        run_timeout=1000.0,
    )
    assert result == {"a": "ok", "b": "ok", "c": "skipped"}
    assert "run exceeded" in str(rows(tmp_path)["c"]["error"])


def test_run_command_reports_exit_codes_and_timeouts() -> None:
    assert pipeline.run_command([sys.executable, "-c", "pass"], timeout=10) == OK
    failed = pipeline.run_command([sys.executable, "-c", "raise SystemExit(3)"], timeout=10)
    assert failed == Outcome(False, "exit code 3")
    slow = pipeline.run_command([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.3)
    assert not slow.ok
    assert "timed out" in str(slow.error)


def test_a_stage_is_started_through_run_recorded() -> None:
    stage = Stage("stat_data", "nfl_stat.pipeline.cli", args=("--refresh",))
    assert pipeline.argv_for(stage)[1:] == [
        "-m",
        "fantasy.stages.run_recorded",
        "stat_data",
        "nfl_stat.pipeline.cli",
        "--refresh",
    ]


def test_the_stage_list_is_what_make_refresh_ran_before() -> None:
    assert [s.name for s in pipeline.STAGES] == [
        "backup",
        "sync_sleeper",
        "news_archive",
        "ingest_nfl",
        "week_rollover",
        "sleeper_projections",
        "outside_projections",
        "crosswalk",
        "score",
        "odds_snapshot",
        "prop_points",
        "streaming",
        "project",
        "learn",
        "availability",
        "distributions",
        "injuries",
        "outlook",
        "simulate",
        "digest",
        "market_values",
        "stat_data",
    ]


@pytest.mark.parametrize("stage", pipeline.STAGES, ids=lambda s: s.name)
def test_every_stage_module_exists(stage: Stage) -> None:
    assert importlib.util.find_spec(stage.module) is not None


def test_the_stages_the_simulation_cannot_do_without_are_required() -> None:
    required = {s.name for s in pipeline.STAGES if s.required}
    assert {"backup", "sync_sleeper", "ingest_nfl", "project", "learn", "simulate"} <= required


def test_the_daily_profile_is_the_full_run_without_spending_odds_credits() -> None:
    assert [s for s in pipeline.STAGES if s.name != "odds_snapshot"] == list(pipeline.DAILY_STAGES)


def test_the_sleeper_profile_writes_no_archive_and_keeps_the_week_rolled_over() -> None:
    names = [s.name for s in pipeline.SLEEPER_STAGES]
    assert names.index("sync_sleeper") < names.index("week_rollover") < names.index("simulate")
    assert "backup" not in names  # safe only because nothing below appends to the archive
    archive_writers = {"news_archive", "sleeper_projections", "outside_projections", "learn"}
    assert not archive_writers & set(names)
    assert {"streaming", "odds_snapshot"}.isdisjoint(names)
    simulate = next(s for s in pipeline.SLEEPER_STAGES if s.name == "simulate")
    assert simulate.args == ("--no-archive",)


def test_main_rejects_an_unknown_profile() -> None:
    assert pipeline.main(["hourly"]) == 2


@pytest.mark.parametrize("profile", list(pipeline.PROFILES))
def test_main_runs_the_named_profile(monkeypatch: pytest.MonkeyPatch, profile: str) -> None:
    seen: list[tuple[Stage, ...]] = []

    def fake_refresh(stages: tuple[Stage, ...], runner: object, **kw: object) -> tuple[dict, bool]:
        seen.append(stages)
        return {}, True

    monkeypatch.setattr(pipeline, "refresh", fake_refresh)
    monkeypatch.setattr(refresh_report, "main", lambda argv: 0)
    assert pipeline.main([profile]) == 0
    assert seen == [pipeline.PROFILES[profile]]


class Building:
    """A runner that, like a stage, writes a table into whatever release is being built."""

    def __init__(self, fail: str | None = None) -> None:
        self.fail = fail

    def __call__(self, stage: Stage) -> Outcome:
        if stage.name == self.fail:
            return Outcome(False, "boom")
        path = store.table_path(f"out_{stage.name}", "derived")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        pl.DataFrame({"v": [1]}).write_parquet(tmp)
        os.replace(tmp, path)
        return OK


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.delenv(store.RELEASE_ENV, raising=False)
    old = tmp_path / "derived" / "out_old.parquet"
    old.parent.mkdir()
    pl.DataFrame({"v": [0]}).write_parquet(old)  # a table from before the first release
    return tmp_path


def names(directory: Path) -> set[str]:
    return {p.stem for p in directory.glob("*.parquet")}


def test_a_run_whose_required_stages_pass_is_published_and_keeps_older_tables(root: Path) -> None:
    results, published = pipeline.refresh(stages("a", "b?"), Building(), sleep=lambda s: None)
    assert published
    assert results == {"a": "ok", "b": "ok"}
    current = names(store.area_dir("derived"))
    assert {"out_a", "out_b", "out_old"} <= current  # the first run also migrated the old layout
    assert (root / "current").is_symlink()
    assert store.RELEASE_ENV not in os.environ


def test_a_failed_required_stage_publishes_nothing_but_the_failure_is_visible(root: Path) -> None:
    pipeline.refresh(stages("a"), Building(), sleep=lambda s: None)  # a good release first
    before = (root / "current").resolve()
    results, published = pipeline.refresh(
        stages("a", "b", "c"), Building(fail="b"), sleep=lambda s: None
    )
    assert not published
    assert results == {"a": "ok", "b": "failed", "c": "skipped"}
    assert (root / "current").resolve() == before  # readers still see the last good release
    assert "out_c" not in names(store.area_dir("derived"))
    failed = {r["stage"] for r in store.read_table("refresh_runs", "derived").to_dicts()}
    assert {"b", "c"} <= failed  # the banner reads the current release, so it was carried over


def test_an_optional_failure_still_publishes_and_the_old_table_carries_forward(root: Path) -> None:
    results, published = pipeline.refresh(
        stages("a", "b?"), Building(fail="b"), sleep=lambda s: None
    )
    assert published
    assert results["b"] == "failed"
    assert "out_old" in names(store.area_dir("derived"))
    assert "out_b" not in names(store.area_dir("derived"))


def test_a_run_takes_every_queued_request(root: Path) -> None:
    from fantasy import refresh_queue

    refresh_queue.request_refresh("league added: 1")
    refresh_queue.request_refresh("league added: 2")
    pipeline.refresh(stages("a"), Building(), sleep=lambda s: None)
    assert refresh_queue.consume() == []  # served by that run
    assert refresh_queue.status()["state"] == "idle"


@pytest.mark.parametrize(
    ("published", "report_code", "expected"),
    [(True, 0, 0), (True, 1, 1), (False, 1, NOT_PUBLISHED_EXIT)],
)
def test_the_exit_code_tells_the_service_whether_a_retry_is_worth_it(
    monkeypatch: pytest.MonkeyPatch, published: bool, report_code: int, expected: int
) -> None:
    monkeypatch.setattr(pipeline, "refresh", lambda stages, runner, **kw: ({}, published))
    monkeypatch.setattr(refresh_report, "main", lambda argv: report_code)
    assert pipeline.main() == expected


def test_the_childs_own_error_survives_the_parents_exit_code_row(tmp_path: Path) -> None:
    def runner(stage: Stage) -> Outcome:
        record_run(stage.name, "failed", "RuntimeError('disk full')", tmp_path)
        return Outcome(False, "exit code 1")  # what run_command says after the child exits 1

    run(stages("a?"), runner, tmp_path)
    table = store.read_table("refresh_runs", "derived", tmp_path).to_dicts()
    assert [(r["stage"], r["error"]) for r in table] == [("a", "RuntimeError('disk full')")]


def test_a_failure_the_child_could_not_record_is_still_recorded(tmp_path: Path) -> None:
    run(stages("a?"), Script({"a": [Outcome(False, "timed out after 600s")]}), tmp_path)
    assert rows(tmp_path)["a"]["error"] == "timed out after 600s"


SOFT = Outcome(False, "soft failure", soft=True)


def test_a_soft_failure_exit_code_is_told_apart_from_a_failure() -> None:
    code = f"raise SystemExit({SOFT_FAILURE_EXIT})"
    assert pipeline.run_command([sys.executable, "-c", code], timeout=10) == SOFT


def test_a_network_stage_that_soft_fails_is_retried(tmp_path: Path) -> None:
    runner = Script({"a": [SOFT, OK]})
    result = run(stages("a@?"), runner, tmp_path)
    assert runner.calls == ["a", "a"]
    assert result == {"a": "ok"}


def test_a_soft_failure_after_the_last_retry_does_not_stop_the_run_or_record_twice(
    tmp_path: Path,
) -> None:
    runner = Script({"a": [SOFT] * 5})
    result = run(stages("a@", "b"), runner, tmp_path)  # a is required
    assert runner.calls == ["a"] * (1 + pipeline.NETWORK_RETRIES) + ["b"]
    assert result == {"a": "ok", "b": "ok"}
    assert not (tmp_path / "derived" / "refresh_runs.parquet").exists()  # the child recorded it
