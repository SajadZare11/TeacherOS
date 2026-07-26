from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from openai import AsyncOpenAI

from config import OPENROUTER_API_KEY, OPENROUTER_MODEL

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client

    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is missing from the .env file.")

    if _client is None:
        _client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
            timeout=90.0,
            max_retries=2,
        )

    return _client


async def generate_text(messages: Sequence[dict[str, Any]]) -> str:
    response = await get_client().chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=list(messages),
    )

    if not response.choices:
        raise RuntimeError("OpenRouter returned no choices.")

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError("OpenRouter returned an empty response.")

    return content.strip()

