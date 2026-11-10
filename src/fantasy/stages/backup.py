"""Copy `data/archive/` and the accounts file `data/auth.db` to a dated folder outside the repo.
Neither can be regenerated.

`make refresh` runs it first. The folder is `~/fantasy-app-backups` unless FANTASY_BACKUP_DIR is
set; the newest KEEP copies stay. The archive holds private-use data and the accounts file holds
password hashes, so keep the folder out of any repository or shared drive.
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
    partial.rename(copy)  # a copy that failed halfway never carries a real name
    stamped = sorted(p for p in root.iterdir() if p.is_dir() and COPY_NAME.match(p.name))
    for old in stamped[: max(len(stamped) - keep, 0)]:
        shutil.rmtree(old)
    return copy


def main() -> None:
    copy = run()
    print(f"archive and accounts copied to {copy}" if copy else "nothing to back up")


if __name__ == "__main__":
    main()
