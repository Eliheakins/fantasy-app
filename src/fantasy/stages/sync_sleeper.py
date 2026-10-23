"""Sync Sleeper leagues, rosters, matchups, transactions, trending and players to parquet.

Run: uv run python -m fantasy.stages.sync_sleeper
"""

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from fantasy import store
from fantasy.config import Config, load_config
from fantasy.sources.sleeper import fetch

PLAYERS_CACHE = store.DATA_DIR / "raw" / "sleeper_players_cache.json"
PLAYERS_TTL_SECONDS = 24 * 3600  # Sleeper asks for at most one players pull a day
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}
LAST_WEEK = 17
EMPTY_SLOT = "0"


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _frame(name: str, rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=store.SCHEMAS[name])


def load_players(
    cache: Path = PLAYERS_CACHE, now: float | None = None
) -> dict[str, dict[str, Any]]:
    now = time.time() if now is None else now
    if cache.exists() and now - cache.stat().st_mtime < PLAYERS_TTL_SECONDS:
        return json.loads(cache.read_text())
    data: dict[str, dict[str, Any]] = fetch("/players/nfl")
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, cache)
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
    rows = []
    for r in rosters:
        starters = {p for p in (r.get("starters") or []) if p != EMPTY_SLOT}
        reserve = set(r.get("reserve") or [])
        for pid in r.get("players") or []:
            rows.append(
                {
                    "league_id": league_id,
                    "roster_id": _int(r["roster_id"]),
                    "sleeper_id": str(pid),
                    "is_starter": pid in starters,
                    "is_ir": pid in reserve,
                }
            )
    return _frame("rosters", rows)


def matchups_frames(
    league_id: str, week: int, matchups: list[dict[str, Any]]
) -> tuple[pl.DataFrame, pl.DataFrame]:
    teams, players = [], []
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
        for pid in m.get("players") or []:
            players.append(
                {
                    "league_id": league_id,
                    "week": week,
                    "roster_id": roster_id,
                    "sleeper_id": str(pid),
                    "points": points.get(pid),
                    "is_starter": pid in starters,
                }
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


def run(cfg: Config) -> dict[str, int]:
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    league_tables = ("leagues", "league_teams", "rosters", "matchups", "matchup_players")
    out: dict[str, list[pl.DataFrame]] = {k: [] for k in (*league_tables, "transactions")}
    for key, league_id in cfg.leagues.items():
        lg = fetch(f"/league/{league_id}")
        rosters = fetch(f"/league/{league_id}/rosters")
        users = fetch(f"/league/{league_id}/users")
        out["leagues"].append(league_frame(key, lg))
        out["league_teams"].append(teams_frame(league_id, rosters, users, cfg.user_id))
        out["rosters"].append(rosters_frame(league_id, rosters))
        for week in range(1, LAST_WEEK + 1):
            raw_matchups = fetch(f"/league/{league_id}/matchups/{week}")
            teams, players = matchups_frames(league_id, week, raw_matchups)
            out["matchups"].append(teams)
            out["matchup_players"].append(players)
        current = _int((lg.get("settings") or {}).get("leg")) or 1
        for week in range(1, current + 1):
            txs = fetch(f"/league/{league_id}/transactions/{week}")
            out["transactions"].append(transactions_frame(league_id, week, txs))

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
    return counts


def main() -> None:
    for name, rows in run(load_config()).items():
        print(f"{name}: {rows} rows")


if __name__ == "__main__":
    main()
