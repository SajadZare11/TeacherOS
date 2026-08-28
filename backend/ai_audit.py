from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Mapping, Sequence

from database import database_connection


_SOURCE_TABLES = {
    "classes",
    "class_objectives",
    "class_lessons",
    "lesson_outcomes",
    "class_action_items",
    "materials",
}
_STATUSES = {"succeeded", "safe_failure", "provider_failure", "timeout"}
_HASH = re.compile(r"^[0-9a-f]{64}$")
_CODE = re.compile(r"^[a-z0-9_:-]{1,80}$")


def _clean_source_ids(
    value: Mapping[str, Sequence[int]],
) -> dict[str, list[int]]:
    unknown = set(value) - _SOURCE_TABLES
    if unknown:
        raise ValueError("Unsupported AI provenance source category.")
    result: dict[str, list[int]] = {}
    for table in sorted(value):
        identifiers = value[table]
        cleaned = sorted(
            {
                int(identifier)
                for identifier in identifiers
                if isinstance(identifier, int)
                and not isinstance(identifier, bool)
                and identifier > 0
            }
        )[:50]
        result[table] = cleaned
    return result


def start_ai_audit(
    *,
    telegram_user_id: int,
    class_id: int | None,
    feature: str,
    prompt_contract: str,
    prompt_version: str,
    prompt_hash_sha256: str,
    context_hash_sha256: str,
    source_record_ids: Mapping[str, Sequence[int]],
    provider: str,
    model: str,
    database_path: Path | None = None,
) -> int:
    """Store hashes, record IDs, and routing metadata—never prompt/response text."""
    if not _HASH.fullmatch(prompt_hash_sha256) or not _HASH.fullmatch(
        context_hash_sha256
    ):
        raise ValueError("AI audit hashes must be lowercase SHA-256 values.")
    sources_json = json.dumps(
        _clean_source_ids(source_record_ids), separators=(",", ":"), sort_keys=True
    )
    with database_connection(database_path) as connection:
        user_row = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        if user_row is None:
            raise RuntimeError("AI audit requires a registered TeacherOS user.")
        cursor = connection.execute(
            """
            INSERT INTO ai_generation_audits (
                request_id, user_id, class_id, feature,
                prompt_contract, prompt_version,
                prompt_hash_sha256, context_hash_sha256,
                source_record_ids_json, provider, model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                int(user_row["id"]),
                class_id,
                feature,
                prompt_contract,
                prompt_version,
                prompt_hash_sha256,
                context_hash_sha256,
                sources_json,
                provider,
                model,
            ),
        )
        return int(cursor.lastrowid)


def finish_ai_audit(
    audit_id: int | None,
    *,
    status: str,
    attempt_count: int,
    repair_attempted: bool,
    latency_ms: int,
    input_tokens: int | None,
    output_tokens: int | None,
    cost_microusd: int | None,
    error_code: str | None,
    database_path: Path | None = None,
) -> None:
    if audit_id is None:
        return
    if status not in _STATUSES:
        raise ValueError("Unsupported AI audit completion status.")
    if not 0 <= attempt_count <= 3:
        raise ValueError("AI attempt count is out of range.")
    if error_code is not None and not _CODE.fullmatch(error_code):
        raise ValueError("AI audit error code is not safe.")
    with database_connection(database_path) as connection:
        connection.execute(
            """
            UPDATE ai_generation_audits
            SET status = ?, attempt_count = ?, repair_attempted = ?,
                latency_ms = ?, input_tokens = ?, output_tokens = ?,
                cost_microusd = ?, error_code = ?,
                completed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ? AND status = 'started'
            """,
            (
                status,
                attempt_count,
                int(repair_attempted),
                max(0, int(latency_ms)),
                input_tokens,
                output_tokens,
                cost_microusd,
                error_code,
                audit_id,
            ),
        )
