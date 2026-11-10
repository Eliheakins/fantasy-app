from datetime import UTC, datetime, timedelta
from pathlib import Path

from fantasy import _runs, refresh_queue
from fantasy._lock import pipeline_lock

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def test_two_requests_make_one_marker_that_remembers_both_reasons(tmp_path: Path) -> None:
    refresh_queue.request_refresh("league added: 123", tmp_path)
    refresh_queue.request_refresh("league added: 456", tmp_path)
    markers = [p.name for p in tmp_path.iterdir()]
    assert markers == [refresh_queue.MARKER]
    assert refresh_queue.consume(tmp_path) == ["league added: 123", "league added: 456"]


def test_consume_clears_the_marker_so_a_later_request_starts_a_new_one(tmp_path: Path) -> None:
    refresh_queue.request_refresh("first", tmp_path)
    assert refresh_queue.consume(tmp_path) == ["first"]
    assert refresh_queue.consume(tmp_path) == []  # nothing queued
    refresh_queue.request_refresh("second", tmp_path)
    assert refresh_queue.consume(tmp_path) == ["second"]


def test_a_reason_cannot_break_the_marker_format(tmp_path: Path) -> None:
    refresh_queue.request_refresh("line one\nline two", tmp_path)
    assert refresh_queue.consume(tmp_path) == ["line one line two"]


def test_status_is_idle_when_nothing_is_queued_or_running(tmp_path: Path) -> None:
    status = refresh_queue.status(tmp_path)
    assert status["state"] == "idle"
    assert status["queued"] == 0
    assert status["last_finished_at"] is None
    assert status["last_run_failed"] is None


def test_status_is_queued_after_a_request(tmp_path: Path) -> None:
    refresh_queue.request_refresh("a", tmp_path)
    refresh_queue.request_refresh("b", tmp_path)
    status = refresh_queue.status(tmp_path)
    assert (status["state"], status["queued"]) == ("queued", 2)


def test_status_is_running_while_the_pipeline_lock_is_held(tmp_path: Path) -> None:
    refresh_queue.request_refresh("a", tmp_path)
    with pipeline_lock(tmp_path):
        assert refresh_queue.status(tmp_path)["state"] == "running"
    assert refresh_queue.status(tmp_path)["state"] == "queued"


def test_status_reports_the_last_run_and_whether_it_had_failures(tmp_path: Path) -> None:
    _runs.record_run("sync_sleeper", "ok", None, tmp_path, now=NOW, run_id="r1", duration_s=1.0)
    _runs.record_run("project", "failed", "boom", tmp_path, now=NOW, run_id="r1", duration_s=1.0)
    status = refresh_queue.status(tmp_path)
    assert status["last_finished_at"] == NOW.isoformat(timespec="seconds")
    assert status["last_run_failed"] is True
    _runs.record_run(
        "sync_sleeper", "ok", None, tmp_path, now=NOW + timedelta(minutes=1), run_id="r2"
    )
    assert refresh_queue.status(tmp_path)["last_run_failed"] is False  # r2 is the newest run
