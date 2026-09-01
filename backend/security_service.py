"""TeacherOS Red-Team Security & Prompt Protection Engine (Day 27).

Defends against cross-user authorization attacks, prompt injections, exfiltration attempts,
directory traversal, MIME spoofing, and oversized denial-of-wallet payloads.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from database import database_connection

logger = logging.getLogger(__name__)

# Reserved Windows file names
_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})

# Prompt injection & exfiltration regex patterns
_INJECTION_PATTERNS = [
    (re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE), "ignore_instructions"),
    (re.compile(r"disregard\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE), "disregard_instructions"),
    (re.compile(r"system\s+override", re.IGNORECASE), "system_override"),
    (re.compile(r"(reveal|print|show|output)\s+(the\s+)?(system\s+prompt|hidden\s+instructions)", re.IGNORECASE), "prompt_exfiltration"),
    (re.compile(r"(reveal|print|show|output)\s+(all\s+)?(student\s+data|database|keys|secrets)", re.IGNORECASE), "data_exfiltration"),
    (re.compile(r"<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]", re.IGNORECASE), "delimiter_injection"),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---------------------------------------------------------------------------
# 1. Path Traversal & Filename Sanitization
# ---------------------------------------------------------------------------

def validate_safe_filename(filename: str, default: str = "document.txt") -> str:
    """Sanitize and validate a filename against path traversal and reserved names."""
    if not isinstance(filename, str) or not filename.strip():
        return default

    # Remove null bytes, control characters, and path separators
    cleaned = filename.replace("\x00", "").replace("/", "").replace("\\", "").strip()
    cleaned = re.sub(r'[\x00-\x1f\x7f<>:"|?*]', "", cleaned)
    cleaned = cleaned.lstrip(". ")

    if not cleaned:
        return default

    stem = Path(cleaned).stem.upper()
    if stem in _RESERVED_NAMES:
        cleaned = f"safe_{cleaned}"

    return cleaned[:100]


# ---------------------------------------------------------------------------
# 2. Prompt Injection & Exfiltration Defense
# ---------------------------------------------------------------------------

def is_potential_prompt_injection(text: str) -> tuple[bool, str | None]:
    """Inspect input text for adversarial prompt injection patterns."""
    if not isinstance(text, str) or not text:
        return False, None

    for pattern, rule_name in _INJECTION_PATTERNS:
        if pattern.search(text):
            return True, rule_name

    return False, None


def sanitize_prompt_input(text: str, max_chars: int = 25000) -> str:
    """Disarm prompt injection delimiters and enforce bounded payload size."""
    if not isinstance(text, str):
        return ""

    # Truncate oversized input to protect against denial-of-wallet
    sanitized = text[:max_chars]

    # Neutralize structural prompt delimiters
    sanitized = re.sub(r"<\|im_start\|>|<\|im_end\|>", "[PROMPT_DELIMITER_REMOVED]", sanitized)
    sanitized = re.sub(r"\[INST\]|\[/INST\]", "[INST_REMOVED]", sanitized)
    sanitized = re.sub(r"^SYSTEM:\s*", "TEACHER_NOTE: ", sanitized, flags=re.IGNORECASE | re.MULTILINE)

    return sanitized


# ---------------------------------------------------------------------------
# 3. File Content & Magic Header Verification
# ---------------------------------------------------------------------------

def validate_file_content(
    content: bytes,
    allowed_types: set[str] | None = None,
    max_bytes: int = 10 * 1024 * 1024,
) -> bool:
    """Verify file byte stream size and standard magic header signatures."""
    if not isinstance(content, bytes) or len(content) == 0:
        return False

    if len(content) > max_bytes:
        return False

    if allowed_types is None:
        return True

    # PDF header: %PDF-
    if "pdf" in allowed_types and content.startswith(b"%PDF-"):
        return True

    # DOCX / ZIP header: PK\x03\x04
    if ("docx" in allowed_types or "zip" in allowed_types) and content.startswith(b"PK\x03\x04"):
        return True

    # Plain text / UTF-8
    if "txt" in allowed_types:
        try:
            content.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False

    return False


# ---------------------------------------------------------------------------
# 4. Security Audit Logging
# ---------------------------------------------------------------------------

def log_security_event(
    *,
    event_type: str,
    severity: str = "medium",
    user_id: int | None = None,
    target_resource: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Record a security violation or audit event in security_audit_logs."""
    if severity not in {"low", "medium", "high", "critical"}:
        severity = "medium"

    log_uuid = f"sec_{uuid.uuid4().hex[:12]}"
    now_str = _utc_now()
    details_json = json.dumps(details or {}, ensure_ascii=False)

    with database_connection(database_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO security_audit_logs (
                log_uuid, user_id, event_type, severity, target_resource,
                details_json, ip_address, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_uuid,
                user_id,
                event_type,
                severity,
                target_resource,
                details_json,
                ip_address,
                now_str,
            ),
        )
        row = conn.execute("SELECT * FROM security_audit_logs WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row) if row else {}
