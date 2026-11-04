from __future__ import annotations

import httpx
from conftest import FILTERS, STATS

from core.state import app_state


async def test_intent_returns_503_when_the_llm_client_is_not_initialized(
    client: httpx.AsyncClient,
):
    app_state.llm_client = None

    res = await client.post(
        "/nlq/intent",
        json={
            "question": "Mahomes passing yards",
            "stats": [s.model_dump() for s in STATS],
            "filters": [f.model_dump() for f in FILTERS],
        },
    )

    assert res.status_code == 503
