from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, cast

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, OpenAIError
from openai.types.chat import ChatCompletionMessageParam

logger = logging.getLogger(__name__)

ChatMessage = dict[str, Any]


class ModelError(Exception):
    """The model call failed; `str(err)` is safe to show. The router maps it to HTTP."""


class ModelUnavailable(ModelError):
    """The model server cannot be reached."""


class ModelTimeout(ModelError):
    """The model server took too long."""


class ModelFailed(ModelError):
    """The model server answered with an error, or with nothing usable."""


def model_error_from_llm_error(exc: BaseException, base_url: str) -> ModelError:
    """Map SDK errors to client-safe domain errors; details go to the server log."""
    if isinstance(exc, APITimeoutError):
        logger.error("Local model request timed out (%s)", base_url)
        return ModelTimeout("The local model took too long. Try again.")
    if isinstance(exc, APIConnectionError):
        logger.error("Cannot reach local model server at %s", base_url)
        return ModelUnavailable(
            (
                f"Local model server is not reachable at {base_url}. "
                "Start it with: uv run --group llm mlx_lm.server --model <LLM_MODEL>"
            ),
        )
    if isinstance(exc, APIStatusError):
        logger.error("Local model server returned %s: %s", exc.status_code, exc.response.text[:500])
        return ModelFailed(
            f"The local model server returned an error ({exc.status_code}).",
        )
    logger.exception("Unexpected LLM error: %s", exc)
    return ModelFailed("The local model request failed.")


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
        raise model_error_from_llm_error(e, str(client.base_url)) from e

    if not completion.choices:
        raise ModelFailed("The local model returned no output.")
    return (completion.choices[0].message.content or "").strip()
