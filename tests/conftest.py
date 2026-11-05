"""Shared fixtures: a fake API store, a client over it, and a small league store."""

from collections.abc import Iterator
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient
from store_fixture import LID, PAIRS, POSITIONS, SCORES, _engine_store, write_rows

from fantasy import _engine, api, store

CSRF_HEADER = {"X-Requested-With": "fantasy-app"}


@pytest.fixture
def store_dir(tmp_path: Path) -> Path:
    _engine_store(tmp_path)
    write_rows(
        tmp_path,
        "sim_season",
        [
            {"league_id": "L1", "roster_id": 1, "team_name": "Mine", "p_title": 0.5},
            {"league_id": "L1", "roster_id": 2, "team_name": "Theirs", "p_title": 0.1},
        ],
    )
    write_rows(tmp_path, "sim_seeds", [{"league_id": "L1", "roster_id": 1, "seed": 1, "p": 1.0}])
    history = [
        {"league_id": "L1", "roster_id": r, "team_name": n, "run_at": "2026-09-01"}
        for r, n in ((1, "Mine"), (2, "Theirs"))
    ]
    frame = pl.DataFrame(history, schema=store.SCHEMAS["sim_season_history"])
    store.write_table("sim_season_history", frame, "archive", tmp_path)
    write_rows(
        tmp_path,
        "streaming_projection",
        [
            {"league_id": "L1", "kind": "K", "unit": "G_FREEK", "team": "KC", "week": 3}
            | {"projection": 6.0},
        ],
    )
    _engine._clear_league_cache()
    return tmp_path


@pytest.fixture
def client(store_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("LIVE_REFRESH", "off")  # no background thread in API tests
    with TestClient(
        api.create_app(data_dir=store_dir), base_url="http://localhost", headers=CSRF_HEADER
    ) as c:
        yield c


@pytest.fixture
def league(tmp_path: Path) -> Path:
    write_rows(
        tmp_path,
        "leagues",
        [
            {
                "league_key": "t",
                "league_id": LID,
                "current_week": 3,
                "playoff_week_start": 10,
                "roster_positions": POSITIONS,
                "scoring_settings": "{}",
            }
        ],
    )
    teams = [
        {"league_id": LID, "roster_id": r, "team_name": f"T{r}", "is_me": r == 1}
        for r in range(1, 5)
    ]
    write_rows(tmp_path, "league_teams", teams)
    rows = []
    for week, pairs in PAIRS.items():
        for m, pair in enumerate(pairs, start=1):
            rows += [
                {"league_id": LID, "week": week, "roster_id": r, "matchup_id": m}
                | {"points": SCORES.get(week, {}).get(r, 0.0)}
                for r in pair
            ]
    write_rows(tmp_path, "matchups", rows)
    write_rows(
        tmp_path,
        "sleeper_players",
        [
            {"sleeper_id": s, "position": p, "fantasy_positions": [p]}
            for s, p in (("qb1", "QB"), ("rb1", "RB"), ("rb2", "RB"), ("k1", "K"), ("ir", "WR"))
        ],
    )
    players = [
        # sleeper_id, points, is_starter
        ("qb1", 20.0, True), ("rb1", 10.0, True), ("rb2", 15.0, False), ("k1", 5.0, True),
        ("ir", None, False),
    ]  # fmt: skip
    write_rows(
        tmp_path,
        "matchup_players",
        [
            {"league_id": LID, "week": w, "roster_id": 1, "sleeper_id": s, "points": p}
            | {"is_starter": st}
            for w in (1, 2)
            for s, p, st in players
        ],
    )
    return tmp_path
