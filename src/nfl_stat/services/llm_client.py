from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, cast

from fastapi import HTTPException
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, OpenAIError
from openai.types.chat import ChatCompletionMessageParam

logger = logging.getLogger(__name__)

ChatMessage = dict[str, Any]


def http_exception_from_llm_error(exc: BaseException, base_url: str) -> HTTPException:
    """Map SDK errors to client-safe responses; details go to the server log."""
    if isinstance(exc, APITimeoutError):
        logger.error("Local model request timed out (%s)", base_url)
        return HTTPException(status_code=504, detail="The local model took too long. Try again.")
    if isinstance(exc, APIConnectionError):
        logger.error("Cannot reach local model server at %s", base_url)
        return HTTPException(
            status_code=503,
            detail=(
                f"Local model server is not reachable at {base_url}. "
                "Start it with: uv run --group llm mlx_lm.server --model <LLM_MODEL>"
            ),
        )
    if isinstance(exc, APIStatusError):
        logger.error("Local model server returned %s: %s", exc.status_code, exc.response.text[:500])
        return HTTPException(
            status_code=502,
            detail=f"The local model server returned an error ({exc.status_code}).",
        )
    logger.exception("Unexpected LLM error: %s", exc)
    return HTTPException(status_code=502, detail="The local model request failed.")


async def chat_text(
    *,
    client: AsyncOpenAI,
    model: str,
    messages: Sequence[ChatMessage],
    max_tokens: int = 300,
) -> str:
    try:
        completion = await client.chat.completions.create(
            model=model,
            messages=cast("list[ChatCompletionMessageParam]", list(messages)),
            temperature=0,
            max_tokens=max_tokens,
        )
    except (OpenAIError, OSError) as e:
        raise http_exception_from_llm_error(e, str(client.base_url)) from e

    if not completion.choices:
        raise HTTPException(status_code=502, detail="The local model returned no output.")
    return (completion.choices[0].message.content or "").strip()
