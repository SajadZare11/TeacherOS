from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import logging
from openai import AsyncOpenAI

from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_FALLBACK_MODELS,
    OPENROUTER_MAX_FALLBACK_MODELS,
    OPENROUTER_MAX_TOKENS,
    OPENROUTER_MODEL,
    OPENROUTER_REQUEST_TIMEOUT_SECONDS,
    OPENROUTER_TOTAL_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

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
            timeout=OPENROUTER_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
        )

    return _client


async def generate_response(
    messages: Sequence[dict[str, Any]],
    *,
    model: str | None = None,
) -> ModelResponse:
    target_models: list[str] = []
    if model:
        target_models.append(model)
        for fb in OPENROUTER_FALLBACK_MODELS:
            if fb != model and fb not in target_models:
                target_models.append(fb)
    else:
        target_models = list(OPENROUTER_FALLBACK_MODELS) or [OPENROUTER_MODEL]

    # A long fallback list increases worst-case latency dramatically. Keep the
    # operator's ordering, but bound attempts; the total deadline remains the
    # final safety net for transient provider failures.
    target_models = target_models[:OPENROUTER_MAX_FALLBACK_MODELS]
    deadline = asyncio.get_running_loop().time() + OPENROUTER_TOTAL_TIMEOUT_SECONDS

    last_exc: Exception | None = None
    for candidate_model in target_models:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        try:
            response = await asyncio.wait_for(
                get_client().chat.completions.create(
                    model=candidate_model,
                    messages=list(messages),
                    response_format={"type": "json_object"},
                    max_tokens=OPENROUTER_MAX_TOKENS,
                ),
                timeout=min(remaining, OPENROUTER_REQUEST_TIMEOUT_SECONDS),
            )

            if not response.choices:
                raise RuntimeError(f"OpenRouter returned no choices for model: {candidate_model}")

            msg = response.choices[0].message
            content = getattr(msg, "content", None) or getattr(msg, "reasoning", None)
            if not content or not str(content).strip():
                raise RuntimeError(f"OpenRouter returned an empty response for model: {candidate_model}")
            content = str(content).strip()

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
        except Exception as exc:
            logger.warning(
                "OpenRouter model '%s' failed (%s). Trying next fallback model immediately...",
                candidate_model,
                exc,
            )
            last_exc = exc

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("All configured OpenRouter fallback models failed.")


async def generate_text(
    messages: Sequence[dict[str, Any]],
    *,
    model: str | None = None,
) -> str:
    """Compatibility helper; product AI surfaces use ai_gateway instead."""
    return (await generate_response(messages, model=model)).content

