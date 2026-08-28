from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from config import OPENROUTER_API_KEY, OPENROUTER_MODEL

_client: AsyncOpenAI | None = None


@dataclass(frozen=True)
class ModelResponse:
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


def get_client() -> AsyncOpenAI:
    global _client

    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is missing from the .env file.")

    if _client is None:
        _client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
            timeout=8.0,
            max_retries=0,
        )

    return _client


async def generate_response(
    messages: Sequence[dict[str, Any]],
    *,
    model: str | None = None,
) -> ModelResponse:
    response = await get_client().chat.completions.create(
        model=(model or OPENROUTER_MODEL),
        messages=list(messages),
        response_format={"type": "json_object"},
    )

    if not response.choices:
        raise RuntimeError("OpenRouter returned no choices.")

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError("OpenRouter returned an empty response.")

    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "prompt_tokens", None) if usage is not None else None
    output_tokens = (
        getattr(usage, "completion_tokens", None) if usage is not None else None
    )
    cost = getattr(usage, "cost", None) if usage is not None else None
    return ModelResponse(
        content.strip(),
        input_tokens if isinstance(input_tokens, int) else None,
        output_tokens if isinstance(output_tokens, int) else None,
        float(cost) if isinstance(cost, (int, float)) and cost >= 0 else None,
    )


async def generate_text(
    messages: Sequence[dict[str, Any]],
    *,
    model: str | None = None,
) -> str:
    """Compatibility helper; product AI surfaces use ai_gateway instead."""
    return (await generate_response(messages, model=model)).content

