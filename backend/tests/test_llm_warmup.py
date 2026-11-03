from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import openai
import pytest

from services.llm_warmup import keep_model_warm


class PingRecorder:
    def __init__(self, fail_first: bool = False) -> None:
        self.calls: list[dict] = []
        self._fail_first = fail_first
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._fail_first and len(self.calls) == 1:
            raise openai.APIConnectionError(
                request=httpx.Request("POST", "http://127.0.0.1:8080/v1/chat/completions")
            )
        return SimpleNamespace(choices=[])


async def _run_for(client: PingRecorder, seconds: float) -> None:
    task = asyncio.create_task(keep_model_warm(client, "m", interval_seconds=0.01))
    await asyncio.sleep(seconds)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_pings_repeatedly_with_a_single_token_request():
    client = PingRecorder()

    await _run_for(client, 0.1)

    assert len(client.calls) >= 2
    assert all(c["max_tokens"] == 1 and c["model"] == "m" for c in client.calls)


async def test_keeps_pinging_after_the_server_was_unreachable():
    client = PingRecorder(fail_first=True)

    await _run_for(client, 0.1)

    assert len(client.calls) >= 2
