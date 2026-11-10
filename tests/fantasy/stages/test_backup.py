import shutil
from pathlib import Path

import pytest

from fantasy.stages import backup


def _archive(data_dir: Path) -> None:
    (data_dir / "archive" / "odds").mkdir(parents=True)
    (data_dir / "archive" / "proj_snapshots.parquet").write_text("x")
    (data_dir / "archive" / "odds" / "w7.parquet").write_text("y")


def test_copies_the_archive_with_its_folders_and_leaves_the_source_alone(tmp_path: Path) -> None:
    _archive(tmp_path / "data")

    copy = backup.run(tmp_path / "data", tmp_path / "out")

    assert copy is not None and copy.parent == tmp_path / "out"
    assert (copy / "odds" / "w7.parquet").read_text() == "y"
    assert (tmp_path / "data" / "archive" / "proj_snapshots.parquet").exists()


def test_keeps_only_the_newest_copies_and_never_touches_other_folders(tmp_path: Path) -> None:
    _archive(tmp_path / "data")
    out = tmp_path / "out"
    for stamp in ("20260101-000000", "20260102-000000", "20260103-000000"):
        (out / f"archive-{stamp}").mkdir(parents=True)
    (out / "notes").mkdir()

    backup.run(tmp_path / "data", out, keep=2)

    names = sorted(p.name for p in out.iterdir())
    assert "notes" in names and "archive-20260101-000000" not in names
    assert "archive-20260103-000000" in names and len(names) == 3  # notes, newest old, new


def test_does_nothing_without_an_archive(tmp_path: Path) -> None:
    assert backup.run(tmp_path / "data", tmp_path / "out") is None
    assert not (tmp_path / "out").exists()


def test_two_copies_in_one_second_both_survive_and_odd_folders_do_not_count(
    tmp_path: Path,
) -> None:
    _archive(tmp_path / "data")
    out = tmp_path / "out"
    (out / "archive-notes").mkdir(parents=True)

    first = backup.run(tmp_path / "data", out, keep=2)
    second = backup.run(tmp_path / "data", out, keep=2)
    third = backup.run(tmp_path / "data", out, keep=2)

    assert first and second and third and len({first, second, third}) == 3
    assert (out / "archive-notes").exists()
    copies = [p for p in out.iterdir() if backup.COPY_NAME.match(p.name)]
    assert len(copies) == 2 and not list(out.glob(".*.partial"))


def _accounts(data_dir: Path) -> None:
    import datetime as dt

    from fantasy.auth import accounts

    conn = accounts.connect(data_dir)
    accounts.create_invite(conn, "friend@example.com", dt.datetime(2026, 11, 9, tzinfo=dt.UTC))
    conn.close()


def test_the_accounts_file_is_copied_with_the_archive_and_readable_as_a_database(
    tmp_path: Path,
) -> None:
    import sqlite3
    import stat

    _archive(tmp_path / "data")
    _accounts(tmp_path / "data")

    copy = backup.run(tmp_path / "data", tmp_path / "out")

    assert copy is not None
    saved = copy / "auth.db"
    assert stat.S_IMODE(saved.stat().st_mode) == 0o600  # it holds password hashes
    conn = sqlite3.connect(saved)
    assert conn.execute("SELECT email FROM accounts").fetchall() == [("friend@example.com",)]
    conn.close()


def test_accounts_are_backed_up_even_before_there_is_an_archive(tmp_path: Path) -> None:
    _accounts(tmp_path / "data")
    copy = backup.run(tmp_path / "data", tmp_path / "out")
    assert copy is not None and (copy / "auth.db").exists()


def test_a_copy_that_shrank_keeps_every_older_backup(tmp_path: Path) -> None:
    _archive(tmp_path / "data")
    out = tmp_path / "out"
    first = backup.run(tmp_path / "data", out, keep=1)
    (tmp_path / "data" / "archive" / "odds" / "w7.parquet").unlink()  # the archive lost a file

    second = backup.run(tmp_path / "data", out, keep=1)

    assert first and second and first.exists() and second.exists()


def test_a_copy_that_did_not_shrink_still_prunes(tmp_path: Path) -> None:
    _archive(tmp_path / "data")
    out = tmp_path / "out"
    first = backup.run(tmp_path / "data", out, keep=1)
    (tmp_path / "data" / "archive" / "proj_snapshots.parquet").write_text("xx")  # grew

    second = backup.run(tmp_path / "data", out, keep=1)

    assert first and second and not first.exists() and second.exists()


def test_a_copy_that_does_not_match_the_source_is_discarded_and_nothing_is_pruned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _archive(tmp_path / "data")
    out = tmp_path / "out"
    first = backup.run(tmp_path / "data", out, keep=1)
    real_copytree = shutil.copytree

    def lossy(src: Path, dst: Path, *args: object, **kwargs: object) -> Path:
        real_copytree(src, dst, *args, **kwargs)  # type: ignore[arg-type]
        (Path(dst) / "odds" / "w7.parquet").unlink(missing_ok=True)
        return Path(dst)

    monkeypatch.setattr(shutil, "copytree", lossy)
    with pytest.raises(RuntimeError, match="incomplete"):
        backup.run(tmp_path / "data", out, keep=1)

    assert first and first.exists()
    assert [p.name for p in out.iterdir()] == [first.name]
