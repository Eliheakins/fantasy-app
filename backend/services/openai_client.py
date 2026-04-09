from __future__ import annotations

import logging

from fastapi import HTTPException
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    OpenAIError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


def http_exception_from_openai_error(exc: BaseException) -> HTTPException:
    """Map OpenAI SDK errors to safe client responses; log details server-side."""
    if isinstance(exc, APITimeoutError):
        logger.exception("OpenAI request timed out")
        return HTTPException(
            status_code=504,
            detail="The language model request timed out. Try again in a moment.",
        )
    if isinstance(exc, APIConnectionError):
        logger.exception("OpenAI connection error")
        return HTTPException(
            status_code=502,
            detail="Could not reach the language model service. Try again later.",
        )
    if isinstance(exc, RateLimitError):
        logger.warning("OpenAI rate limited: %s", exc)
        return HTTPException(
            status_code=429,
            detail="The language model is temporarily rate-limited. Try again shortly.",
        )
    if isinstance(exc, AuthenticationError):
        logger.error("OpenAI authentication failed (check API key configuration)")
        return HTTPException(
            status_code=503,
            detail="NLQ is misconfigured on the server.",
        )
    if isinstance(exc, APIStatusError):
        logger.exception("OpenAI API status error: %s", exc)
        return HTTPException(
            status_code=502,
            detail="The language model returned an error. Try again later.",
        )
    if isinstance(exc, OpenAIError):
        logger.exception("OpenAI error: %s", exc)
        return HTTPException(
            status_code=502,
            detail="The language model request failed. Try again later.",
        )
    logger.exception("Unexpected error during OpenAI call")
    return HTTPException(
        status_code=502,
        detail="The language model request failed. Try again later.",
    )


async def openai_chat_text(
    *,
    client: AsyncOpenAI,
    model: str,
    system: str,
    user_content: str,
    max_tokens: int,
) -> str:
    try:
        completion = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
        )
    except (OpenAIError, APIConnectionError, APITimeoutError, RateLimitError, AuthenticationError, APIStatusError) as e:
        raise http_exception_from_openai_error(e) from e
    except Exception:
        logger.exception("Unexpected error in openai_chat_text")
        raise HTTPException(
            status_code=502,
            detail="The language model request failed. Try again later.",
        ) from None

    if not completion.choices:
        raise HTTPException(
            status_code=502,
            detail="The language model returned no output choices.",
        )
    content = completion.choices[0].message.content
    if content is None:
        return ""
    return content.strip()
