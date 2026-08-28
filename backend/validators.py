from __future__ import annotations

import json
import re
from dataclasses import dataclass

from prompt_contracts import PromptContract


@dataclass(frozen=True)
class ValidationResult:
    content: str | None
    schema_errors: tuple[str, ...]
    pedagogical_errors: tuple[str, ...]

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


def validate_model_response(raw: object, contract: PromptContract) -> ValidationResult:
    """Validate schema first and pedagogy second; invalid content is never renderable."""
    content, schema_errors = _parse_schema(raw)
    if schema_errors or content is None:
        return ValidationResult(None, tuple(schema_errors), ())
    pedagogy = _pedagogical_errors(content, contract)
    return ValidationResult(content, (), tuple(pedagogy))
