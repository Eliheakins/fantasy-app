"""Annotations for the season-odds chart: my trades, injuries to my starters and big weeks.

Takes `me`, my row from `data_api.leagues` (this module never calls `leagues`, see data_api).
Each event carries `run_at`, the saved simulation run whose odds first reflect it, or null when it
came before the first saved run. Only what the stored data supports: waivers are not annotated,
and an injury is a change of the Sleeper status to Out, IR or Doubtful between two daily snapshots.
"""

from bisect import bisect_left
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from fantasy import store

SEVERE = frozenset({"Out", "IR", "Doubtful"})
BIG_WEEK_SDS = 1.0  # a week this many standard deviations above my mean
MIN_WEEKS = 3  # fewer completed weeks have no meaningful spread
COLUMNS = {"kind": pl.String, "when": pl.String, "run_at": pl.String, "label": pl.String}


def _utc(text: str) -> datetime:
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _try_utc(text: str | None) -> datetime | None:
    """The time, or None for a missing or malformed timestamp (such a row is skipped)."""
    try:
        return None if text is None else _utc(text)
    except ValueError:
        return None


def _scan(name: str, area: str, data_dir: Path, columns: list[str], where: pl.Expr) -> pl.DataFrame:
    """Only the needed columns and rows of an optional table; empty if it is not there yet."""
    path = store.table_path(name, area, data_dir)
    if not path.exists():
        return pl.DataFrame(schema={c: store.SCHEMAS[name][c] for c in columns})
    return pl.scan_parquet(path).filter(where).select(columns).collect()


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).isoformat(timespec="seconds")


def _names(ids: set[str], data_dir: Path) -> dict[str, str]:
    players = _scan(
        "sleeper_players", "raw", data_dir, ["sleeper_id", "full_name"],
        pl.col("sleeper_id").is_in(ids),
    )  # fmt: skip
    return {s: n for s, n in players.iter_rows() if n}


Trade = tuple[str, list[str], list[str]]  # when (ISO), sleeper ids added, sleeper ids sent


def _trades(me: dict[str, Any], data_dir: Path) -> list[Trade]:
    rows = _scan(
        "transactions", "raw", data_dir,
        ["transaction_id", "created", "action", "sleeper_id"],
        (pl.col("league_id") == me["league_id"])
        & (pl.col("roster_id") == me["roster_id"])
        & (pl.col("type") == "trade")
        & (pl.col("status") == "complete"),
    )  # fmt: skip
    out: list[Trade] = []
    for _, group in rows.group_by("transaction_id"):
        at = datetime.fromtimestamp(group["created"][0] / 1000, UTC)
        side = {
            a: group.filter(pl.col("action") == a)["sleeper_id"].to_list() for a in ("add", "drop")
        }
        out.append((_iso(at), side["add"], side["drop"]))
    return out


def _trade_label(trade: Trade, names: dict[str, str]) -> str:
    def who(ids: list[str]) -> str:
        return ", ".join(names.get(i, "a player") for i in ids) or "nobody"

    return f"Trade: got {who(trade[1])}; sent {who(trade[2])}"


def _starters(me: dict[str, Any], data_dir: Path) -> set[str]:
    """My starters in the latest week with a lineup on record."""
    mine = _scan(
        "matchup_players", "raw", data_dir, ["week", "sleeper_id"],
        (pl.col("league_id") == me["league_id"])
        & (pl.col("roster_id") == me["roster_id"])
        & pl.col("is_starter"),
    )  # fmt: skip
    if mine.is_empty():
        return set()
    return set(mine.filter(pl.col("week") == mine["week"].max())["sleeper_id"])


def _injuries(
    me: dict[str, Any], starters: set[str], names: dict[str, str], data_dir: Path
) -> list[tuple[str, str, str]]:
    if not starters:
        return []
    snaps = _scan(
        "sleeper_player_status", "archive", data_dir,
        ["sleeper_id", "fetched_at", "injury_status"], pl.col("sleeper_id").is_in(starters),
    )  # fmt: skip
    times = {t: at for t in snaps["fetched_at"].drop_nulls().unique() if (at := _try_utc(t))}
    stamps = sorted(times, key=times.__getitem__)
    status = {
        (r["sleeper_id"], r["fetched_at"]): r["injury_status"] for r in snaps.iter_rows(named=True)
    }
    out = []
    for before, after in zip(stamps, stamps[1:], strict=False):
        for sid in sorted(starters):
            was, now = status.get((sid, before)), status.get((sid, after))
            if now in SEVERE and was != now:
                out.append(
                    ("injury", _iso(times[after]), f"{names.get(sid, 'A starter')} listed {now}")
                )
    return out


def _big_weeks(me: dict[str, Any], data_dir: Path) -> list[tuple[str, int, str]]:
    """Weeks at least BIG_WEEK_SDS above the mean of my other completed weeks."""
    played = _scan(
        "matchups", "raw", data_dir, ["week", "points"],
        (pl.col("league_id") == me["league_id"])
        & (pl.col("roster_id") == me["roster_id"])
        & (pl.col("week") < me["current_week"])
        & (pl.col("points") > 0),
    ).sort("week")  # fmt: skip
    scores = list(played.iter_rows())
    out = []
    for week, points in scores:
        others = pl.Series([p for w, p in scores if w != week])
        if len(others) < MIN_WEEKS:
            return []
        mean, sd = float(others.mean()), float(others.std() or 0.0)  # type: ignore[arg-type]
        if points >= mean + BIG_WEEK_SDS * sd:
            out.append(
                (
                    "big_week",
                    int(week),
                    f"Week {week}: {points:.1f} points, {points - mean:.1f} above your usual",
                )
            )
    return out


def season_events(me: dict[str, Any], data_dir: Path) -> pl.DataFrame:
    """Events for the chart, oldest first."""
    history = _scan(
        "sim_season_history", "archive", data_dir, ["run_at", "as_of_week"],
        pl.col("league_id") == me["league_id"],
    )  # fmt: skip
    runs = sorted({(at, r, w) for r, w in history.iter_rows() if (at := _try_utc(r)) is not None})
    times = [at for at, _, _ in runs]

    def after_time(when: datetime) -> str | None:
        i = bisect_left(times, when)
        return None if i == 0 or i == len(runs) else runs[i][1]  # before the first run: no point

    def after_week(week: int) -> str | None:
        if runs and runs[0][2] > week:
            return None  # played before the first saved run: no step on the chart to explain
        return next((r for _, r, w in runs if w > week), None)

    starters = _starters(me, data_dir)
    trades = _trades(me, data_dir)
    names = _names(starters | {i for _, got, sent in trades for i in [*got, *sent]}, data_dir)
    found = [("trade", when, _trade_label(t, names)) for t in trades for when in [t[0]]]
    found += _injuries(me, starters, names, data_dir)
    rows: list[tuple[str, datetime, str | None, str]] = []
    for kind, when, label in found:
        if (at := _try_utc(when)) is not None:
            rows.append((kind, at, after_time(at), label))
    for kind, week, label in _big_weeks(me, data_dir):
        run = after_week(week)
        if run is not None and (at := _try_utc(run)) is not None:
            rows.append((kind, at, run, label))
    ordered = sorted(rows, key=lambda r: r[1])
    return pl.DataFrame(
        [(k, _iso(at), run, label) for k, at, run, label in ordered], schema=COLUMNS, orient="row"
    )
