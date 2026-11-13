"""Archive tables added after a server's archive already existed. `store.read_archive` refuses a
missing table while its siblings exist (`ArchiveMissing`), so the deploy (`ops/server/push.sh`)
writes each new one empty, once. It never replaces a table: the archive cannot be regenerated.

Usage: python -m fantasy.archive_tables
"""

from pathlib import Path

import polars as pl

from fantasy import store

# Add a table here in the change that registers it as a new archive table.
NEW_ARCHIVE_TABLES = ("market_values_history",)


def ensure(names: tuple[str, ...] = NEW_ARCHIVE_TABLES, data_dir: Path | None = None) -> list[str]:
    """Write each missing table in `names` empty; return the names written. An archive with no
    tables yet is left alone: there a missing table is a first run, while one empty table would
    make every other archive table read as missing."""
    written = []
    for name in names:
        path = store.table_path(name, "archive", data_dir)
        has_siblings = any(p.stem != name for p in path.parent.glob("*.parquet"))
        if path.exists() or not has_siblings:
            continue
        # shortcut: check-then-write, not exclusive; fine because the only writer of a new table
        # (its stage) raises ArchiveMissing until this has run.
        store.write_table(name, pl.DataFrame(schema=store.SCHEMAS[name]), "archive", data_dir)
        written.append(name)
    return written


def main() -> None:
    written = ensure()
    print(f"archive tables written empty: {', '.join(written) or 'none'}")


if __name__ == "__main__":
    main()
