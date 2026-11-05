from __future__ import annotations

from pathlib import Path

import pytest

from nfl_stat.pipeline.atomic import atomic_path


def test_the_target_appears_only_after_the_block_finishes(tmp_path: Path):
    target = tmp_path / "out.txt"

    with atomic_path(target) as tmp:
        tmp.write_text("hello")
        assert not target.exists()

    assert target.read_text() == "hello"


def test_no_temp_file_is_left_behind_on_success(tmp_path: Path):
    target = tmp_path / "out.txt"

    with atomic_path(target) as tmp:
        tmp.write_text("hello")

    assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]


def test_a_failure_leaves_the_old_file_untouched_and_cleans_up(tmp_path: Path):
    target = tmp_path / "out.txt"
    target.write_text("old")

    with pytest.raises(RuntimeError, match="boom"), atomic_path(target) as tmp:
        tmp.write_text("half-written")
        raise RuntimeError("boom")

    assert target.read_text() == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]


def test_two_writers_never_share_a_temp_path(tmp_path: Path):
    target = tmp_path / "out.txt"

    with atomic_path(target) as first, atomic_path(target) as second:
        assert first != second
