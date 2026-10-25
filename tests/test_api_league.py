"""Smoke tests for the League page routes."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_league_view import league, sim_tables  # noqa: F401  (league is a fixture)

from fantasy import api, store

COLUMNS = {
    "power-rankings": {
        "roster_id", "team_name", "is_me", "rank", "exp_points_week", "exp_wins", "p_playoffs",
        "p_title", "sos_remaining", "sos_rank",
    },
    "luck": {
        "roster_id", "team_name", "is_me", "weeks", "wins", "losses", "ties", "ap_wins",
        "ap_losses", "ap_ties", "exp_wins", "luck",
    },
    "manager-grades": {
        "roster_id", "team_name", "is_me", "weeks", "actual_points", "optimal_points",
        "efficiency", "bench_points_left",
    },
    "what-if": {
        "winner_id", "loser_id", "winner", "loser", "involves_me", "p_condition", "n_runs",
        "d_playoffs", "d_title",
    },
}  # fmt: skip


@pytest.fixture
def client(league: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:  # noqa: F811
    sim_tables(league)
    monkeypatch.setattr(store, "DATA_DIR", league)
    headers = {"X-Requested-With": "fantasy-app"}
    with TestClient(api.create_app(), base_url="http://localhost", headers=headers) as c:
        yield c


@pytest.mark.parametrize("route", COLUMNS)
def test_league_routes_return_an_ok_envelope_with_the_expected_columns(
    route: str, client: TestClient
) -> None:
    out = client.get(f"/api/leagues/t/{route}").json()
    assert out["status"] == "ok" and out["error"] is None, out
    assert set(out["data"][0]) == COLUMNS[route]


def test_what_if_takes_a_week_and_rejects_a_bad_one(client: TestClient) -> None:
    assert client.get("/api/leagues/t/what-if?week=2").json()["data"] == []
    assert client.get("/api/leagues/t/what-if?week=99").status_code == 422
