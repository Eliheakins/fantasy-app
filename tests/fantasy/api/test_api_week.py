"""The week calendar (kickoffs and waiver day) and the roster's status changes since a time."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from fastapi.testclient import TestClient
from store_fixture import write_rows

from fantasy import api, store
from fantasy.config import load_config


@pytest.fixture
def client(league: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("LIVE_REFRESH", "off")
    headers = {"X-Requested-With": "fantasy-app"}
    with TestClient(
        api.create_app(data_dir=league), base_url="http://localhost", headers=headers
    ) as c:
        yield c


def get(client: TestClient, url: str) -> dict[str, Any]:
    return client.get(url).json()  # type: ignore[no-any-return]


def set_settings(path: Path, settings: dict[str, Any] | None) -> None:
    frame = store.read_table("leagues", "raw", path)
    value = None if settings is None else json.dumps(settings)
    store.write_table(
        "leagues", frame.with_columns(pl.lit(value, dtype=pl.String).alias("settings")), "raw", path
    )


def test_calendar_gives_kickoffs_of_the_current_week_with_the_offset(
    client: TestClient,
    league: Path,
) -> None:
    season = load_config().season
    games = [
        {"season": season, "week": 3, "game_type": "REG", "home_team": "KC", "away_team": "BUF"}
        | {"gameday": "2026-09-24", "gametime": "20:15"},
        {"season": season, "week": 4, "game_type": "REG", "home_team": "DAL", "away_team": "NYG"}
        | {"gameday": "2026-10-01", "gametime": "20:15"},
    ]
    write_rows(league, "nfl_schedules", games)
    data = get(client, "/api/week-calendar")["data"]
    assert data["week"] == 3
    assert {(k["team"], k["kickoff"]) for k in data["kickoffs"]} == {
        ("KC", "2026-09-24T20:15:00-04:00"),
        ("BUF", "2026-09-24T20:15:00-04:00"),
    }


def test_calendar_without_a_schedule_still_answers_with_no_kickoffs(client: TestClient) -> None:
    data = get(client, "/api/week-calendar")["data"]
    assert data["week"] == 3 and data["kickoffs"] == []


def test_calendar_reads_the_waiver_day_and_marks_daily_waivers(
    client: TestClient,
    league: Path,
) -> None:
    set_settings(league, {"waiver_day_of_week": 2, "daily_waivers": 0})
    assert get(client, "/api/week-calendar")["data"]["waivers"] == [
        {"league_key": "t", "name": None, "day_of_week": 2, "daily": False}
    ]
    set_settings(league, {"waiver_day_of_week": 2, "daily_waivers": 1})
    row = get(client, "/api/week-calendar")["data"]["waivers"][0]
    assert row["daily"] is True and row["day_of_week"] is None


def test_calendar_with_no_settings_has_no_waiver_day(client: TestClient, league: Path) -> None:
    set_settings(league, None)
    row = get(client, "/api/week-calendar")["data"]["waivers"][0]
    assert row["day_of_week"] is None and row["daily"] is False


def snapshot(path: Path, rows: list[dict[str, Any]]) -> None:
    schema = store.SCHEMAS["sleeper_player_status"]
    blank = dict.fromkeys(schema)
    frame = pl.DataFrame([{**blank, **r} for r in rows], schema=schema)
    store.write_table("sleeper_player_status", frame, "archive", path)


def snap(sleeper_id: str, fetched_at: str, injury: str | None) -> dict[str, Any]:
    return {"sleeper_id": sleeper_id, "fetched_at": fetched_at, "injury_status": injury}


@pytest.fixture
def my_roster(league: Path) -> Path:
    write_rows(
        league,
        "rosters",
        [
            {"league_id": "L1", "roster_id": 1, "sleeper_id": s, "is_starter": True}
            for s in ("qb1", "rb1")
        ]
        + [{"league_id": "L1", "roster_id": 2, "sleeper_id": "k1", "is_starter": True}],
    )
    return league


def test_status_changes_lists_my_players_whose_status_moved_since(
    client: TestClient, my_roster: Path
) -> None:
    snapshot(
        my_roster,
        [
            snap("qb1", "2026-10-30T10:00:00+00:00", None),
            snap("rb1", "2026-10-30T10:00:00+00:00", "Questionable"),
            snap("k1", "2026-10-30T10:00:00+00:00", None),
            snap("qb1", "2026-11-02T10:00:00+00:00", "Out"),
            snap("rb1", "2026-11-02T10:00:00+00:00", "Questionable"),
            snap("k1", "2026-11-02T10:00:00+00:00", "Out"),
        ],
    )
    out = get(client, "/api/leagues/t/status-changes?since=2026-11-01T00:00:00Z")
    rows = out["data"]
    assert [(r["sleeper_id"], r["before"], r["after"]) for r in rows] == [("qb1", None, "Out")]


def test_status_changes_is_empty_when_there_is_no_snapshot_at_or_before_since(
    client: TestClient, my_roster: Path
) -> None:
    snapshot(my_roster, [snap("qb1", "2026-11-02T10:00:00+00:00", "Out")])
    out = get(client, "/api/leagues/t/status-changes?since=2026-11-01T00:00:00Z")
    assert out["status"] == "ok" and out["data"] == []


def test_status_changes_without_the_archive_is_empty(client: TestClient) -> None:
    out = get(client, "/api/leagues/t/status-changes?since=2026-11-01T00:00:00Z")
    assert out["status"] == "ok" and out["data"] == []


def test_status_changes_follows_the_viewed_team(client: TestClient, my_roster: Path) -> None:
    snapshot(
        my_roster,
        [
            snap("k1", "2026-10-30T10:00:00+00:00", None),
            snap("k1", "2026-11-02T10:00:00+00:00", "Out"),
        ],
    )
    out = get(client, "/api/leagues/t/status-changes?since=2026-11-01T00:00:00Z&team=2")
    assert [r["sleeper_id"] for r in out["data"]] == ["k1"]


def test_status_changes_rejects_unknown_leagues_and_a_bad_time(client: TestClient) -> None:
    unknown = get(client, "/api/leagues/zzz/status-changes?since=2026-11-01T00:00:00Z")
    assert unknown["error"]["code"] == "invalid"
    assert client.get("/api/leagues/t/status-changes?since=yesterday").status_code == 422
    assert client.get("/api/leagues/t/status-changes").status_code == 422


def test_status_changes_reads_a_time_without_a_zone_as_utc(
    client: TestClient, my_roster: Path
) -> None:
    snapshot(
        my_roster,
        [
            snap("qb1", "2026-10-30T10:00:00+00:00", None),
            snap("qb1", "2026-11-02T10:00:00+00:00", "Out"),
        ],
    )
    out = get(client, "/api/leagues/t/status-changes?since=2026-11-01T00:00:00")
    assert out["status"] == "ok" and [r["sleeper_id"] for r in out["data"]] == ["qb1"]


def test_status_changes_shows_a_player_missing_from_the_older_snapshot(
    client: TestClient, my_roster: Path
) -> None:
    snapshot(
        my_roster,
        [
            snap("rb1", "2026-10-30T10:00:00+00:00", None),
            snap("rb1", "2026-11-02T10:00:00+00:00", None),
            snap("qb1", "2026-11-02T10:00:00+00:00", "Out"),
        ],
    )
    rows = get(client, "/api/leagues/t/status-changes?since=2026-11-01T00:00:00Z")["data"]
    assert [(r["sleeper_id"], r["before"], r["after"]) for r in rows] == [("qb1", None, "Out")]


def test_status_changes_uses_the_one_snapshot_at_or_before_since(
    client: TestClient, my_roster: Path
) -> None:
    snapshot(
        my_roster,
        [
            snap("qb1", "2026-10-20T10:00:00+00:00", "Out"),
            snap("qb1", "2026-10-30T10:00:00+00:00", None),
            snap("qb1", "2026-11-05T10:00:00+00:00", "Out"),
        ],
    )
    rows = get(client, "/api/leagues/t/status-changes?since=2026-11-01T00:00:00Z")["data"]
    assert [(r["before"], r["after"]) for r in rows] == [(None, "Out")]


def test_calendar_survives_bad_settings_and_reports_teams_without_a_kickoff_time(
    client: TestClient,
    league: Path,
) -> None:
    frame = store.read_table("leagues", "raw", league)
    store.write_table(
        "leagues",
        frame.with_columns(pl.lit("{not json", dtype=pl.String).alias("settings")),
        "raw",
        league,
    )
    games = [
        {"season": load_config().season, "week": 3, "game_type": "REG", "home_team": "KC"}
        | {"away_team": "BUF", "gameday": "2026-09-24", "gametime": None}
    ]
    write_rows(league, "nfl_schedules", games)
    data = get(client, "/api/week-calendar")["data"]
    assert data["waivers"][0]["day_of_week"] is None
    assert data["kickoffs"] == [{"team": "BUF", "kickoff": None}, {"team": "KC", "kickoff": None}]


def test_calendar_kickoff_offset_follows_daylight_saving(
    client: TestClient,
    league: Path,
) -> None:
    season = load_config().season
    games = [
        {"season": season, "week": 3, "game_type": "REG", "home_team": "KC", "away_team": "BUF"}
        | {"gameday": "2026-11-01", "gametime": "13:00"},  # the Sunday daylight time ends
        {"season": season, "week": 3, "game_type": "REG", "home_team": "DAL", "away_team": "NYG"}
        | {"gameday": "2026-10-25", "gametime": "13:00"},
    ]
    write_rows(league, "nfl_schedules", games)
    by_team = {
        k["team"]: k["kickoff"] for k in get(client, "/api/week-calendar")["data"]["kickoffs"]
    }
    assert by_team["KC"] == "2026-11-01T13:00:00-05:00"
    assert by_team["DAL"] == "2026-10-25T13:00:00-04:00"
