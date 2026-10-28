"""Copy `data/archive/` to a dated folder outside the repo. The archive cannot be regenerated.

`make refresh` runs it first. The folder is `~/fantasy-app-backups` unless FANTASY_BACKUP_DIR is
set; the newest KEEP copies stay. The archive holds private-use data, so keep the folder out of
any repository or shared drive.
"""

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from fantasy import store

log = logging.getLogger(__name__)
KEEP = 30
PREFIX = "archive-"
STAMP = "%Y%m%d-%H%M%S"


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
    copy = root / f"{PREFIX}{datetime.now().strftime(STAMP)}"
    shutil.copytree(source, copy)
    stamped = sorted(
        p for p in root.iterdir() if p.is_dir() and p.name.startswith(PREFIX)
    )  # the stamp sorts oldest first
    for old in stamped[: max(len(stamped) - keep, 0)]:
        shutil.rmtree(old)
    return copy


def main() -> None:
    copy = run()
    print(f"archive copied to {copy}" if copy else "no archive to back up")


if __name__ == "__main__":
    main()
