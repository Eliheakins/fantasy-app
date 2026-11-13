"""Archive a daily snapshot of Sleeper's status fields for skill players.

Sleeper serves only the current injury notes, practice status, depth chart order and news
timestamps, and sync_sleeper keeps none of them, so a history exists only if it is kept here, for
research/news_residual_check.py. Reads the players file sync_sleeper caches (no API call), so run
it after sync_sleeper. At most one snapshot per calendar day (UTC) of the file's fetch; fetched_at
is the file's fetch time, so a file kept from yesterday is not stamped as today's. Fails soft: a
missing or broken file logs a warning and the rest of `make refresh` runs on.

RotoWire's NFL news RSS is not archived: its terms forbid archiving content by automated means
(Article VI, https://www.rotowire.com/termsandconditions.php, checked 2026-10-26).

Run: uv run python -m fantasy.stages.news_archive
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from fantasy import store
from fantasy._runs import note_soft_failure
from fantasy.stages.sync_sleeper import PLAYERS_CACHE, as_int

TABLE = "sleeper_player_status"
INT_FIELDS = {"depth_chart_order", "news_updated"}


def _str(value: Any) -> str | None:
    return None if value is None else str(value)


def status_frame(raw: dict[str, dict[str, Any]], fetched_at: str) -> pl.DataFrame:
    """One row per skill player in the players file, with the archived fields."""
    fields = [c for c in store.SCHEMAS[TABLE] if c not in ("sleeper_id", "fetched_at")]
    rows = [
        {
            "sleeper_id": str(player_id),
            **{f: (as_int if f in INT_FIELDS else _str)(p.get(f)) for f in fields},
            "fetched_at": fetched_at,
        }
        for player_id, p in raw.items()
        if p.get("position") in store.SKILL
    ]
    return pl.DataFrame(rows, schema=store.SCHEMAS[TABLE])


def run(data_dir: Path | None = None) -> int:
    """Append today's snapshot unless one from the file's fetch day exists; returns rows added."""
    cache = store.resolve(data_dir) / "raw" / PLAYERS_CACHE.name
    try:
        fetched = datetime.fromtimestamp(cache.stat().st_mtime, UTC)
        new = status_frame(json.loads(cache.read_text()), fetched.isoformat(timespec="seconds"))
        old = store.read_archive(TABLE, data_dir)
        if old["fetched_at"].str.starts_with(fetched.date().isoformat()).any():
            print(f"{TABLE}: a snapshot of the {fetched.date()} players file is already archived")
            return 0
        store.write_table(TABLE, pl.concat([old, new]), "archive", data_dir)
    except Exception as err:  # noqa: BLE001 - fail soft: the archive is optional, refresh runs on
        print(f"warning: {TABLE} snapshot skipped: {err!r}")
        note_soft_failure(repr(err))
        return 0
    return new.height


if __name__ == "__main__":
    print(f"{run()} rows added to the archive")
