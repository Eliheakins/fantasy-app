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

import polars as pl

from fantasy import data_api, store

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
    """One league's rows: the best waiver adds by playoff odds, then the first found trades."""
    top = waivers.sort("playoff_delta", descending=True, nulls_last=True).head(TOP_WAIVERS)
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


def run(
    data_dir: Path = store.DATA_DIR,
    waivers: Finder | None = None,
    trades: Finder | None = None,
    now: str | None = None,
) -> int:
    """Rows written. `waivers` and `trades` take a league key (the real ones by default)."""
    waivers = waivers or data_api.waivers
    trades = trades or data_api.find_trades
    created = now or datetime.now(UTC).isoformat(timespec="seconds")
    frames = []
    for league in data_api.leagues(data_dir).iter_rows(named=True):
        try:
            found: pl.DataFrame | None = trades(league["league_key"])
        except ValueError as past:  # the trade deadline has passed
            log.info("no trade ideas for %s: %s", league["league_key"], past)
            found = None
        frames.append(
            ideas(
                league["league_id"],
                int(league["current_week"]),
                created,
                waivers(league["league_key"]),
                found,
            )
        )
    table = pl.concat(frames) if frames else pl.DataFrame(schema=store.SCHEMAS["move_ideas"])
    store.write_table("move_ideas", table, "derived", data_dir)
    return table.height


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        print(f"{run()} move ideas stored")
    except Exception:
        log.exception("digest stage failed; previous move ideas left in place")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
