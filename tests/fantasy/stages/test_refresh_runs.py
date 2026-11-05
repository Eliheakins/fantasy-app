import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fantasy import _runs, store
from fantasy.stages import refresh_report

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, body: str) -> str:
    (tmp_path / f"{name}.py").write_text(body)
    monkeypatch.syspath_prepend(str(tmp_path))
    return name


def runs(data_dir: Path) -> list[dict[str, object]]:
    return store.read_table("refresh_runs", "derived", data_dir).to_dicts()


def test_a_stage_that_finishes_is_recorded_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = module(tmp_path, monkeypatch, "stage_ok", "print('hi')\n")
    assert _runs.run_stage("ok_stage", mod, data_dir=tmp_path / "d") == 0
    [row] = runs(tmp_path / "d")
    assert (row["stage"], row["status"], row["error"]) == ("ok_stage", "ok", None)
    assert datetime.fromisoformat(str(row["finished_at"])).tzinfo is not None


def test_a_soft_failure_is_recorded_failed_with_its_error_and_exit_code_stays_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = module(
        tmp_path,
        monkeypatch,
        "stage_soft",
        "from fantasy._runs import note_soft_failure\nnote_soft_failure('site changed')\n",
    )
    assert _runs.run_stage("soft", mod, data_dir=tmp_path) == 0
    [row] = runs(tmp_path)
    assert (row["status"], row["error"]) == ("failed", "site changed")


def test_soft_failures_do_not_leak_into_the_next_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    soft = module(
        tmp_path,
        monkeypatch,
        "stage_a",
        "from fantasy._runs import note_soft_failure\nnote_soft_failure('x')\n",
    )
    fine = module(tmp_path, monkeypatch, "stage_b", "pass\n")
    _runs.run_stage("a", soft, data_dir=tmp_path)
    _runs.run_stage("b", fine, data_dir=tmp_path)
    assert {r["stage"]: r["status"] for r in runs(tmp_path)} == {"a": "failed", "b": "ok"}


def test_a_crash_is_recorded_and_reraised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = module(tmp_path, monkeypatch, "stage_boom", "raise RuntimeError('disk full')\n")
    with pytest.raises(RuntimeError):
        _runs.run_stage("boom", mod, data_dir=tmp_path)
    [row] = runs(tmp_path)
    assert row["status"] == "failed" and "disk full" in str(row["error"])


def test_a_nonzero_exit_is_recorded_failed_and_returned_and_argv_is_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = module(
        tmp_path,
        monkeypatch,
        "stage_exit",
        "import sys\nraise SystemExit(3 if sys.argv[1:] == ['--refresh'] else 0)\n",
    )
    before = list(sys.argv)
    assert _runs.run_stage("exit", mod, ["--refresh"], data_dir=tmp_path) == 3
    assert sys.argv == before
    [row] = runs(tmp_path)
    assert (row["status"], row["error"]) == ("failed", "exit code 3")


def test_runs_append_and_the_latest_row_per_stage_wins(tmp_path: Path) -> None:
    _runs.record_run("a", "failed", "old", tmp_path, now=NOW)
    _runs.record_run("b", "ok", None, tmp_path, now=NOW)
    _runs.record_run("a", "ok", None, tmp_path, now=datetime(2026, 11, 6, tzinfo=UTC))
    latest = _runs.latest_runs(tmp_path)
    assert {r["stage"]: r["status"] for r in latest.to_dicts()} == {"a": "ok", "b": "ok"}
    assert _runs.latest_runs(tmp_path / "none").height == 0


def test_a_long_error_is_cut(tmp_path: Path) -> None:
    _runs.record_run("a", "failed", "x" * 5000, tmp_path, now=NOW)
    assert len(str(runs(tmp_path)[0]["error"])) <= _runs.MAX_ERROR_CHARS


def test_the_table_is_never_written_under_the_stat_folder(tmp_path: Path) -> None:
    _runs.record_run("a", "ok", None, tmp_path, now=NOW)
    assert store.table_path("refresh_runs", "derived", tmp_path).parent.name == "derived"


def test_report_exits_one_and_names_each_failed_stage_of_this_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _runs.record_run("digest", "failed", "boom", tmp_path, now=datetime(2026, 11, 1, tzinfo=UTC))
    _runs.record_run("market_values", "failed", "down", tmp_path, now=NOW)
    _runs.record_run("score", "ok", None, tmp_path, now=NOW)
    code = refresh_report.main(["--since", "2026-11-05T11:00:00Z"], data_dir=tmp_path)
    out = capsys.readouterr().out
    assert code == 1
    assert "market_values: down" in out and "digest" not in out and "score" not in out


def test_report_exits_zero_when_nothing_failed_in_this_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _runs.record_run("digest", "failed", "boom", tmp_path, now=datetime(2026, 11, 1, tzinfo=UTC))
    _runs.record_run("score", "ok", None, tmp_path, now=NOW)
    assert refresh_report.main(["--since", "2026-11-05T11:00:00+00:00"], data_dir=tmp_path) == 0
    assert "every stage ok" in capsys.readouterr().out
