"""Smoke tests for the digest route and the stored-adds switch on actions."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from store_fixture import write_rows
from test_api import store_dir as store_dir  # noqa: F401  (fixture)
from test_api import wait_ok
from test_digest import idea_rows
from test_league_view import league  # noqa: F401  (league is a fixture)

from fantasy import api, data_api, store


@pytest.fixture
def client(league: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:  # noqa: F811
    monkeypatch.setattr(store, "DATA_DIR", league)
    monkeypatch.setenv("LIVE_REFRESH", "off")
    headers = {"X-Requested-With": "fantasy-app"}
    with TestClient(api.create_app(), base_url="http://localhost", headers=headers) as c:
        yield c


def digest(client: TestClient, query: str = "") -> dict[str, Any]:
    out = client.get(f"/api/leagues/t/digest{query}").json()
    assert out["status"] == "ok", out
    data: dict[str, Any] = out["data"]
    return data


def test_digest_without_any_stored_ideas_still_gives_last_week(client: TestClient) -> None:
    data = digest(client)
    assert data["last_week"]["week"] == 2 and data["last_week"]["result"] == "L"
    assert data["waivers"] == [] and data["trades"] == []
    assert data["ideas"]["created_at"] is None and data["ideas"]["is_mine"] is True
    assert data["odds_change"] == []  # no simulation history yet


def test_digest_returns_stored_ideas_with_their_time(client: TestClient, league: Path) -> None:
    write_rows(league, "move_ideas", idea_rows())
    data = digest(client)
    assert data["ideas"]["created_at"] == "2026-10-25T08:00:00+00:00"
    assert data["ideas"]["as_of_week"] == 7
    assert [r["get"] for r in data["waivers"]] == ["Added"]
    assert set(data["waivers"][0]) == {
        "kind", "partner", "give", "get", "give_ids", "get_ids", "rank", "playoff_delta",
        "title_delta", "se_title", "delta_points",
    }  # fmt: skip


def test_digest_for_another_team_says_ideas_are_mine_only(client: TestClient, league: Path) -> None:
    write_rows(league, "move_ideas", idea_rows())
    data = digest(client, "?team=3")
    assert data["ideas"]["is_mine"] is False
    assert data["waivers"] == [] and data["trades"] == []
    assert data["last_week"]["team_name"] == "T3"


def test_digest_marks_the_deadline_as_passed_and_rejects_unknown_leagues(
    client: TestClient, league: Path
) -> None:
    write_rows(
        league,
        "leagues",
        [
            {
                "league_key": "t", "league_id": "L1", "current_week": 3, "trade_deadline": 2,
                "playoff_week_start": 10, "roster_positions": ["QB"], "scoring_settings": "{}",
            }
        ],
    )  # fmt: skip
    assert digest(client)["ideas"]["deadline_passed"] is True
    assert client.get("/api/leagues/zzz/digest").json()["error"]["code"] == "invalid"


def test_actions_can_reuse_the_stored_waivers(
    store_dir: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_rows(store_dir, "move_ideas", idea_rows(league_id="L1"))
    write_rows(store_dir, "league_teams", [{"league_id": "L1", "roster_id": 1, "is_me": True}])
    monkeypatch.setattr(data_api, "waivers", lambda *a, **k: pytest.fail("re-simulated"))
    monkeypatch.setenv("LIVE_REFRESH", "off")
    headers = {"X-Requested-With": "fantasy-app"}
    with TestClient(api.create_app(), base_url="http://localhost", headers=headers) as c:
        out = wait_ok(c, lambda: c.get("/api/leagues/t/actions?stored_adds=true"))
    assert out["status"] == "ok"
    assert any(r["kind"] == "Waiver" and "Added" in r["text"] for r in out["data"]), out["data"]
