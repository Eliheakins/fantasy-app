from pathlib import Path

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
