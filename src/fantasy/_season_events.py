"""Annotations for the season-odds chart: my trades, injuries to my starters and big weeks.

Takes `me`, my row from `data_api.leagues` (this module never calls `leagues`, see data_api).
Each event carries `run_at`, the saved simulation run whose odds first reflect it, or null when it
came before the first saved run. Only what the stored data supports: waivers are not annotated,
and an injury is a change of the Sleeper status to Out, IR or Doubtful between two daily snapshots.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from fantasy._engine import _read

SEVERE = frozenset({"Out", "IR", "Doubtful"})
BIG_WEEK_SDS = 1.0  # a week this many standard deviations above my mean
MIN_WEEKS = 3  # fewer completed weeks have no meaningful spread
COLUMNS = {"kind": pl.String, "when": pl.String, "run_at": pl.String, "label": pl.String}


def _utc(text: str) -> datetime:
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).isoformat(timespec="seconds")


def _names(data_dir: Path) -> dict[str, str]:
    players = _read("sleeper_players", data_dir).select("sleeper_id", "full_name")
    return {s: n for s, n in players.iter_rows() if n}


def _players(group: pl.DataFrame, action: str, names: dict[str, str]) -> str:
    ids = group.filter(pl.col("action") == action)["sleeper_id"].to_list()
    return ", ".join(names.get(i, "a player") for i in ids) or "nobody"


def _trades(
    me: dict[str, Any], names: dict[str, str], data_dir: Path
) -> list[tuple[str, str, str]]:
    rows = _read("transactions", data_dir).filter(
        (pl.col("league_id") == me["league_id"])
        & (pl.col("roster_id") == me["roster_id"])
        & (pl.col("type") == "trade")
        & (pl.col("status") == "complete")
    )
    out = []
    for _, group in rows.group_by("transaction_id"):
        at = datetime.fromtimestamp(group["created"][0] / 1000, UTC)
        got, sent = (_players(group, a, names) for a in ("add", "drop"))
        out.append(("trade", _iso(at), f"Trade: got {got}; sent {sent}"))
    return out


def _starters(me: dict[str, Any], data_dir: Path) -> set[str]:
    """My starters in the latest week with a lineup on record."""
    mine = _read("matchup_players", data_dir).filter(
        (pl.col("league_id") == me["league_id"])
        & (pl.col("roster_id") == me["roster_id"])
        & pl.col("is_starter")
    )
    if mine.is_empty():
        return set()
    return set(mine.filter(pl.col("week") == mine["week"].max())["sleeper_id"])


def _injuries(
    me: dict[str, Any], names: dict[str, str], data_dir: Path
) -> list[tuple[str, str, str]]:
    snaps = _read("sleeper_player_status", data_dir, area="archive")
    starters = _starters(me, data_dir)
    if snaps.is_empty() or not starters:
        return []
    snaps = snaps.filter(pl.col("sleeper_id").is_in(starters))
    stamps = sorted(snaps["fetched_at"].drop_nulls().unique(), key=_utc)
    status = {
        (r["sleeper_id"], r["fetched_at"]): r["injury_status"]
        for r in snaps.select("sleeper_id", "fetched_at", "injury_status").iter_rows(named=True)
    }
    out = []
    for before, after in zip(stamps, stamps[1:], strict=False):
        for sid in sorted(starters):
            was, now = status.get((sid, before)), status.get((sid, after))
            if now in SEVERE and was != now:
                label = f"{names.get(sid, 'A starter')} listed {now}"
                out.append(("injury", _iso(_utc(after)), label))
    return out


def _big_weeks(me: dict[str, Any], data_dir: Path) -> list[tuple[str, int, str]]:
    played = _read("matchups", data_dir).filter(
        (pl.col("league_id") == me["league_id"])
        & (pl.col("roster_id") == me["roster_id"])
        & (pl.col("week") < me["current_week"])
        & (pl.col("points") > 0)
    )
    if played.height < MIN_WEEKS:
        return []
    mean, sd = float(played["points"].mean()), float(played["points"].std() or 0.0)  # type: ignore[arg-type]
    big = played.filter(pl.col("points") >= mean + BIG_WEEK_SDS * sd).sort("week")
    return [
        ("big_week", int(w), f"Week {w}: {p:.1f} points, {p - mean:.1f} above your average")
        for w, p in big.select("week", "points").iter_rows()
    ]


def season_events(me: dict[str, Any], data_dir: Path) -> pl.DataFrame:
    """Events for the chart, oldest first."""
    history = _read("sim_season_history", data_dir, area="archive").filter(
        pl.col("league_id") == me["league_id"]
    )
    runs = sorted(
        {(r, w) for r, w in history.select("run_at", "as_of_week").iter_rows()},
        key=lambda x: _utc(x[0]),
    )

    def after_time(when: str) -> str | None:
        if runs and _utc(when) < _utc(runs[0][0]):
            return None  # before the first saved run: the chart has no point for it
        return next((r for r, _ in runs if _utc(r) >= _utc(when)), None)

    def after_week(week: int) -> str | None:
        if runs and runs[0][1] > week:
            return None  # played before the first saved run: no step on the chart to explain
        return next((r for r, w in runs if w > week), None)

    names = _names(data_dir)
    rows = [
        (kind, when, after_time(when), label)
        for kind, when, label in [*_trades(me, names, data_dir), *_injuries(me, names, data_dir)]
    ]
    for kind, week, label in _big_weeks(me, data_dir):
        run = after_week(week)
        rows.append((kind, run or "", run, label))  # no run to place it on: dropped below
    rows = [r for r in rows if r[1]]
    return pl.DataFrame(sorted(rows, key=lambda r: r[1]), schema=COLUMNS, orient="row")
