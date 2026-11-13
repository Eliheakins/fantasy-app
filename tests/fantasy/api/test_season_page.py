"""Season page reads: win needs for my team and the annotations on the odds chart."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from store_fixture import write_rows
from test_league_view import LID

from fantasy import api, data_api

RUNS = [  # run_at, as_of_week
    ("2026-10-20T06:00:00+00:00", 5),
    ("2026-10-27T06:00:00+00:00", 6),
    ("2026-11-03T06:00:00+00:00", 7),
    ("2026-11-10T06:00:00+00:00", 8),
]
MY_SCORES = [100.0, 102.0, 98.0, 101.0, 99.0, 150.0, 100.0]  # weeks 1 to 7; week 6 is the big one


def ms(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=UTC).timestamp() * 1000)


@pytest.fixture
def season(league: Path) -> Path:
    write_rows(
        league, "leagues",
        [{"league_key": "t", "league_id": LID, "current_week": 8, "playoff_week_start": 15,
          "roster_positions": ["QB"], "scoring_settings": "{}"}],
    )  # fmt: skip
    write_rows(
        league, "matchups",
        [{"league_id": LID, "week": w, "roster_id": 1, "matchup_id": 1, "points": p}
         for w, p in enumerate(MY_SCORES, start=1)]
        + [{"league_id": LID, "week": 8, "roster_id": 1, "matchup_id": 1, "points": 0.0}],
    )  # fmt: skip
    names = {"qb1": "Quinn Back", "rb1": "Ray Runner", "rb2": "Bo Bench", "k1": "Kay Kicker"}
    write_rows(
        league, "sleeper_players",
        [{"sleeper_id": s, "full_name": n, "position": "QB", "fantasy_positions": ["QB"]}
         for s, n in names.items()],
    )  # fmt: skip
    write_rows(
        league, "sim_season_history",
        [{"league_id": LID, "roster_id": 1, "team_name": "T1", "run_at": r, "as_of_week": w,
          "p_playoffs": 0.5} for r, w in RUNS],
        area="archive",
    )  # fmt: skip
    trade = {"league_id": LID, "week": 6, "type": "trade", "status": "complete", "roster_id": 1}
    other = {**trade, "transaction_id": "t2", "roster_id": 2}
    write_rows(
        league, "transactions",
        [
            {**trade, "transaction_id": "t1", "created": ms("2026-10-25T12:00:00"),
             "sleeper_id": "rb2", "action": "add"},
            {**trade, "transaction_id": "t1", "created": ms("2026-10-25T12:00:00"),
             "sleeper_id": "k1", "action": "drop"},
            {**other, "created": ms("2026-10-25T12:00:00"), "sleeper_id": "rb1", "action": "add"},
            {**trade, "transaction_id": "w1", "type": "waiver", "sleeper_id": "rb1",
             "created": ms("2026-10-25T12:00:00"), "action": "add"},
            {**trade, "transaction_id": "t0", "created": ms("2026-10-01T12:00:00"),
             "sleeper_id": "rb1", "action": "add"},
        ],
        area="raw",
    )  # fmt: skip
    snap = {"team": "X", "position": "QB"}
    write_rows(
        league, "sleeper_player_status",
        [
            {**snap, "sleeper_id": "qb1", "fetched_at": "2026-10-26T12:00:00+00:00"},
            {**snap, "sleeper_id": "rb2", "fetched_at": "2026-10-26T12:00:00+00:00"},
            {**snap, "sleeper_id": "qb1", "fetched_at": "2026-10-29T12:00:00+00:00",
             "injury_status": "Out"},
            {**snap, "sleeper_id": "rb2", "fetched_at": "2026-10-29T12:00:00+00:00",
             "injury_status": "Out"},
        ],
        area="archive",
    )  # fmt: skip
    return league


def events(season: Path) -> list[dict]:
    return data_api.season_events("t", season).sort("when").to_dicts()


def test_each_kind_of_event_lands_on_the_first_run_after_it(season: Path) -> None:
    by_kind = {e["kind"]: e for e in events(season)}
    assert by_kind["trade"]["run_at"] == RUNS[1][0]
    assert by_kind["injury"]["run_at"] == RUNS[2][0]
    assert by_kind["big_week"]["run_at"] == RUNS[2][0]  # first run after week 6 was played


def test_only_my_starters_my_trades_and_big_weeks_are_annotated(season: Path) -> None:
    out = events(season)
    labels = [e["label"] for e in out]
    assert sum(e["kind"] == "trade" for e in out) == 2  # t0 is early, still listed; t2, waiver not
    assert any("Quinn Back" in x and "Out" in x for x in labels)
    assert not any("Bo Bench" in x and "Out" in x for x in labels)  # a bench player
    assert any("Bo Bench" in x and "Kay Kicker" in x for x in labels)
    assert [e["kind"] for e in out].count("big_week") == 1
    assert next(e for e in out if e["kind"] == "big_week")["label"].startswith("Week 6")


def test_an_event_before_the_first_saved_run_has_no_run_to_sit_on(season: Path) -> None:
    early = [e for e in events(season) if e["kind"] == "trade" and e["when"] < RUNS[0][0]]
    assert len(early) == 1 and early[0]["run_at"] is None


def test_no_history_or_no_data_gives_no_events(season: Path) -> None:
    assert data_api.season_events("nope", season).is_empty()
    write_rows(season, "sim_season_history", [], area="archive")
    assert all(e["run_at"] is None for e in events(season))


def test_a_big_week_before_the_first_saved_run_is_not_marked(season: Path) -> None:
    write_rows(
        season,
        "sim_season_history",
        [{"league_id": LID, "roster_id": 1, "run_at": RUNS[3][0], "as_of_week": 8}],
        area="archive",
    )
    assert "big_week" not in {e["kind"] for e in events(season)}


def test_a_malformed_timestamp_is_skipped_not_fatal(season: Path) -> None:
    snap = {"team": "X", "position": "QB", "sleeper_id": "qb1"}
    write_rows(
        season,
        "sleeper_player_status",
        [{**snap, "fetched_at": "garbage"}, {**snap, "fetched_at": "2026-10-26T12:00:00+00:00"},
         {**snap, "fetched_at": "2026-10-29T12:00:00+00:00", "injury_status": "Out"}],
        area="archive",
    )  # fmt: skip
    assert [e["kind"] for e in events(season)].count("injury") == 1


def test_a_big_week_is_judged_against_the_other_weeks(season: Path) -> None:
    labels = [e["label"] for e in events(season) if e["kind"] == "big_week"]
    assert len(labels) == 1 and "50.0 above" in labels[0]  # 150 against the others' mean of 100


def write_need(path: Path) -> None:
    rows = [(1, 4, k, 100 * (k + 1), 0.1 * (k + 1), 0.2 * (k + 1)) for k in range(5)] + [
        (2, 4, 0, 50, 1.0, 0.9)
    ]
    write_rows(
        path, "sim_win_need",
        [{"league_id": LID, "as_of_week": 8, "roster_id": r, "n_games": g, "wins": k,
          "n_runs": n, "p_condition": pc, "p_playoffs": pp} for r, g, k, n, pc, pp in rows],
    )  # fmt: skip


def test_win_needs_are_my_rows_by_wins(season: Path) -> None:
    write_need(season)
    out = data_api.win_needs("t", season)
    assert out["wins"].to_list() == [0, 1, 2, 3, 4]
    assert out["p_playoffs"].to_list() == pytest.approx([0.2, 0.4, 0.6, 0.8, 1.0])
    assert set(out.columns) == {"n_games", "wins", "n_runs", "p_condition", "p_playoffs"}


def test_win_needs_are_empty_before_the_simulation_has_written_them(season: Path) -> None:
    assert data_api.win_needs("t", season).is_empty()
    assert data_api.win_needs("nope", season).is_empty()


@pytest.fixture
def client(season: Path) -> Iterator[TestClient]:
    write_need(season)
    headers = {"X-Requested-With": "fantasy-app"}
    with TestClient(
        api.create_app(data_dir=season), base_url="http://localhost", headers=headers
    ) as c:
        yield c


def test_routes_return_ok_envelopes(client: TestClient) -> None:
    need = client.get("/api/leagues/t/win-needs").json()
    assert need["status"] == "ok" and len(need["data"]) == 5
    found = client.get("/api/leagues/t/season-events").json()
    assert found["status"] == "ok"
    assert set(found["data"][0]) == {"kind", "when", "run_at", "label"}
