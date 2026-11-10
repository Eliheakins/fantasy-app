"""Sync Sleeper leagues, rosters, matchups, transactions, trending and players to parquet.

Run: uv run python -m fantasy.stages.sync_sleeper
"""

import json
import logging
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from fantasy import store
from fantasy.auth import accounts, leagues
from fantasy.config import Config, load_config
from fantasy.sources.sleeper import SleeperError, fetch
from nfl_stat.pipeline.atomic import atomic_path

log = logging.getLogger(__name__)
PLAYERS_CACHE = store.DATA_DIR / "raw" / "sleeper_players_cache.json"
PLAYERS_TTL_SECONDS = 24 * 3600  # Sleeper asks for at most one players pull a day
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}
LAST_WEEK = 17
EMPTY_SLOT = "0"
MIN_PLAYERS = 1000  # the real file has about 11,000 entries


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _frame(name: str, rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=store.SCHEMAS[name])


def check_players(data: Any) -> None:
    """Raise before an empty, truncated or error-object response is cached for a day."""
    if not isinstance(data, dict) or len(data) < MIN_PLAYERS:
        size = len(data) if hasattr(data, "__len__") else "?"
        raise RuntimeError(
            f"Sleeper players file looks wrong: {type(data).__name__}, {size} entries"
        )
    sample = next(iter(data.values()))
    if not isinstance(sample, dict) or "position" not in sample:
        raise RuntimeError("Sleeper players file entries do not have the expected shape")


def load_players(
    cache: Path = PLAYERS_CACHE, now: float | None = None
) -> dict[str, dict[str, Any]]:
    now = time.time() if now is None else now
    if cache.exists() and now - cache.stat().st_mtime < PLAYERS_TTL_SECONDS:
        cached: dict[str, dict[str, Any]] = json.loads(cache.read_text())
        return cached
    data: dict[str, dict[str, Any]] = fetch("/players/nfl")
    check_players(data)
    cache.parent.mkdir(parents=True, exist_ok=True)
    with atomic_path(cache) as tmp:
        tmp.write_text(json.dumps(data))
    return data


def players_frame(raw: dict[str, dict[str, Any]]) -> pl.DataFrame:
    rows = []
    for player_id, p in raw.items():
        if p.get("position") not in FANTASY_POSITIONS:
            continue
        name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        rows.append(
            {
                "sleeper_id": str(player_id),
                "full_name": name or str(player_id),
                "position": p["position"],
                "team": p.get("team"),
                "status": p.get("status"),
                "injury_status": p.get("injury_status"),
                "age": _int(p.get("age")),
                "years_exp": _int(p.get("years_exp")),
                "gsis_id": p.get("gsis_id"),
                "fantasy_positions": p.get("fantasy_positions") or [],
            }
        )
    return _frame("sleeper_players", rows)


def league_frame(league_key: str, lg: dict[str, Any]) -> pl.DataFrame:
    s = lg.get("settings") or {}
    row = {
        "league_key": league_key,
        "league_id": str(lg["league_id"]),
        "name": lg.get("name"),
        "season": _int(lg.get("season")),
        "status": lg.get("status"),
        "num_teams": _int(s.get("num_teams")),
        "current_week": _int(s.get("leg")),
        "playoff_week_start": _int(s.get("playoff_week_start")),
        "playoff_teams": _int(s.get("playoff_teams")),
        "playoff_seed_type": _int(s.get("playoff_seed_type")),
        "trade_deadline": _int(s.get("trade_deadline")),
        "waiver_type": _int(s.get("waiver_type")),
        "roster_positions": lg.get("roster_positions") or [],
        "scoring_settings": json.dumps(lg.get("scoring_settings") or {}, sort_keys=True),
        "settings": json.dumps(s, sort_keys=True),
    }
    return _frame("leagues", [row])


def teams_frame(
    league_id: str, rosters: list[dict[str, Any]], users: list[dict[str, Any]], my_user_id: str
) -> pl.DataFrame:
    names = {
        u["user_id"]: (u.get("metadata") or {}).get("team_name") or u.get("display_name", "")
        for u in users
    }
    rows = []
    for r in rosters:
        s = r.get("settings") or {}
        owner = r.get("owner_id")
        rows.append(
            {
                "league_id": league_id,
                "roster_id": _int(r["roster_id"]),
                "owner_id": str(owner or ""),
                "team_name": names.get(owner, ""),
                "is_me": owner == my_user_id,
                "wins": _int(s.get("wins")) or 0,
                "losses": _int(s.get("losses")) or 0,
                "ties": _int(s.get("ties")) or 0,
                "points_for": (s.get("fpts") or 0) + (s.get("fpts_decimal") or 0) / 100,
                "points_against": (s.get("fpts_against") or 0)
                + (s.get("fpts_against_decimal") or 0) / 100,
            }
        )
    return _frame("league_teams", rows)


def rosters_frame(league_id: str, rosters: list[dict[str, Any]]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for r in rosters:
        starters = {p for p in (r.get("starters") or []) if p != EMPTY_SLOT}
        reserve = set(r.get("reserve") or [])
        rows.extend(
            {
                "league_id": league_id,
                "roster_id": _int(r["roster_id"]),
                "sleeper_id": str(pid),
                "is_starter": pid in starters,
                "is_ir": pid in reserve,
            }
            for pid in r.get("players") or []
        )
    return _frame("rosters", rows)


def matchups_frames(
    league_id: str, week: int, matchups: list[dict[str, Any]]
) -> tuple[pl.DataFrame, pl.DataFrame]:
    teams: list[dict[str, Any]] = []
    players: list[dict[str, Any]] = []
    for m in matchups:
        roster_id = _int(m["roster_id"])
        teams.append(
            {
                "league_id": league_id,
                "week": week,
                "roster_id": roster_id,
                "matchup_id": _int(m.get("matchup_id")),
                "points": m.get("points"),
            }
        )
        starters = {p for p in (m.get("starters") or []) if p != EMPTY_SLOT}
        points = m.get("players_points") or {}
        players.extend(
            {
                "league_id": league_id,
                "week": week,
                "roster_id": roster_id,
                "sleeper_id": str(pid),
                "points": points.get(pid),
                "is_starter": pid in starters,
            }
            for pid in m.get("players") or []
        )
    return _frame("matchups", teams), _frame("matchup_players", players)


def transactions_frame(league_id: str, week: int, txs: list[dict[str, Any]]) -> pl.DataFrame:
    rows = []
    for t in txs:
        bid = _int((t.get("settings") or {}).get("waiver_bid"))
        for action, key in (("add", "adds"), ("drop", "drops")):
            for pid, roster_id in (t.get(key) or {}).items():
                rows.append(
                    {
                        "league_id": league_id,
                        "week": week,
                        "transaction_id": str(t["transaction_id"]),
                        "type": t.get("type"),
                        "status": t.get("status"),
                        "created": _int(t.get("created")),
                        "roster_id": _int(roster_id),
                        "sleeper_id": str(pid),
                        "action": action,
                        "waiver_bid": bid,
                    }
                )
    return _frame("transactions", rows)


def trending_frame(fetched_at: str, kind: str, items: list[dict[str, Any]]) -> pl.DataFrame:
    rows = [
        {
            "fetched_at": fetched_at,
            "kind": kind,
            "sleeper_id": str(i["player_id"]),
            "count": _int(i.get("count")),
        }
        for i in items
    ]
    return _frame("trending", rows)


def _concat(name: str, frames: list[pl.DataFrame]) -> pl.DataFrame:
    return pl.concat(frames) if frames else _frame(name, [])


LEAGUE_TABLES = (
    "leagues",
    "league_teams",
    "rosters",
    "matchups",
    "matchup_players",
    "transactions",
)
# What a league added by someone else can fail with: Sleeper refusing it or not answering, no
# rosters, or a payload that is not the shape we read. Anything else is a bug: stop the run.
ISOLATED_ERRORS = (SleeperError, RuntimeError, KeyError, ValueError, TypeError)
MAX_REASON_CHARS = 200

Registered = Sequence[tuple[str, str]]  # (league key, league id) of leagues people added
Report = Callable[[str, str | None], None]  # league id, and why the sync failed (None: it worked)


def _league_frames(
    key: str, league_id: str, my_user_id: str, strict: bool
) -> dict[str, list[pl.DataFrame]]:
    """Every table's rows for one league. `strict` (the owner's leagues in config.toml) also
    insists that one roster is the owner's; a league someone else added has none."""
    lg = fetch(f"/league/{league_id}")
    rosters = fetch(f"/league/{league_id}/rosters")
    users = fetch(f"/league/{league_id}/users")
    teams = teams_frame(league_id, rosters, users, my_user_id)
    if not rosters:
        raise RuntimeError(f"Sleeper returned no rosters for league {key} ({league_id})")
    if strict and not teams["is_me"].any():
        raise RuntimeError(f"no roster in league {key} belongs to user_id {my_user_id}")
    frames: dict[str, list[pl.DataFrame]] = {name: [] for name in LEAGUE_TABLES}
    frames["leagues"].append(league_frame(key, lg))
    frames["league_teams"].append(teams)
    frames["rosters"].append(rosters_frame(league_id, rosters))
    for week in range(1, LAST_WEEK + 1):
        raw_matchups = fetch(f"/league/{league_id}/matchups/{week}")
        week_teams, week_players = matchups_frames(league_id, week, raw_matchups)
        frames["matchups"].append(week_teams)
        frames["matchup_players"].append(week_players)
    current = _int((lg.get("settings") or {}).get("leg")) or 1
    for week in range(1, current + 1):
        txs = fetch(f"/league/{league_id}/transactions/{week}")
        frames["transactions"].append(transactions_frame(league_id, week, txs))
    return frames


def _reason(err: Exception) -> str:
    if isinstance(err, SleeperError):
        return "Sleeper refused this league or did not answer."
    return f"The league could not be read: {err}"[:MAX_REASON_CHARS]


def registered_leagues() -> Registered:
    """The leagues people added by username, from the accounts file (none if there is no file)."""
    if not accounts.db_path().exists():
        return []
    with accounts.open_db() as conn:
        return [(r["league_key"], r["league_id"]) for r in leagues.registered(conn)]


def record_outcomes(outcomes: Sequence[tuple[str, str | None]]) -> None:
    """Tell the accounts file how each added league went, for its owner to see."""
    if not outcomes:
        return
    now = datetime.now(UTC)
    with accounts.open_db() as conn:
        for league_id, error in outcomes:
            leagues.mark(conn, league_id, error, now)


def run(
    cfg: Config, registered: Registered | None = None, report: Report | None = None
) -> dict[str, int]:
    """Pull every configured and registered league, trending adds/drops and the players file.

    Needs the network (Sleeper, read-only); no earlier stage. A failing configured league stops
    the run, a failing registered one is recorded through `report` (default `record_outcomes`) and
    skipped. Writes the league tables (`leagues`, teams, rosters, matchups, transactions),
    `trending` and `sleeper_players` to the raw area, each replaced whole. Returns row counts by
    table.
    """
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    out: dict[str, list[pl.DataFrame]] = {name: [] for name in LEAGUE_TABLES}
    outcomes: list[tuple[str, str | None]] = []

    def take(frames: dict[str, list[pl.DataFrame]]) -> None:
        for name, parts in frames.items():
            out[name].extend(parts)

    for key, league_id in cfg.leagues.items():  # the owner's: a failure stops the run
        take(_league_frames(key, league_id, cfg.user_id, strict=True))
    configured = set(cfg.leagues.values())
    for key, league_id in registered_leagues() if registered is None else registered:
        if league_id in configured:  # already synced above; do not read it twice
            outcomes.append((league_id, None))
            continue
        try:
            take(_league_frames(key, league_id, cfg.user_id, strict=False))
        except ISOLATED_ERRORS as err:  # one bad league must not stop everyone else's refresh
            log.exception("league %s not synced", league_id)  # the traceback shows a code bug
            outcomes.append((league_id, _reason(err)))
        else:
            outcomes.append((league_id, None))

    out["trending"] = [
        trending_frame(fetched_at, kind, fetch(f"/players/nfl/trending/{kind}", {"limit": 50}))
        for kind in ("add", "drop")
    ]
    out["sleeper_players"] = [players_frame(load_players())]

    counts = {}
    for name, frames in out.items():
        df = _concat(name, frames)
        store.write_table(name, df, area="raw")
        counts[name] = df.height
    if report is None:
        record_outcomes(outcomes)
    else:
        for league_id, error in outcomes:
            report(league_id, error)
    return counts


def sync_week(week: int, data_dir: Path | None = None) -> int:
    """Re-fetch one week's matchups for every league and replace those rows (two API calls).

    Used for live scores during games; the full sync stays `run`. Returns the player rows."""
    league_ids = store.read_table("leagues", "raw", data_dir)["league_id"].to_list()
    fetched = [
        matchups_frames(lid, week, fetch(f"/league/{lid}/matchups/{week}")) for lid in league_ids
    ]
    # build both replacements before writing either, so a failure cannot leave one updated
    merged = {}
    for name, index in (("matchups", 0), ("matchup_players", 1)):
        old = store.read_table(name, "raw", data_dir)
        kept = old.filter(~((pl.col("week") == week) & pl.col("league_id").is_in(league_ids)))
        merged[name] = pl.concat([kept, *(f[index] for f in fetched)])
    for name, df in merged.items():
        store.write_table(name, df, "raw", data_dir)
    return sum(f[1].height for f in fetched)


def main() -> None:
    for name, rows in run(load_config()).items():
        print(f"{name}: {rows} rows")


if __name__ == "__main__":
    main()
