"""Copy `data/archive/` and the accounts file `data/auth.db` to a dated folder outside the repo.
Neither can be regenerated.

`make refresh` runs it first. The folder is `~/fantasy-app-backups` unless FANTASY_BACKUP_DIR is
set; the newest KEEP copies stay. A copy is checked against the source (file count and bytes)
before it is kept, and no older copy is deleted when the new one holds fewer files or bytes than the
previous one, because that means the archive itself lost data. The archive holds private-use data
and the accounts file holds password hashes, so keep the folder out of any repository or shared
drive.
"""

import logging
import os
import re
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from fantasy import store
from fantasy.auth import accounts

log = logging.getLogger(__name__)
KEEP = 30
PREFIX = "archive-"
STAMP = "%Y%m%d-%H%M%S"  # UTC, so copies sort in the order they were made
COPY_NAME = re.compile(rf"{PREFIX}\d{{8}}-\d{{6}}(-\d+)?$")


def backup_dir() -> Path:
    return Path(os.environ.get("FANTASY_BACKUP_DIR") or Path.home() / "fantasy-app-backups")


def copy_database(source: Path, destination: Path) -> None:
    """A consistent copy of a live SQLite file (its own backup, not a file copy), owner-only."""
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(destination)) as dst:
        src.backup(dst)
    destination.chmod(0o600)


def tree_size(path: Path, skip: str = "") -> tuple[int, int]:
    """(file count, bytes) under `path`, leaving out a top-level file named `skip`."""
    files = [p for p in path.rglob("*") if p.is_file() and p.relative_to(path) != Path(skip)]
    return len(files), sum(p.stat().st_size for p in files)


def run(data_dir: Path | None = None, target: Path | None = None, keep: int = KEEP) -> Path | None:
    """The new copy's path, or None when there is nothing yet to back up. Older copies past `keep`
    go."""
    source = store.resolve(data_dir) / "archive"
    auth = accounts.db_path(data_dir)
    if not source.is_dir() and not auth.exists():
        log.info("no archive at %s and no accounts file; nothing to back up", source)
        return None
    root = target or backup_dir()
    root.mkdir(parents=True, exist_ok=True)
    name = f"{PREFIX}{datetime.now(UTC).strftime(STAMP)}"
    copy, n = root / name, 1
    while copy.exists():  # two runs in one second
        copy, n = root / f"{name}-{n}", n + 1
    partial = root / f".{copy.name}.partial"
    shutil.rmtree(partial, ignore_errors=True)
    if source.is_dir():
        shutil.copytree(source, partial)
    else:
        partial.mkdir()
    if auth.exists():
        copy_database(auth, partial / accounts.DB_NAME)
    copied = tree_size(
        partial, accounts.DB_NAME
    )  # the accounts file is a SQLite copy, not a file copy
    if copied != (tree_size(source) if source.is_dir() else (0, 0)):
        shutil.rmtree(partial)
        raise RuntimeError(f"backup of {source} is incomplete (files, bytes): {copied}; discarded")
    earlier = sorted(p for p in root.iterdir() if p.is_dir() and COPY_NAME.match(p.name))
    partial.rename(copy)  # a copy that failed halfway never carries a real name
    previous = tree_size(earlier[-1], accounts.DB_NAME) if earlier else (0, 0)
    if copied[0] < previous[0] or copied[1] < previous[1]:
        log.warning(
            "archive shrank since %s (files, bytes: %s -> %s); keeping every backup",
            earlier[-1].name,
            previous,
            copied,
        )
        return copy
    stamped = [*earlier, copy]
    for old in stamped[: max(len(stamped) - keep, 0)]:
        shutil.rmtree(old)
    return copy


def main() -> None:
    copy = run()
    print(f"archive and accounts copied to {copy}" if copy else "nothing to back up")


if __name__ == "__main__":
    main()
