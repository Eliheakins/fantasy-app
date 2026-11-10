"""Store my top waiver adds and trade ideas for the weekly digest page (table `move_ideas`).

Runs after `simulate` in `make refresh`. Waivers re-simulate up to 15 adds and `find_trades` goes
over every roster, so the page reads this table instead of computing at load. Live ticks do not
run it. It never fails the refresh: after the trade deadline it writes no trade rows, and any other
error is logged and leaves the previous table in place. Ideas are for my team only (Sleeper's
`is_me`).
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from fantasy import data_api, store
from fantasy._runs import note_soft_failure

log = logging.getLogger(__name__)
TOP_WAIVERS = 5
TOP_TRADES = 5
Finder = Callable[[str], pl.DataFrame]


def ideas(
    league_id: str,
    as_of_week: int,
    created_at: str,
    waivers: pl.DataFrame,
    trades: pl.DataFrame | None,
) -> pl.DataFrame:
    """One league's rows: the best waiver adds by rest-of-season points (the Waivers page order;
    it won more games than ranking by next-week points or form, research/waiver_rule_check.py),
    then the first found trades."""
    top = waivers.sort("delta_points", descending=True, nulls_last=True).head(TOP_WAIVERS)
    rows = [
        {
            "kind": "waiver", "partner": None, "give": r["drop_name"], "get": r["full_name"],
            "give_ids": [], "get_ids": [r["gsis_id"]], "playoff_delta": r["playoff_delta"],
            "title_delta": r["title_delta"], "se_title": r["se_title"],
            "delta_points": r["delta_points"],
        }
        for r in top.iter_rows(named=True)
    ]  # fmt: skip
    found = None if trades is None else trades.head(TOP_TRADES)
    rows += [
        {
            "kind": "trade", "partner": r["partner"], "give": r["give"], "get": r["get"],
            "give_ids": r["give_ids"], "get_ids": r["get_ids"], "playoff_delta": r["my_playoff"],
            "title_delta": r["my_title"], "se_title": r["se_title"], "delta_points": None,
        }
        for r in (found.iter_rows(named=True) if found is not None else [])
    ]  # fmt: skip
    seen: dict[str, int] = {}
    numbered = []
    for r in rows:
        seen[r["kind"]] = seen.get(r["kind"], 0) + 1
        numbered.append(
            {"league_id": league_id, "created_at": created_at, "as_of_week": as_of_week}
            | r
            | {"rank": seen[r["kind"]]}
        )
    return pl.DataFrame(numbered, schema=store.SCHEMAS["move_ideas"])


def league_ideas(
    league: dict[str, Any], waivers: Finder, trades: Finder, created: str
) -> pl.DataFrame:
    """The stored ideas for one league. After the trade deadline there are no trade rows."""
    try:
        found: pl.DataFrame | None = trades(league["league_key"])
    except ValueError as past:  # the trade deadline has passed
        log.info("no trade ideas for %s: %s", league["league_key"], past)
        found = None
    return ideas(
        league["league_id"],
        int(league["current_week"]),
        created,
        waivers(league["league_key"]),
        found,
    )


def _previous_ideas(league_ids: list[str], data_dir: Path | None) -> list[pl.DataFrame]:
    if not league_ids:
        return []
    try:
        old = store.read_table("move_ideas", "derived", data_dir)
    except FileNotFoundError:
        return []
    return [old.filter(pl.col("league_id").is_in(league_ids))]


def run(
    data_dir: Path | None = None,
    waivers: Finder | None = None,
    trades: Finder | None = None,
    now: str | None = None,
) -> int:
    """Rows written. `waivers` and `trades` take a league key (the real ones by default)."""
    waivers = waivers or data_api.waivers
    trades = trades or data_api.find_trades
    created = now or datetime.now(UTC).isoformat(timespec="seconds")
    frames = []
    failed: list[str] = []
    for league in data_api.leagues(data_dir).iter_rows(named=True):
        if league["roster_id"] is None:  # a league added by someone else: no team of mine in it
            log.info("no ideas for %s: no team of mine", league["league_key"])
            continue
        try:
            frames.append(league_ideas(league, waivers, trades, created))
        except Exception as err:
            log.exception("no ideas for %s", league["league_key"])
            note_soft_failure(f"digest skipped {league['league_key']}: {err!r}")
            failed.append(league["league_id"])
    frames.extend(_previous_ideas(failed, data_dir))  # a failed league keeps its last ideas
    table = pl.concat(frames) if frames else pl.DataFrame(schema=store.SCHEMAS["move_ideas"])
    store.write_table("move_ideas", table, "derived", data_dir)
    return table.height


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        print(f"{run()} move ideas stored")
    except Exception as err:
        log.exception("digest stage failed; previous move ideas left in place")
        note_soft_failure(repr(err))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
