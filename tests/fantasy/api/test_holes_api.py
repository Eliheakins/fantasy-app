from fastapi.testclient import TestClient


def test_holes_route_returns_a_list_in_the_envelope(client: TestClient) -> None:
    body = client.get("/api/leagues/t/holes").json()
    assert body["status"] == "ok"
    for row in body["data"]:
        assert set(row) == {"kind", "slot", "player_name", "fill_ins"}


def test_holes_route_unknown_league_is_not_a_server_error(client: TestClient) -> None:
    assert client.get("/api/leagues/nope/holes").status_code != 500
