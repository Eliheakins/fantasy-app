"""The stat app's routes inside the fantasy API: data shards, intent endpoint, shared guards."""

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest
from fakes import FakeLlm
from fastapi.testclient import TestClient

from fantasy import api
from nfl_stat.api.deps import get_llm_client
from nfl_stat.core.config import AppSettings

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
    settings = AppSettings(
        data_dir=data_root / "stat",
        llm_model="test-model",
        llm_base_url="http://fake-llm/v1",
        llm_timeout_seconds=1.0,
        intent_provider="local",
        jev_api_key=None,
        jev_model="jev-latest",
        jev_timeout_seconds=1.0,
    )
    app = api.create_app(web_dist, stat_settings=settings)
    reply = json.dumps({"unsupported": "no such stat"})
    app.dependency_overrides[get_llm_client] = lambda: FakeLlm([reply])
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


# --- one error envelope for /api/* ----------------------------------------------------


def _assert_error_envelope(r: Any, status: int, code: str) -> str:
    assert r.status_code == status, r.text
    out = r.json()
    assert out["status"] == "error" and out["data"] is None
    assert out["error"]["code"] == code
    return str(out["error"]["message"])


def test_a_bad_stat_request_is_a_422_envelope_naming_the_field(client: TestClient) -> None:
    r = client.post("/api/stat/nlq/intent", json={**INTENT, "question": ""}, headers=CSRF_HEADER)

    assert _assert_error_envelope(r, 422, "invalid").startswith("question: ")


def test_a_fantasy_validation_error_names_the_field(client: TestClient) -> None:
    r = client.get("/api/leagues/t/scoreboard?week=99")

    assert _assert_error_envelope(r, 422, "invalid").startswith("week: ")


def test_a_model_that_is_down_is_a_503_envelope(client: TestClient) -> None:
    async def refuse(**_: Any) -> Any:
        raise openai.APIConnectionError(request=httpx2.Request("POST", "http://127.0.0.1:8080/v1"))

    down = SimpleNamespace(
        base_url="http://127.0.0.1:8080/v1",
        chat=SimpleNamespace(completions=SimpleNamespace(create=refuse)),
    )
    client.app.dependency_overrides[get_llm_client] = lambda: down  # type: ignore[attr-defined]
    r = client.post("/api/stat/nlq/intent", json=INTENT, headers=CSRF_HEADER)

    assert "mlx_lm.server" in _assert_error_envelope(r, 503, "server")


def test_a_stat_post_without_the_csrf_header_is_a_403_envelope(client: TestClient) -> None:
    r = client.post("/api/stat/nlq/intent", json=INTENT, headers={"X-Requested-With": "nope"})

    assert "X-Requested-With" in _assert_error_envelope(r, 403, "invalid")


def test_a_missing_stat_shard_is_a_404_envelope(client: TestClient) -> None:
    r = client.get("/api/stat/data/nope.parquet")

    _assert_error_envelope(r, 404, "invalid")


def _llm_raising(error: Exception) -> SimpleNamespace:
    async def create(**_: Any) -> Any:
        raise error

    return SimpleNamespace(
        base_url="http://127.0.0.1:8080/v1",
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    )


def test_a_model_timeout_is_a_504_envelope(client: TestClient) -> None:
    request = httpx2.Request("POST", "http://127.0.0.1:8080/v1")
    down = _llm_raising(openai.APITimeoutError(request=request))
    client.app.dependency_overrides[get_llm_client] = lambda: down  # type: ignore[attr-defined]
    r = client.post("/api/stat/nlq/intent", json=INTENT, headers=CSRF_HEADER)

    assert "too long" in _assert_error_envelope(r, 504, "server")


def test_a_model_server_error_is_a_502_envelope(client: TestClient) -> None:
    response = httpx2.Response(500, request=httpx2.Request("POST", "http://x"), text="boom")
    broken = _llm_raising(openai.APIStatusError("boom", response=response, body=None))
    client.app.dependency_overrides[get_llm_client] = lambda: broken  # type: ignore[attr-defined]
    r = client.post("/api/stat/nlq/intent", json=INTENT, headers=CSRF_HEADER)

    assert "500" in _assert_error_envelope(r, 502, "server")


def test_an_unhandled_error_on_a_stat_route_is_a_500_envelope(
    client: TestClient, data_root: Path, web_dist: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_: Any, **__: Any) -> Any:
        raise KeyError("secret internals")

    monkeypatch.setattr("nfl_stat.api.routers.nlq.answer_intent", boom)
    quiet = TestClient(client.app, base_url="http://localhost", raise_server_exceptions=False)
    r = quiet.post("/api/stat/nlq/intent", json=INTENT, headers=CSRF_HEADER)

    assert "secret" not in _assert_error_envelope(r, 500, "server")


def test_an_http_error_keeps_its_headers(client: TestClient) -> None:
    r = client.post("/api/status")

    assert r.status_code == 403  # the guard answers first without the header
    r = client.post("/api/status", headers=CSRF_HEADER)
    assert r.status_code == 405 and "GET" in r.headers["allow"]
    assert r.json()["status"] == "error"


def test_a_malformed_json_body_has_no_field_prefix(client: TestClient) -> None:
    r = client.post(
        "/api/stat/nlq/intent",
        content=b"{not json",
        headers={**CSRF_HEADER, "content-type": "application/json"},
    )

    assert not _assert_error_envelope(r, 422, "invalid").startswith("body")
