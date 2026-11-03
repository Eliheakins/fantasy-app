from __future__ import annotations

import asyncio
import logging

from openai import AsyncOpenAI, OpenAIError

logger = logging.getLogger(__name__)

WARM_INTERVAL_SECONDS = 20.0


async def keep_model_warm(
    client: AsyncOpenAI, model: str, *, interval_seconds: float = WARM_INTERVAL_SECONDS
) -> None:
    """
    Run a one-token completion on a timer so the model's weights stay resident.

    An idle multi-GB model gets paged out on a laptop, and the next real question then waits
    20-40 s for it to come back. A failed ping is normal while the model server is not running.
    """
    while True:
        try:
            await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ok"}],
                max_tokens=1,
                temperature=0,
            )
        except (OpenAIError, OSError) as e:
            logger.debug("Model warm-up ping skipped: %s", e)
        await asyncio.sleep(interval_seconds)
