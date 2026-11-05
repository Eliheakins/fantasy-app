"""The stat app's routes inside the fantasy API: data shards, intent endpoint, shared guards."""

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fantasy import api
from nfl_stat.api.deps import get_llm_client

CSRF_HEADER = {"X-Requested-With": "fantasy-app"}
SHARD = b"PAR1-fake-shard-bytes"
INTENT = {
    "question": "mahomes passing yards",
    "stats": [{"id": "pass_yards", "label": "Pass yards", "category": "passing"}],
    "filters": [],
}
MANIFEST = {
    "built_at": "2026-11-04T00:00:00+00:00",
    "nflreadpy_version": "0.1.5",
    "seasons": [
        {
            "season": 2026,
            "path": "nfl_pbp_2026.parquet",
            "rows": 1,
            "max_week": 9,
            "has_participation": False,
        }
    ],
}


class FakeLlm:
    def __init__(self, reply: str) -> None:
        self.base_url = "http://fake-llm/v1"
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._reply = reply

    async def _create(self, **_: Any) -> Any:
        message = SimpleNamespace(content=self._reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    stat = tmp_path / "data" / "stat"
    stat.mkdir(parents=True)
    (stat / "manifest.json").write_text(json.dumps(MANIFEST))
    (stat / "nfl_pbp_2026.parquet").write_bytes(SHARD)
    derived = tmp_path / "data" / "derived"
    derived.mkdir()
    (derived / "x.parquet").write_bytes(b"PRIVATE")
    return tmp_path / "data"


@pytest.fixture
def web_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>app shell</html>")
    return dist


@pytest.fixture
def client(
    data_root: Path, web_dist: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("LIVE_REFRESH", "off")
    settings = SimpleNamespace(
        data_dir=data_root / "stat",
        llm_model="test-model",
        llm_base_url="http://fake-llm/v1",
        llm_timeout_seconds=1.0,
    )
    app = api.create_app(web_dist, stat_settings=settings)
    reply = json.dumps({"unsupported": "no such stat"})
    app.dependency_overrides[get_llm_client] = lambda: FakeLlm(reply)
    with TestClient(app, base_url="http://localhost") as c:
        yield c


def test_manifest_is_served_from_data_stat(client: TestClient) -> None:
    r = client.get("/api/stat/data/manifest.json")
    assert r.status_code == 200
    assert r.json()["seasons"][0]["max_week"] == 9


def test_a_version_query_on_a_shard_url_still_serves_the_shard(client: TestClient) -> None:
    r = client.get("/api/stat/data/nfl_pbp_2026.parquet?v=2026-11-04T12%3A00%3A00%2B00%3A00")
    assert r.status_code == 200
    assert r.content == SHARD


def test_plain_get_of_a_shard_advertises_ranges(client: TestClient) -> None:
    r = client.get("/api/stat/data/nfl_pbp_2026.parquet")
    assert r.status_code == 200
    assert r.headers["accept-ranges"] == "bytes"


@pytest.mark.parametrize("name", ["notes.csv", "secret.json", "players.json.bak"])
def test_only_manifest_players_and_parquet_are_served(
    client: TestClient, data_root: Path, name: str
) -> None:
    (data_root / "stat" / name).write_text("private")
    r = client.get(f"/api/stat/data/{name}")
    assert r.status_code == 404
    assert b"private" not in r.content


def test_players_json_is_served(client: TestClient, data_root: Path) -> None:
    (data_root / "stat" / "players.json").write_text("[]")
    assert client.get("/api/stat/data/players.json").status_code == 200


def test_unknown_stat_route_is_404_not_the_app_shell(client: TestClient) -> None:
    r = client.get("/api/stat/nope")
    assert r.status_code == 404
    assert b"app shell" not in r.content


def test_range_request_gives_partial_content(client: TestClient) -> None:
    r = client.get("/api/stat/data/nfl_pbp_2026.parquet", headers={"Range": "bytes=0-3"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 0-3/{len(SHARD)}"
    assert r.content == SHARD[:4]


def test_intent_post_needs_the_csrf_header(client: TestClient) -> None:
    assert client.post("/api/stat/nlq/intent", json=INTENT).status_code == 403


def test_intent_post_with_header_answers(client: TestClient) -> None:
    r = client.post("/api/stat/nlq/intent", json=INTENT, headers=CSRF_HEADER)
    assert r.status_code == 200
    assert r.json()["outcome"] == "unsupported"


def test_health_is_under_api_stat(client: TestClient) -> None:
    r = client.get("/api/stat/health")
    assert r.status_code == 200
    assert r.json()["data_through"] == "2026 week 9"


def test_foreign_host_is_rejected(client: TestClient) -> None:
    r = client.get("/api/stat/data/manifest.json", headers={"Host": "evil.example"})
    assert r.status_code == 400


@pytest.mark.parametrize(
    "path",
    [
        "/api/stat/data/%2e%2e/derived/x.parquet",
        "/api/stat/data/..%2fderived%2fx.parquet",
        "/api/stat/data/x.parquet",  # exists only in data/derived
    ],
)
def test_data_outside_data_stat_is_not_served(client: TestClient, path: str) -> None:
    r = client.get(path)
    assert r.status_code == 404
    assert b"PRIVATE" not in r.content


def test_missing_shard_is_404_not_the_app_shell(client: TestClient) -> None:
    r = client.get("/api/stat/data/nfl_pbp_1999.parquet")
    assert r.status_code == 404
    assert b"app shell" not in r.content


def test_missing_manifest_is_404(client: TestClient, data_root: Path) -> None:
    (data_root / "stat" / "manifest.json").unlink()
    assert client.get("/api/stat/data/manifest.json").status_code == 404
