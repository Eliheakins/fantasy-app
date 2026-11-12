from fastapi.testclient import TestClient


def test_holes_route_returns_a_list_in_the_envelope(client: TestClient) -> None:
    body = client.get("/api/leagues/t/holes").json()
    assert body["status"] == "ok"
    for row in body["data"]:
        assert set(row) == {"kind", "slot", "player_name", "fill_ins"}


def test_holes_route_unknown_league_is_not_a_server_error(client: TestClient) -> None:
    assert client.get("/api/leagues/nope/holes").status_code != 500


def test_stash_route_returns_slots_and_rows(client: TestClient) -> None:
    body = client.get("/api/leagues/t/stash").json()
    assert body["status"] == "ok"
    assert set(body["data"]) == {"open_ir_slots", "rows"}
    for row in body["data"]["rows"]:
        assert set(row) == {
            "gsis_id", "full_name", "position", "status", "owner", "is_mine",
            "ir_eligible", "first_week", "playoff_points",
        }  # fmt: skip


def test_lineup_grid_route_returns_weeks_and_rows(client: TestClient) -> None:
    body = client.get("/api/leagues/t/lineup-grid").json()
    assert body["status"] == "ok"
    assert set(body["data"]) == {"weeks", "playoff_weeks", "rows"}
    for row in body["data"]["rows"]:
        assert set(row) == {"week", "slot", "gsis_id", "full_name", "points", "flag"}
