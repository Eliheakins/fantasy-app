from pathlib import Path

from fastapi.testclient import TestClient

from fantasy import refresh_queue
from fantasy._lock import pipeline_lock


def data(client: TestClient) -> dict[str, object]:
    response = client.get("/api/refresh/status")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ok"
    return payload["data"]


def test_status_is_idle_when_nothing_is_queued(client: TestClient) -> None:
    assert data(client)["state"] == "idle"


def test_status_is_queued_after_a_request_and_running_while_the_lock_is_held(
    client: TestClient, store_dir: Path
) -> None:
    refresh_queue.request_refresh("league added", store_dir)
    assert data(client)["state"] == "queued"
    assert data(client)["queued"] == 1
    with pipeline_lock(store_dir):
        assert data(client)["state"] == "running"
