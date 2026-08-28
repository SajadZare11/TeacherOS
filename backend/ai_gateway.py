from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ai_audit import finish_ai_audit, start_ai_audit
from class_context import ClassContext, build_class_context
from openrouter_client import ModelResponse, generate_response
from prompt_contracts import (
    PromptContract,
    get_prompt_contract,
    repair_instruction,
    render_feature_prompt,
    structured_output_instruction,
)
from validators import ValidationResult, validate_model_response


PROVIDER = "openrouter"
TOTAL_TIMEOUT_SECONDS = 24.0
CALL_TIMEOUT_SECONDS = 8.0
MAX_PROVIDER_ATTEMPTS = 2


class SafeGenerationError(RuntimeError):
    """A controlled failure whose message never contains prompt or response content."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"TeacherOS generation stopped safely ({code}).")


@dataclass(frozen=True)
class GenerationResult:
    content: str
    provider: str
    model: str
    prompt_contract: str
    prompt_version: str
    prompt_hash_sha256: str
    context_hash_sha256: str
    source_record_ids: dict[str, list[int]]
    attempt_count: int
    repair_attempted: bool
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    cost_microusd: int | None


def generation_provenance(result: GenerationResult) -> dict[str, object]:
    """Return the safe subset that may travel with a saved material."""
    return {
        "provider": result.provider,
        "model": result.model,
        "prompt_contract": result.prompt_contract,
        "prompt_version": result.prompt_version,
        "prompt_hash_sha256": result.prompt_hash_sha256,
        "context_hash_sha256": result.context_hash_sha256,
        "source_record_ids": result.source_record_ids,
    }


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _cost_microusd(value: float | None) -> int | None:
    if value is None or value < 0:
        return None
    return int(round(value * 1_000_000))


def _sum_optional(values: list[int | None]) -> int | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _messages(
    contract: PromptContract,
    task_prompt: str,
    class_context: ClassContext,
) -> list[dict[str, str]]:
    payload = json.dumps(
        {
            "TASK_SPECIFICATION": task_prompt,
            "CLASS_CONTEXT": class_context.payload,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return [
        {"role": "system", "content": structured_output_instruction(contract)},
        {"role": "user", "content": payload},
    ]


async def _call_model(
    messages: list[dict[str, str]],
    *,
    model: str,
    deadline: float,
) -> ModelResponse:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("generation_deadline")
    try:
        return await asyncio.wait_for(
            generate_response(messages, model=model),
            timeout=min(CALL_TIMEOUT_SECONDS, remaining),
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError("provider_timeout") from exc


def _repair_messages(
    original: list[dict[str, str]],
    *,
    contract: PromptContract,
    invalid_response: str,
    validation: ValidationResult,
) -> list[dict[str, str]]:
    return [
        *original,
        {"role": "assistant", "content": invalid_response[:60_000]},
        {
            "role": "system",
            "content": repair_instruction(contract, validation.errors),
        },
    ]


async def generate_artifact(
    *,
    feature: str,
    telegram_user_id: int,
    model: str,
    current_request: str,
    prompt_replacements: Mapping[str, object] | None = None,
    class_id: int | None = None,
    database_path: Path | None = None,
) -> GenerationResult:
    """Run the shared request→JSON→validate→repair-once→render pipeline."""
    contract = get_prompt_contract(feature)
    task_prompt = render_feature_prompt(feature, prompt_replacements or {})
    class_context = build_class_context(
        telegram_user_id=telegram_user_id,
        class_id=class_id,
        current_request=current_request,
        database_path=database_path,
    )
    messages = _messages(contract, task_prompt, class_context)
    context_json = json.dumps(
        class_context.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    prompt_hash = _hash_text(
        json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
    )
    context_hash = _hash_text(context_json)
    audit_id = start_ai_audit(
        telegram_user_id=telegram_user_id,
        class_id=class_id,
        feature=feature,
        prompt_contract=contract.name,
        prompt_version=contract.version,
        prompt_hash_sha256=prompt_hash,
        context_hash_sha256=context_hash,
        source_record_ids=class_context.source_record_ids,
        provider=PROVIDER,
        model=model,
        database_path=database_path,
    )

    started = time.monotonic()
    deadline = started + TOTAL_TIMEOUT_SECONDS
    responses: list[ModelResponse] = []
    attempt_count = 0
    repair_attempted = False

    first: ModelResponse | None = None
    last_error: Exception | None = None
    for _ in range(MAX_PROVIDER_ATTEMPTS):
        attempt_count += 1
        try:
            first = await _call_model(messages, model=model, deadline=deadline)
            responses.append(first)
            break
        except Exception as exc:
            last_error = exc
    if first is None:
        elapsed = int((time.monotonic() - started) * 1_000)
        status = "timeout" if isinstance(last_error, TimeoutError) else "provider_failure"
        code = "provider_timeout" if status == "timeout" else "provider_failure"
        finish_ai_audit(
            audit_id,
            status=status,
            attempt_count=attempt_count,
            repair_attempted=False,
            latency_ms=elapsed,
            input_tokens=None,
            output_tokens=None,
            cost_microusd=None,
            error_code=code,
            database_path=database_path,
        )
        raise SafeGenerationError(code) from last_error

    validation = validate_model_response(first.content, contract)
    final = first
    if not validation.valid:
        repair_attempted = True
        attempt_count += 1
        try:
            final = await _call_model(
                _repair_messages(
                    messages,
                    contract=contract,
                    invalid_response=first.content,
                    validation=validation,
                ),
                model=model,
                deadline=deadline,
            )
            responses.append(final)
        except Exception as exc:
            elapsed = int((time.monotonic() - started) * 1_000)
            status = "timeout" if isinstance(exc, TimeoutError) else "provider_failure"
            code = "repair_timeout" if status == "timeout" else "repair_provider_failure"
            finish_ai_audit(
                audit_id,
                status=status,
                attempt_count=attempt_count,
                repair_attempted=True,
                latency_ms=elapsed,
                input_tokens=_sum_optional([item.input_tokens for item in responses]),
                output_tokens=_sum_optional([item.output_tokens for item in responses]),
                cost_microusd=_sum_optional(
                    [_cost_microusd(item.cost_usd) for item in responses]
                ),
                error_code=code,
                database_path=database_path,
            )
            raise SafeGenerationError(code) from exc
        validation = validate_model_response(final.content, contract)

    elapsed = int((time.monotonic() - started) * 1_000)
    input_tokens = _sum_optional([item.input_tokens for item in responses])
    output_tokens = _sum_optional([item.output_tokens for item in responses])
    cost = _sum_optional([_cost_microusd(item.cost_usd) for item in responses])
    if not validation.valid or validation.content is None:
        finish_ai_audit(
            audit_id,
            status="safe_failure",
            attempt_count=attempt_count,
            repair_attempted=repair_attempted,
            latency_ms=elapsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_microusd=cost,
            error_code="validation_failed_after_repair",
            database_path=database_path,
        )
        raise SafeGenerationError("validation_failed_after_repair")

    finish_ai_audit(
        audit_id,
        status="succeeded",
        attempt_count=attempt_count,
        repair_attempted=repair_attempted,
        latency_ms=elapsed,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_microusd=cost,
        error_code=None,
        database_path=database_path,
    )
    return GenerationResult(
        validation.content,
        PROVIDER,
        model,
        contract.name,
        contract.version,
        prompt_hash,
        context_hash,
        class_context.source_record_ids,
        attempt_count,
        repair_attempted,
        elapsed,
        input_tokens,
        output_tokens,
        cost,
    )
