"""Copy `data/archive/` to a dated folder outside the repo. The archive cannot be regenerated.

`make refresh` runs it first. The folder is `~/fantasy-app-backups` unless FANTASY_BACKUP_DIR is
set; the newest KEEP copies stay. The archive holds private-use data, so keep the folder out of
any repository or shared drive.
"""

import logging
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from fantasy import store

log = logging.getLogger(__name__)
KEEP = 30
PREFIX = "archive-"
STAMP = "%Y%m%d-%H%M%S"  # UTC, so copies sort in the order they were made
COPY_NAME = re.compile(rf"{PREFIX}\d{{8}}-\d{{6}}(-\d+)?$")


def backup_dir() -> Path:
    return Path(os.environ.get("FANTASY_BACKUP_DIR") or Path.home() / "fantasy-app-backups")


def run(
    data_dir: Path = store.DATA_DIR, target: Path | None = None, keep: int = KEEP
) -> Path | None:
    """The new copy's path, or None when there is no archive yet. Older copies past `keep` go."""
    source = data_dir / "archive"
    if not source.is_dir():
        log.info("no archive at %s; nothing to back up", source)
        return None
    root = target or backup_dir()
    root.mkdir(parents=True, exist_ok=True)
    name = f"{PREFIX}{datetime.now(UTC).strftime(STAMP)}"
    copy, n = root / name, 1
    while copy.exists():  # two runs in one second
        copy, n = root / f"{name}-{n}", n + 1
    partial = root / f".{copy.name}.partial"
    shutil.rmtree(partial, ignore_errors=True)
    shutil.copytree(source, partial)
    partial.rename(copy)  # a copy that failed halfway never carries a real name
    stamped = sorted(p for p in root.iterdir() if p.is_dir() and COPY_NAME.match(p.name))
    for old in stamped[: max(len(stamped) - keep, 0)]:
        shutil.rmtree(old)
    return copy


def main() -> None:
    copy = run()
    print(f"archive copied to {copy}" if copy else "no archive to back up")


if __name__ == "__main__":
    main()
