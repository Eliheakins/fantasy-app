from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest

from nfl_stat.services.llm_client import (
    ModelFailed,
    ModelTimeout,
    ModelUnavailable,
    chat_text,
    model_error_from_llm_error,
)

BASE_URL = "http://127.0.0.1:8080/v1"


def _request() -> httpx.Request:
    return httpx.Request("POST", f"{BASE_URL}/chat/completions")


def test_timeout_maps_to_504():
    exc = model_error_from_llm_error(openai.APITimeoutError(request=_request()), BASE_URL)

    assert isinstance(exc, ModelTimeout)


def test_connection_error_maps_to_503_and_says_how_to_start_the_server():
    exc = model_error_from_llm_error(openai.APIConnectionError(request=_request()), BASE_URL)

    assert isinstance(exc, ModelUnavailable)
    assert BASE_URL in str(exc)
    assert "mlx_lm.server" in str(exc)


def test_http_status_error_maps_to_502_with_the_upstream_code():
    response = httpx.Response(500, request=_request(), text="boom")
    exc = model_error_from_llm_error(
        openai.APIStatusError("boom", response=response, body=None), BASE_URL
    )

    assert isinstance(exc, ModelFailed)
    assert "500" in str(exc)


def test_unexpected_error_maps_to_502_without_leaking_details():
    exc = model_error_from_llm_error(RuntimeError("secret internals"), BASE_URL)

    assert isinstance(exc, ModelFailed)
    assert "secret" not in str(exc)


def _client(
    content: str | None = None, choices: list | None = None, error: Exception | None = None
):
    async def create(**_):
        if error:
            raise error
        picked = (
            choices
            if choices is not None
            else [SimpleNamespace(message=SimpleNamespace(content=content))]
        )
        return SimpleNamespace(choices=picked)

    return SimpleNamespace(
        base_url=BASE_URL, chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


async def test_chat_text_returns_stripped_content():
    assert await chat_text(client=_client("  hello \n"), model="m", messages=[]) == "hello"


async def test_chat_text_returns_empty_string_when_content_is_none():
    assert await chat_text(client=_client(None), model="m", messages=[]) == ""


async def test_chat_text_raises_model_failed_when_there_are_no_choices():
    with pytest.raises(ModelFailed):
        await chat_text(client=_client(choices=[]), model="m", messages=[])


async def test_chat_text_converts_sdk_errors_to_model_errors():
    client = _client(error=openai.APIConnectionError(request=_request()))

    with pytest.raises(ModelUnavailable):
        await chat_text(client=client, model="m", messages=[])
