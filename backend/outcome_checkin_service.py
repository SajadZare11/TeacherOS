from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from config import get_usage_timezone
from database import database_connection


RESULTS = {"achieved": "met", "partly_achieved": "partly_met", "needs_reteaching": "not_met"}
RESULT_LABELS = {value: key for key, value in RESULTS.items()}
DIFFICULTY_CATEGORIES = (
    "none",
    "language",
    "instructions",
    "pace",
    "participation",
    "materials",
    "assessment",
)
COMPLETION_STATUSES = {"completed", "partly_completed", "not_completed"}
REMINDER_CHOICES = {"one_hour", "local_18", "local_20", "tomorrow_09"}
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")


def _event_uuid(prefix: str) -> str:
    return f"{prefix}:{secrets.token_hex(12)}"


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _owned_taught_lesson(connection: Any, telegram_user_id: int, lesson_id: int) -> Any:
    return connection.execute(
        """
        SELECT l.*, c.display_name, c.revision AS class_revision,
               c.status AS class_status, u.telegram_user_id
        FROM class_lessons AS l
        JOIN users AS u ON u.id = l.user_id
        JOIN classes AS c ON c.id = l.class_id AND c.user_id = l.user_id
        WHERE u.telegram_user_id = ? AND l.id = ? AND l.lifecycle_state = 'taught'
        """,
        (telegram_user_id, lesson_id),
    ).fetchone()


def _active_outcome(connection: Any, user_id: int, lesson_id: int) -> Any:
    return connection.execute(
        """
        SELECT * FROM lesson_outcomes
        WHERE user_id = ? AND class_lesson_id = ? AND status != 'archived'
        ORDER BY updated_at DESC, id DESC LIMIT 1
        """,
        (user_id, lesson_id),
    ).fetchone()


def _normalize_difficulties(values: Iterable[str]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise ValueError("Difficulty categories must be a collection.")
    unique = {str(value).strip().lower() for value in values}
    if not unique or not unique <= set(DIFFICULTY_CATEGORIES):
        raise ValueError("Choose at least one valid difficulty option.")
    if "none" in unique and len(unique) != 1:
        raise ValueError("No major difficulty cannot be combined with a difficulty.")
    return [value for value in DIFFICULTY_CATEGORIES if value in unique]


def _normalize_note(note: str | None) -> str | None:
    if note is None:
        return None
    raw = str(note)
    # Reject control characters before whitespace normalization. Normalizing
    # first would silently turn newlines/tabs into spaces.
    if _CONTROL_CHARACTERS.search(raw):
        raise ValueError("Keep the optional note between 1 and 1,000 safe characters.")
    normalized = " ".join(raw.split())
    if not normalized:
        return None
    if len(normalized) > 1000:
        raise ValueError("Keep the optional note between 1 and 1,000 safe characters.")
    if _EMAIL.search(normalized) or _PHONE.search(normalized):
        raise ValueError("Do not include email addresses or phone numbers in a class note.")
    return normalized


def _record_revision(connection: Any, outcome: Any, *, reason: str) -> None:
    note = str(outcome["notes"] or "")
    connection.execute(
        """
        INSERT INTO lesson_outcome_fact_revisions (
            event_uuid, lesson_outcome_id, class_lesson_id, class_id, user_id,
            facts_version, result, difficulty_categories_json,
            completion_status, note_present, note_sha256, reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _event_uuid("outcome-facts"), outcome["id"], outcome["class_lesson_id"],
            outcome["class_id"], outcome["user_id"], outcome["facts_version"],
            outcome["result"], outcome["difficulty_categories_json"],
            outcome["completion_status"], 1 if note else 0,
            hashlib.sha256(note.encode("utf-8")).hexdigest() if note else None,
            reason,
        ),
    )


def _outcome_dict(row: Any) -> dict[str, Any]:
    value = dict(row)
    try:
        difficulties = json.loads(str(value.get("difficulty_categories_json") or "[]"))
    except json.JSONDecodeError:
        difficulties = []
    value["difficulty_categories"] = difficulties if isinstance(difficulties, list) else []
    return value


def list_outcome_lessons(
    *, telegram_user_id: int, class_id: int, limit: int = 20,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List owned taught lessons and their latest active outcome for correction."""
    if telegram_user_id < 1 or class_id < 1 or limit < 1 or limit > 50:
        raise ValueError("Invalid outcome lesson request.")
    with database_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT l.id, l.class_id, l.title, l.taught_at,
                   o.id AS outcome_id, o.result, o.difficulty_categories_json,
                   o.completion_status, o.notes, o.facts_version, o.updated_at
            FROM class_lessons AS l
            JOIN users AS u ON u.id = l.user_id
            JOIN classes AS c ON c.id = l.class_id AND c.user_id = l.user_id
            LEFT JOIN lesson_outcomes AS o ON o.id = (
                SELECT candidate.id FROM lesson_outcomes AS candidate
                WHERE candidate.user_id = l.user_id
                  AND candidate.class_lesson_id = l.id
                  AND candidate.status != 'archived'
                ORDER BY candidate.updated_at DESC, candidate.id DESC LIMIT 1
            )
            WHERE u.telegram_user_id = ? AND c.id = ?
              AND l.lifecycle_state = 'taught'
            ORDER BY COALESCE(l.taught_at, l.updated_at) DESC, l.id DESC
            LIMIT ?
            """,
            (telegram_user_id, class_id, limit),
        ).fetchall()
        return [_outcome_dict(row) for row in rows]


def get_lesson_outcome(
    *, telegram_user_id: int, lesson_id: int, database_path: Path | None = None
) -> dict[str, Any] | None:
    with database_connection(database_path) as connection:
        lesson = _owned_taught_lesson(connection, telegram_user_id, lesson_id)
        if lesson is None:
            return None
        outcome = _active_outcome(connection, int(lesson["user_id"]), lesson_id)
        if outcome is None:
            return None
        value = _outcome_dict(outcome)
        value.update(
            {
                "lesson_title": str(lesson["title"]),
                "display_name": str(lesson["display_name"]),
                "class_revision": int(lesson["class_revision"]),
            }
        )
        return value


def save_outcome_facts(
    *, telegram_user_id: int, lesson_id: int, result: str,
    difficulty_categories: Iterable[str], completion_status: str,
    database_path: Path | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    """Create or correct one active three-tap outcome without duplicating it."""
    normalized_result = RESULTS.get(str(result).strip().lower(), str(result).strip().lower())
    if normalized_result not in RESULTS.values():
        raise ValueError("Choose achieved, partly achieved, or needs reteaching.")
    normalized_difficulties = _normalize_difficulties(difficulty_categories)
    normalized_completion = str(completion_status).strip().lower()
    if normalized_completion not in COMPLETION_STATUSES:
        raise ValueError("Choose a valid completion status.")
    difficulty_json = json.dumps(normalized_difficulties, separators=(",", ":"))
    with database_connection(database_path) as connection:
        lesson = _owned_taught_lesson(connection, telegram_user_id, lesson_id)
        if lesson is None or lesson["class_status"] != "active":
            return None, False
        existing = _active_outcome(connection, int(lesson["user_id"]), lesson_id)
        if existing is not None:
            unchanged = (
                str(existing["result"]) == normalized_result
                and str(existing["difficulty_categories_json"]) == difficulty_json
                and str(existing["completion_status"] or "") == normalized_completion
                and str(existing["capture_source"]) == "three_tap"
            )
            if unchanged:
                value = _outcome_dict(existing)
                value.update({"lesson_title": lesson["title"], "display_name": lesson["display_name"]})
                return value, False
            connection.execute(
                """
                UPDATE lesson_outcomes
                SET result = ?, difficulty_categories_json = ?, completion_status = ?,
                    capture_source = 'three_tap', status = 'approved',
                    facts_version = facts_version + 1,
                    saved_at = COALESCE(saved_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ? AND user_id = ?
                """,
                (
                    normalized_result, difficulty_json, normalized_completion,
                    existing["id"], lesson["user_id"],
                ),
            )
            reason = "three_tap_corrected"
            outcome_id = int(existing["id"])
        else:
            cursor = connection.execute(
                """
                INSERT INTO lesson_outcomes (
                    class_lesson_id, class_id, user_id, result,
                    difficulty_categories_json, completion_status,
                    capture_source, status, saved_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'three_tap', 'approved',
                          strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (
                    lesson_id, lesson["class_id"], lesson["user_id"], normalized_result,
                    difficulty_json, normalized_completion,
                ),
            )
            outcome_id = int(cursor.lastrowid)
            reason = "three_tap_created"
        outcome = connection.execute(
            "SELECT * FROM lesson_outcomes WHERE id = ? AND user_id = ?",
            (outcome_id, lesson["user_id"]),
        ).fetchone()
        if outcome is None:
            raise RuntimeError("TeacherOS could not read the saved outcome.")
        _record_revision(connection, outcome, reason=reason)
        connection.execute(
            """
            INSERT OR IGNORE INTO product_events (
                event_uuid, user_id, class_id, class_lesson_id,
                event_name, privacy_class, properties_json, occurred_at
            ) VALUES (?, ?, ?, ?, 'outcome_saved', 'operational', ?,
                      strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            """,
            (
                f"outcome-saved:{outcome_id}:v{outcome['facts_version']}",
                lesson["user_id"], lesson["class_id"], lesson_id,
                json.dumps({"facts_version": int(outcome["facts_version"])}),
            ),
        )
        connection.execute(
            "UPDATE classes SET last_active_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
            "WHERE id = ? AND user_id = ?",
            (lesson["class_id"], lesson["user_id"]),
        )
        value = _outcome_dict(outcome)
        value.update({"lesson_title": lesson["title"], "display_name": lesson["display_name"]})
        return value, True


def update_outcome_note(
    *, telegram_user_id: int, lesson_id: int, note: str | None,
    database_path: Path | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    """Add, correct, or clear the optional teacher note on an owned saved outcome."""
    normalized = _normalize_note(note)
    with database_connection(database_path) as connection:
        lesson = _owned_taught_lesson(connection, telegram_user_id, lesson_id)
        if lesson is None or lesson["class_status"] != "active":
            return None, False
        existing = _active_outcome(connection, int(lesson["user_id"]), lesson_id)
        if existing is None:
            return None, False
        previous_text = " ".join(str(existing["notes"] or "").split())
        previous = previous_text or None
        if previous == normalized:
            value = _outcome_dict(existing)
            value.update({"lesson_title": lesson["title"], "display_name": lesson["display_name"]})
            return value, False
        connection.execute(
            """
            UPDATE lesson_outcomes
            SET notes = ?, note_updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                facts_version = facts_version + 1
            WHERE id = ? AND user_id = ?
            """,
            (normalized, existing["id"], lesson["user_id"]),
        )
        outcome = connection.execute(
            "SELECT * FROM lesson_outcomes WHERE id = ?", (existing["id"],)
        ).fetchone()
        reason = "note_cleared" if normalized is None else ("note_updated" if previous else "note_added")
        _record_revision(connection, outcome, reason=reason)
        value = _outcome_dict(outcome)
        value.update({"lesson_title": lesson["title"], "display_name": lesson["display_name"]})
        return value, True


def outcome_recording_metrics(
    *, telegram_user_id: int, class_id: int | None = None,
    database_path: Path | None = None,
) -> dict[str, int]:
    """Measure actual outcome capture among explicitly taught lessons."""
    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (telegram_user_id,)
        ).fetchone()
        if user is None:
            return {"taught": 0, "outcomes_recorded": 0, "recording_rate_percent": 0}
        class_filter = " AND l.class_id = ?" if class_id is not None else ""
        parameters: list[Any] = [int(user["id"])]
        if class_id is not None:
            parameters.append(class_id)
        row = connection.execute(
            f"""
            SELECT COUNT(*) AS taught,
                   SUM(CASE WHEN EXISTS (
                       SELECT 1 FROM lesson_outcomes AS o
                       WHERE o.user_id = l.user_id AND o.class_lesson_id = l.id
                         AND o.status != 'archived'
                   ) THEN 1 ELSE 0 END) AS outcomes_recorded
            FROM class_lessons AS l
            WHERE l.user_id = ? AND l.lifecycle_state = 'taught'{class_filter}
            """,
            parameters,
        ).fetchone()
        taught = int(row["taught"] or 0)
        recorded = int(row["outcomes_recorded"] or 0)
        return {
            "taught": taught,
            "outcomes_recorded": recorded,
            "recording_rate_percent": int(round((recorded / taught) * 100)) if taught else 0,
        }


def reminder_due_utc(choice: str, *, now_utc: datetime | None = None) -> datetime:
    normalized = str(choice).strip().lower()
    if normalized not in REMINDER_CHOICES:
        raise ValueError("Choose a valid reminder time.")
    current = now_utc or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if normalized == "one_hour":
        return current.astimezone(timezone.utc) + timedelta(hours=1)
    local = current.astimezone(get_usage_timezone())
    hour = 18 if normalized == "local_18" else 20 if normalized == "local_20" else 9
    days = 1 if normalized == "tomorrow_09" else 0
    due_local = (local + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    if due_local <= local:
        due_local += timedelta(days=1)
    return due_local.astimezone(timezone.utc)


def schedule_outcome_reminder(
    *, telegram_user_id: int, lesson_id: int, choice: str,
    now_utc: datetime | None = None, database_path: Path | None = None,
) -> dict[str, Any]:
    """Schedule one explicit, one-shot reminder; never create a repeating reminder."""
    due = _iso_utc(reminder_due_utc(choice, now_utc=now_utc))
    normalized = str(choice).strip().lower()
    with database_connection(database_path) as connection:
        lesson = _owned_taught_lesson(connection, telegram_user_id, lesson_id)
        if lesson is None or lesson["class_status"] != "active":
            return {"status": "unavailable", "reminder": None}
        if _active_outcome(connection, int(lesson["user_id"]), lesson_id) is not None:
            return {"status": "completed", "reminder": None}
        existing = connection.execute(
            "SELECT * FROM lesson_outcome_reminders WHERE user_id = ? AND class_lesson_id = ?",
            (lesson["user_id"], lesson_id),
        ).fetchone()
        if existing is not None and int(existing["prompt_count"]) >= 3:
            return {"status": "limit", "reminder": dict(existing)}
        if (
            existing is not None and existing["status"] == "pending"
            and existing["local_choice"] == normalized
        ):
            return {"status": "already_scheduled", "reminder": dict(existing)}
        connection.execute(
            """
            INSERT INTO lesson_outcome_reminders (
                class_lesson_id, class_id, user_id, local_choice,
                next_prompt_at_utc, status
            ) VALUES (?, ?, ?, ?, ?, 'pending')
            ON CONFLICT(user_id, class_lesson_id) DO UPDATE SET
                local_choice = excluded.local_choice,
                next_prompt_at_utc = excluded.next_prompt_at_utc,
                status = 'pending',
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (lesson_id, lesson["class_id"], lesson["user_id"], normalized, due),
        )
        reminder = connection.execute(
            "SELECT * FROM lesson_outcome_reminders WHERE user_id = ? AND class_lesson_id = ?",
            (lesson["user_id"], lesson_id),
        ).fetchone()
        return {"status": "scheduled", "reminder": dict(reminder)}


def claim_due_outcome_reminders(
    *, now_utc: datetime | None = None, limit: int = 20,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Claim due one-shot reminders before delivery to avoid duplicate sends."""
    if limit < 1 or limit > 50:
        raise ValueError("Reminder batch size must be between 1 and 50.")
    now = _iso_utc(now_utc or datetime.now(timezone.utc))
    with database_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT r.*, u.telegram_user_id, c.display_name, c.revision AS class_revision,
                   l.title AS lesson_title
            FROM lesson_outcome_reminders AS r
            JOIN users AS u ON u.id = r.user_id
            JOIN classes AS c ON c.id = r.class_id AND c.user_id = r.user_id
            JOIN class_lessons AS l ON l.id = r.class_lesson_id
                AND l.class_id = r.class_id AND l.user_id = r.user_id
            WHERE r.status = 'pending' AND r.next_prompt_at_utc <= ?
              AND r.prompt_count < 3 AND c.status = 'active'
              AND l.lifecycle_state = 'taught'
              AND NOT EXISTS (
                  SELECT 1 FROM lesson_outcomes AS o
                  WHERE o.user_id = r.user_id AND o.class_lesson_id = r.class_lesson_id
                    AND o.status != 'archived'
              )
            ORDER BY r.next_prompt_at_utc, r.id LIMIT ?
            """,
            (now, limit),
        ).fetchall()
        claimed: list[dict[str, Any]] = []
        for row in rows:
            cursor = connection.execute(
                """
                UPDATE lesson_outcome_reminders
                SET status = 'delivered', prompt_count = prompt_count + 1,
                    last_prompted_at_utc = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ? AND status = 'pending'
                """,
                (now, row["id"]),
            )
            if cursor.rowcount == 1:
                value = dict(row)
                value["prompt_count"] = int(row["prompt_count"]) + 1
                claimed.append(value)
        return claimed


def release_failed_reminder(
    *, reminder_id: int, database_path: Path | None = None
) -> None:
    """Retry a failed transport once after backoff without counting it as a prompt."""
    retry = _iso_utc(datetime.now(timezone.utc) + timedelta(minutes=15))
    with database_connection(database_path) as connection:
        connection.execute(
            """
            UPDATE lesson_outcome_reminders
            SET status = 'pending', prompt_count = MAX(prompt_count - 1, 0),
                next_prompt_at_utc = ?, last_prompted_at_utc = NULL,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ? AND status = 'delivered'
            """,
            (retry, reminder_id),
        )
