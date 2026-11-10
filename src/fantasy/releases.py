"""Data releases: the raw and derived tables of one refresh, published all at once.

Layout (after `migrate`):
  data/releases/<id>/raw/*.parquet, derived/*.parquet   one folder per release
  data/current -> releases/<id>                         the one readers use (store.area_dir)
  data/archive, data/stat, and the download caches under data/raw (pbp/, the Sleeper players file)
  stay where they were: they are shared by every release.

A refresh builds the next release as a hard-link copy of the current one (no extra disk until a
table is rewritten; stages replace files atomically, never edit them in place), runs its stages
into it, and flips `current` only when every required stage succeeded. A failed run leaves the
current release serving.

Run: uv run python -m fantasy.releases migrate|prune
"""

import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from fantasy import store

RELEASES_DIR = "releases"
FIRST = "0001-initial"  # sorts before every run id, so pruning meets it first
KEEP = 5


def _link(path: Path, target: Path) -> None:
    """Point the symlink `path` at `target` (relative to its folder), atomically."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    tmp.symlink_to(target)
    os.replace(tmp, path)


def current_release(data_dir: Path | None = None) -> Path:
    link = store.resolve(data_dir) / store.CURRENT
    if not link.is_symlink():
        raise FileNotFoundError(f"{link} does not exist; run `python -m fantasy.releases migrate`")
    return link.resolve()


def migrate(data_dir: Path | None = None) -> bool:
    """Move the tables from data/raw and data/derived into the first release. Safe to repeat and to
    resume after an interruption. Returns whether anything changed."""
    root = store.resolve(data_dir)
    link = root / store.CURRENT
    release = link.resolve() if link.is_symlink() else root / RELEASES_DIR / FIRST
    # Link first, flip, then remove the old names, so a reader never finds a table missing.
    old_names: list[Path] = []
    for area in store.RELEASE_AREAS:
        (release / area).mkdir(parents=True, exist_ok=True)
        source = root / area
        for table in sorted(source.glob("*.parquet")) if source.is_dir() else []:
            destination = release / area / table.name
            if not destination.exists():
                os.link(table, destination)
            elif not destination.samefile(table):
                raise FileExistsError(f"{destination} exists; not overwriting it with {table}")
            old_names.append(table)
    changed = bool(old_names)
    if not link.is_symlink():
        _link(link, Path(RELEASES_DIR) / FIRST)
        changed = True
    for table in old_names:
        table.unlink()
    return changed


def start(run_id: str, data_dir: Path | None = None) -> Path:
    """A new release that starts as a hard-link copy of the current one."""
    root = store.resolve(data_dir)
    source = current_release(data_dir)
    new, attempt = root / RELEASES_DIR / run_id, 1
    while new.exists():  # two runs in one second
        attempt += 1
        new = root / RELEASES_DIR / f"{run_id}-{attempt}"
    new.mkdir(parents=True)
    try:
        for area in store.RELEASE_AREAS:
            shutil.copytree(
                source / area,
                new / area,
                copy_function=os.link,
                ignore=shutil.ignore_patterns("*.tmp"),  # leftovers of a crashed write
            )
    except BaseException:
        shutil.rmtree(new)
        raise
    return new


def publish(release: Path, data_dir: Path | None = None) -> None:
    """Make `release` the one readers see, in one atomic step."""
    root = store.resolve(data_dir)
    if release.parent.resolve() != (root / RELEASES_DIR).resolve():
        raise ValueError(f"{release} is not a release under {root / RELEASES_DIR}")
    _link(root / store.CURRENT, Path(RELEASES_DIR) / release.name)


def carry_over(table: str, area: str, release: Path, data_dir: Path | None = None) -> None:
    """Copy one table from `release` into the current release (the run records of a failed run,
    which must show even though that run is not published)."""
    name = f"{table}.parquet"
    destination = current_release(data_dir) / area / name
    tmp = destination.with_name(name + ".tmp")
    tmp.unlink(missing_ok=True)
    os.link(release / area / name, tmp)
    os.replace(tmp, destination)


def prune(data_dir: Path | None = None, keep: int = KEEP) -> list[Path]:
    """Delete all but the newest `keep` releases, and never the current one."""
    root = store.resolve(data_dir)
    live = current_release(data_dir)
    every = sorted(p for p in (root / RELEASES_DIR).iterdir() if p.is_dir())
    doomed = [p for p in every[: max(len(every) - keep, 0)] if p.resolve() != live]
    for release in doomed:
        shutil.rmtree(release)
    return doomed


def main(argv: Sequence[str]) -> int:
    commands = {"migrate": lambda: migrate(), "prune": lambda: bool(prune())}
    if len(argv) != 1 or argv[0] not in commands:
        print("usage: python -m fantasy.releases migrate|prune", file=sys.stderr)
        return 2
    print("changed" if commands[argv[0]]() else "nothing to do")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
