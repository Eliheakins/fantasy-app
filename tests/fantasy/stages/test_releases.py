import os
from pathlib import Path

import polars as pl
import pytest

from fantasy import releases, store


def put(path: Path, value: int) -> None:
    """Write like the stages do: a temp file replaced into place, never an in-place overwrite
    (a release shares its files with the one before it through hard links)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    pl.DataFrame({"v": [value]}).write_parquet(tmp)
    os.replace(tmp, path)


def value(path: Path) -> int:
    return int(pl.read_parquet(path)["v"][0])


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.delenv(store.RELEASE_ENV, raising=False)
    return tmp_path


def legacy_layout(root: Path) -> None:
    """The layout before the first release: tables in raw/ and derived/, caches beside them."""
    put(root / "raw" / "t_raw.parquet", 1)
    put(root / "derived" / "t_der.parquet", 2)
    put(root / "archive" / "t_arc.parquet", 3)
    (root / "raw" / "pbp").mkdir()
    (root / "raw" / "pbp" / "2026.parquet").write_bytes(b"cache")
    (root / "raw" / "sleeper_players_cache.json").write_text("{}")


def test_migrate_moves_the_tables_and_leaves_caches_and_the_archive(root: Path) -> None:
    legacy_layout(root)
    assert releases.migrate() is True
    assert (root / "current").is_symlink()
    assert value(store.table_path("t_raw", "raw")) == 1
    assert value(store.table_path("t_der", "derived")) == 2
    assert store.table_path("t_raw", "raw") == root / "current" / "raw" / "t_raw.parquet"
    assert not (root / "raw" / "t_raw.parquet").exists()
    assert (root / "raw" / "pbp" / "2026.parquet").read_bytes() == b"cache"
    assert (root / "raw" / "sleeper_players_cache.json").exists()
    assert value(root / "archive" / "t_arc.parquet") == 3


def test_migrate_twice_changes_nothing_the_second_time(root: Path) -> None:
    legacy_layout(root)
    assert releases.migrate() is True
    assert releases.migrate() is False
    assert value(store.table_path("t_raw", "raw")) == 1


def test_migrate_finishes_a_half_done_migration(root: Path) -> None:
    legacy_layout(root)
    releases.migrate()
    put(root / "raw" / "t_late.parquet", 9)  # left behind by an interrupted move
    assert releases.migrate() is True
    assert value(store.table_path("t_late", "raw")) == 9


def test_a_fresh_install_gets_an_empty_release_and_writes_land_in_it(root: Path) -> None:
    assert releases.migrate() is True
    put(store.table_path("t_new", "derived"), 5)
    assert value(root / "current" / "derived" / "t_new.parquet") == 5


def test_before_any_migration_tables_stay_where_they_were(root: Path) -> None:
    assert store.table_path("t_raw", "raw") == root / "raw" / "t_raw.parquet"
    assert store.table_path("t_arc", "archive") == root / "archive" / "t_arc.parquet"


def test_start_copies_the_current_release_without_copying_the_bytes(root: Path) -> None:
    legacy_layout(root)
    releases.migrate()
    staged = releases.start("20261109T120000Z")
    old = root / "current" / "raw" / "t_raw.parquet"
    new = staged / "raw" / "t_raw.parquet"
    assert os.stat(old).st_ino == os.stat(new).st_ino  # hard links: no extra disk
    assert staged.parent == root / "releases"


def test_a_stage_writing_into_the_new_release_leaves_the_current_one_alone(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy_layout(root)
    releases.migrate()
    staged = releases.start("20261109T120000Z")
    monkeypatch.setenv(store.RELEASE_ENV, str(staged))
    df = pl.DataFrame({"v": [100]})
    with_env = store.table_path("t_raw", "raw")
    assert with_env == staged / "raw" / "t_raw.parquet"
    from nfl_stat.pipeline.atomic import atomic_path

    with atomic_path(with_env) as tmp:
        df.write_parquet(tmp)
    assert value(staged / "raw" / "t_raw.parquet") == 100
    assert value(root / "current" / "raw" / "t_raw.parquet") == 1


def test_the_archive_and_explicit_directories_ignore_the_release_variable(
    root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    legacy_layout(root)
    releases.migrate()
    monkeypatch.setenv(store.RELEASE_ENV, str(root / "releases" / "x"))
    assert store.table_path("t_arc", "archive") == root / "archive" / "t_arc.parquet"
    other = tmp_path_factory.mktemp("other")
    assert store.table_path("t_raw", "raw", other) == other / "raw" / "t_raw.parquet"


def test_publish_flips_what_every_reader_sees(root: Path) -> None:
    legacy_layout(root)
    releases.migrate()
    staged = releases.start("20261109T120000Z")
    put(staged / "derived" / "t_der.parquet", 20)
    assert value(store.table_path("t_der", "derived")) == 2
    releases.publish(staged)
    assert value(store.table_path("t_der", "derived")) == 20
    assert (root / "current").resolve() == staged.resolve()


def test_carry_over_copies_one_table_into_the_current_release(root: Path) -> None:
    legacy_layout(root)
    releases.migrate()
    staged = releases.start("20261109T120000Z")
    put(staged / "derived" / "t_der.parquet", 77)
    releases.carry_over("t_der", "derived", staged)
    assert value(store.table_path("t_der", "derived")) == 77
    assert (root / "current").resolve() != staged.resolve()  # nothing else was published


def test_prune_keeps_the_newest_releases_and_never_the_current_one(root: Path) -> None:
    legacy_layout(root)
    releases.migrate()
    names = [f"2026110{n}T000000Z" for n in range(1, 8)]
    for name in names:
        releases.start(name)
    releases.publish(root / "releases" / names[0])  # the oldest is live
    removed = releases.prune(keep=3)
    left = sorted(p.name for p in (root / "releases").iterdir())
    assert names[0] in left
    assert names[-1] in left
    assert len(left) == 4  # the three newest and the live one
    assert len(removed) == len(names) + 1 - 4  # the first release counts too
