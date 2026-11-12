from __future__ import annotations

import json
from pathlib import Path

import httpx
import httpx2
import openai
import pytest
from fakes import FILTERS, STATS

from nfl_stat.api.deps import get_llm_client
from nfl_stat.pipeline.manifest import write_manifest
from nfl_stat.schemas.manifest import JsonFileEntry, Manifest, SeasonEntry


def _intent_body(question: str = "Mahomes passing yards in 2023") -> dict:
    return {
        "question": question,
        "stats": [s.model_dump() for s in STATS],
        "filters": [f.model_dump() for f in FILTERS],
    }


async def test_health_is_degraded_until_the_data_is_built(client: httpx.AsyncClient):
    res = await client.get("/api/stat/health")

    assert res.status_code == 200
    assert res.json() == {
        "status": "degraded",
        "data_ready": False,
        "data_through": None,
        "built_at": None,
        "seasons": [],
    }


def _manifest(
    *, week: int, seasons: tuple[int, ...] = (2025, 2026), players: bool = True
) -> Manifest:
    return Manifest(
        built_at="2026-11-04T12:00:00+00:00",
        nflreadpy_version="1",
        seasons=[
            SeasonEntry(
                season=season,
                path=f"nfl_pbp_{season}.parquet",
                rows=1,
                max_week=week if season == seasons[-1] else 22,
                has_participation=True,
            )
            for season in seasons
        ],
        players=JsonFileEntry(path="players.json", rows=1) if players else None,
    )


async def test_health_reports_how_current_the_data_is(client: httpx.AsyncClient, data_dir: Path):
    write_manifest(_manifest(week=9), data_dir)

    body = (await client.get("/api/stat/health")).json()

    assert body["status"] == "ok"
    assert body["data_ready"] is True
    assert body["data_through"] == "2026 week 9"
    assert body["built_at"] == "2026-11-04T12:00:00+00:00"
    assert body["seasons"] == [2025, 2026]


async def test_health_follows_a_rebuild_without_restarting_the_api(
    client: httpx.AsyncClient, data_dir: Path
):
    write_manifest(_manifest(week=9), data_dir)
    assert (await client.get("/api/stat/health")).json()["data_through"] == "2026 week 9"

    write_manifest(_manifest(week=10, seasons=(2025, 2026, 2027)), data_dir)
    body = (await client.get("/api/stat/health")).json()

    assert body["data_through"] == "2027 week 10"
    assert body["seasons"] == [2025, 2026, 2027]


async def test_health_goes_degraded_when_the_manifest_disappears(
    client: httpx.AsyncClient, data_dir: Path
):
    write_manifest(_manifest(week=9), data_dir)
    assert (await client.get("/api/stat/health")).json()["status"] == "ok"

    (data_dir / "manifest.json").unlink()

    assert (await client.get("/api/stat/health")).json()["status"] == "degraded"


async def test_health_reports_a_broken_manifest_instead_of_failing(
    client: httpx.AsyncClient, data_dir: Path
):
    (data_dir / "manifest.json").write_text("{not json")

    res = await client.get("/api/stat/health")

    assert res.status_code == 200
    assert res.json()["status"] == "degraded"


async def test_health_is_degraded_when_seasons_exist_but_the_players_file_does_not(
    client: httpx.AsyncClient, data_dir: Path
):
    write_manifest(_manifest(week=9, seasons=(2026,), players=False), data_dir)

    body = (await client.get("/api/stat/health")).json()

    assert body["status"] == "degraded"
    assert body["data_ready"] is False
    assert body["seasons"] == [2026]


async def test_the_player_and_shard_endpoints_are_gone_because_the_data_is_static(
    client: httpx.AsyncClient,
):
    for path in ("/search?q=a", "/players/dictionary", "/player/00-0033873", "/pbp/shards"):
        assert (await client.get(path)).status_code == 404, path


async def test_nlq_intent_returns_validated_intent(client: httpx.AsyncClient, use_llm):
    use_llm(['{"stat_ids": ["pass_yards"], "filter_ids": ["season-2023"], "granularity": "total"}'])

    res = await client.post("/api/stat/nlq/intent", json=_intent_body())

    assert res.status_code == 200
    assert res.json() == {
        "outcome": "query",
        "intent": {
            "stat_ids": ["pass_yards"],
            "filter_ids": ["season-2023"],
            "granularity": "total",
            "ranking": False,
        },
    }


async def test_nlq_intent_accepts_the_catalog_the_app_really_sends(
    client: httpx.AsyncClient, use_llm
):
    catalog = json.loads((Path(__file__).parent / "eval" / "catalog.json").read_text())
    use_llm(['{"stat_ids": ["pass_yards"], "filter_ids": [], "granularity": "total"}'])

    res = await client.post("/api/stat/nlq/intent", json={"question": "q", **catalog})

    assert res.status_code == 200, res.text


def _padded(stats: int, aliases: int) -> dict:
    stat = {"id": "s", "label": "l", "category": "c", "aliases": ["a" * 50] * aliases}
    return {"question": "q", "stats": [stat] * stats, "filters": []}


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        (_padded(stats=121, aliases=1), 422),  # more stats than the app has
        (_padded(stats=1, aliases=12), 422),  # more aliases than any stat has
        (_padded(stats=100, aliases=11), 413),  # each field is allowed, the body is too big
    ],
)
async def test_nlq_intent_rejects_an_oversized_catalog_without_calling_the_model(
    client: httpx.AsyncClient, use_llm, payload: dict, status: int
):
    fake = use_llm(['{"stat_ids": ["pass_yards"], "filter_ids": []}'])

    res = await client.post("/api/stat/nlq/intent", json=payload)

    assert res.status_code == status, res.text
    assert fake.calls == []


async def test_nlq_intent_returns_the_reason_when_the_question_is_unsupported(
    client: httpx.AsyncClient, use_llm
):
    use_llm(['{"unsupported": "Salaries are not in the play-by-play data."}'])

    res = await client.post("/api/stat/nlq/intent", json=_intent_body("Mahomes salary in 2023"))

    assert res.status_code == 200
    assert res.json() == {
        "outcome": "unsupported",
        "reason": "Salaries are not in the play-by-play data.",
    }


async def test_nlq_intent_returns_422_when_model_never_produces_valid_json(
    client: httpx.AsyncClient, use_llm
):
    use_llm(["nope", "still nope"])

    res = await client.post("/api/stat/nlq/intent", json=_intent_body())

    assert res.status_code == 422
    assert "couldn't turn that into a query" in res.json()["detail"]


async def test_nlq_intent_rejects_empty_question(client: httpx.AsyncClient, use_llm):
    use_llm([])

    res = await client.post("/api/stat/nlq/intent", json=_intent_body(question=""))

    assert res.status_code == 422


async def test_nlq_intent_returns_503_when_llm_server_is_down(client: httpx.AsyncClient, app):
    class DownLlm:
        base_url = "http://127.0.0.1:8080/v1"

        class chat:
            class completions:
                @staticmethod
                async def create(**_):
                    raise openai.APIConnectionError(
                        request=httpx2.Request("POST", "http://127.0.0.1:8080/v1/chat/completions")
                    )

    app.dependency_overrides[get_llm_client] = lambda: DownLlm()

    res = await client.post("/api/stat/nlq/intent", json=_intent_body())

    assert res.status_code == 503
    assert "mlx_lm.server" in res.json()["detail"]
