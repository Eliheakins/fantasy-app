import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from fantasy import _lock
from fantasy._lock import PipelineBusy, hold_and_run, pipeline_lock

HOLDER = (
    "import sys, time\n"
    "from pathlib import Path\n"
    "from fantasy._lock import pipeline_lock\n"
    "with pipeline_lock(Path(sys.argv[1])):\n"
    "    print('held', flush=True)\n"
    "    time.sleep(30)\n"
)


def test_a_second_non_blocking_holder_is_refused_until_the_first_leaves(tmp_path: Path) -> None:
    with pipeline_lock(tmp_path):
        with pytest.raises(PipelineBusy), pipeline_lock(tmp_path, blocking=False):
            pass
    with pipeline_lock(tmp_path, blocking=False):  # released on exit
        pass


def test_a_blocking_holder_waits_for_the_first(tmp_path: Path) -> None:
    order: list[str] = []
    first_in, release, second_done = threading.Event(), threading.Event(), threading.Event()

    def first() -> None:
        with pipeline_lock(tmp_path):
            order.append("first in")
            first_in.set()
            release.wait(timeout=5)
            order.append("first out")

    def second() -> None:
        with pipeline_lock(tmp_path):
            order.append("second in")
        second_done.set()

    threading.Thread(target=first).start()
    assert first_in.wait(timeout=5)
    threading.Thread(target=second).start()
    assert not second_done.wait(timeout=0.3)  # still waiting while the first holds it
    release.set()
    assert second_done.wait(timeout=5)
    assert order == ["first in", "first out", "second in"]


def test_a_lock_held_by_another_process_refuses_and_dies_with_it(tmp_path: Path) -> None:
    proc = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(tmp_path)], stdout=subprocess.PIPE, text=True
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "held"
        with pytest.raises(PipelineBusy), pipeline_lock(tmp_path, blocking=False):
            pass
    finally:
        proc.kill()
        proc.wait()
    with pipeline_lock(tmp_path, blocking=False):  # a killed holder leaves no stale lock
        pass


def test_hold_and_run_marks_the_child_and_returns_its_exit_code(tmp_path: Path) -> None:
    child = (
        "import os, sys\n"
        "held = os.environ['FANTASY_PIPELINE_LOCK_HELD'] == '1'\n"
        "run_id = os.environ.get('FANTASY_RUN_ID', '')\n"
        "sys.exit(0 if held and run_id else 3)\n"
    )
    assert hold_and_run([sys.executable, "-c", child], tmp_path) == 0
    assert hold_and_run([sys.executable, "-c", "import sys; sys.exit(5)"], tmp_path) == 5


def test_the_run_id_is_a_sortable_utc_stamp() -> None:
    assert re.fullmatch(r"\d{8}T\d{6}Z", _lock.new_run_id())


def test_a_child_of_the_holder_does_not_wait_for_its_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_lock.HELD_ENV, "1")  # the parent process holds the lock for this whole run
    with pipeline_lock(tmp_path), pipeline_lock(tmp_path, blocking=False):
        pass


def test_main_needs_a_command_and_passes_the_exit_code_through(tmp_path: Path) -> None:
    assert _lock.main([]) == 2
    assert _lock.hold_and_run([sys.executable, "-c", "import sys; sys.exit(4)"], tmp_path) == 4


def _ids_seen(tmp_path: Path, code: int) -> str:
    child = (
        "import os, sys\n"
        "open(sys.argv[1], 'w').write(os.environ['FANTASY_RUN_ID'])\n"
        f"sys.exit({code})\n"
    )
    out = tmp_path / "id.txt"
    hold_and_run([sys.executable, "-c", child, str(out)], tmp_path)
    return out.read_text().strip()


def test_a_run_that_was_not_published_is_retried_under_the_same_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_lock.RUN_ID_ENV, raising=False)
    first = _ids_seen(tmp_path, _lock.NOT_PUBLISHED_EXIT)
    assert _ids_seen(tmp_path, _lock.NOT_PUBLISHED_EXIT) == first
    assert _ids_seen(tmp_path, 0) == first  # the retry that publishes still shares the id
    monkeypatch.setattr(_lock, "new_run_id", lambda: "next")
    assert _ids_seen(tmp_path, 0) == "next"  # a published run ends the chain
