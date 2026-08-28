from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Mapping

from prompt_contracts import PromptContract


@dataclass(frozen=True)
class ValidationResult:
    content: str | None
    schema_errors: tuple[str, ...]
    pedagogical_errors: tuple[str, ...]
    quality_scores: dict[str, int]

    @property
    def valid(self) -> bool:
        return (
            self.content is not None
            and not self.schema_errors
            and not self.pedagogical_errors
        )

    @property
    def errors(self) -> list[str]:
        return [*self.schema_errors, *self.pedagogical_errors]


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PROTECTED_TRACE_MARKERS = (
    "teacheros structured-output contract",
    "task_prompt and class_context",
    '"class_context":',
    '"teacher_request_untrusted":',
    "hidden chain of thought",
    "internal chain of thought",
    "developer message:",
    "system message:",
)


def _parse_schema(raw: object) -> tuple[str | None, list[str]]:
    if not isinstance(raw, str):
        return None, ["response_not_text"]
    text = raw.strip()
    if not text:
        return None, ["response_empty"]
    if text.startswith("```"):
        return None, ["response_has_code_fence"]
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None, ["response_not_json"]
    if not isinstance(value, dict):
        return None, ["response_not_object"]
    if set(value) != {"content"}:
        return None, ["response_keys_invalid"]
    content = value.get("content")
    if not isinstance(content, str):
        return None, ["content_not_text"]
    normalized = content.strip()
    if not normalized:
        return None, ["content_empty"]
    return normalized, []


def _pedagogical_errors(content: str, contract: PromptContract) -> list[str]:
    errors: list[str] = []
    if len(content) < contract.minimum_content_chars:
        errors.append("content_too_short")
    if len(content) > contract.maximum_content_chars:
        errors.append("content_too_long")
    if _CONTROL_CHARACTERS.search(content):
        errors.append("content_has_control_characters")

    normalized = re.sub(r"\s+", " ", content.casefold())
    for group in contract.required_heading_groups:
        if not any(heading.casefold() in normalized for heading in group):
            errors.append("missing_section:" + "|".join(group))

    for marker in _PROTECTED_TRACE_MARKERS:
        if marker in normalized:
            errors.append("protected_prompt_trace")
            break
    return errors


def _quality_errors(
    content: str,
    requirements: Mapping[str, object],
) -> tuple[list[str], dict[str, int]]:
    """Apply visible, deterministic Day 10 checks before teacher display."""
    normalized = re.sub(r"\s+", " ", content.casefold())
    errors: list[str] = []
    scores: dict[str, int] = {}

    expected_level = str(requirements.get("level") or "").strip().casefold()
    duration = str(requirements.get("duration_minutes") or "").strip()
    objective_required = bool(requirements.get("objective_alignment"))
    answer_key_required = bool(requirements.get("answer_key"))

    checks = {
        "timing": bool(re.search(r"\b(time|timing|minutes?|mins?)\b", normalized))
        and (not duration or bool(re.search(rf"\b{re.escape(duration)}\b", normalized))),
        "instructions": bool(re.search(r"\b(instructions?|procedure|steps?|directions?)\b", normalized)),
        "level": not expected_level
        or bool(re.search(rf"(?<![a-z0-9]){re.escape(expected_level)}(?![a-z0-9])", normalized)),
        "resource_requirements": bool(
            re.search(r"\b(materials?|resources?|equipment|required resources)\b", normalized)
        ),
        "answer_key": not answer_key_required or "answer key" in normalized,
        "objective_alignment": not objective_required
        or bool(re.search(r"\b(objective alignment|aligned objectives?|learning objectives?)\b", normalized)),
    }
    for name, passed in checks.items():
        scores[name] = 100 if passed else 0
        if not passed:
            errors.append(f"quality_failed:{name}")
    scores["overall"] = int(round(sum(scores.values()) / len(scores)))
    return errors, scores


def validate_model_response(
    raw: object,
    contract: PromptContract,
    quality_requirements: Mapping[str, object] | None = None,
) -> ValidationResult:
    """Validate schema first and pedagogy second; invalid content is never renderable."""
    content, schema_errors = _parse_schema(raw)
    if schema_errors or content is None:
        return ValidationResult(None, tuple(schema_errors), (), {})
    pedagogy = _pedagogical_errors(content, contract)
    quality_errors, quality_scores = _quality_errors(
        content, quality_requirements or {}
    ) if quality_requirements else ([], {})
    return ValidationResult(content, (), tuple([*pedagogy, *quality_errors]), quality_scores)
