from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from class_service import ClassFeatureDisabledError
from database import database_connection
from feature_flags import feature_enabled


PROFILE_FIELDS = (
    "display_name",
    "level",
    "age_group",
    "learner_count_band",
    "lesson_duration_minutes",
    "goal",
    "weak_areas",
    "coursebook",
    "equipment",
    "teaching_preferences",
)
ACTION_ITEM_TYPES = {"analysis_approval", "review_due"}
_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2", "not_sure"}
_AGES = {"young_learners", "teens", "adults", "mixed", "not_sure"}
_SIZES = {"one_to_one", "2_5", "6_12", "13_20", "21_plus", "not_sure"}
_DURATIONS = {30, 45, 60, 90, "not_sure"}
_GOALS = {
    "general_english",
    "conversation",
    "exam_preparation",
    "business_english",
    "academic_english",
    "travel_english",
}
_WEAK = {"spk", "lst", "read", "write", "gram", "vocab", "pron", "ns"}
_EQUIPMENT = {"board", "proj", "audio", "print", "net", "none", "ns"}
_PREFERENCES = {"comm", "struct", "task", "game", "exam", "balanced", "ns"}
_CONTACT = re.compile(
    r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|\b\+?\d[\d -]{7,}\d\b"
)


def _require_classes() -> None:
    if not feature_enabled("classes"):
        raise ClassFeatureDisabledError("Class dashboards are not enabled.")


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{label} must be a positive integer.")
    return value


def _owned_class(connection: Any, telegram_user_id: int, class_id: int) -> Any:
    return connection.execute(
        """
        SELECT c.* FROM classes AS c
        JOIN users AS u ON u.id = c.user_id
        WHERE c.id = ? AND u.telegram_user_id = ?
        """,
        (_positive(class_id, "Class ID"), _positive(telegram_user_id, "Telegram user ID")),
    ).fetchone()


def _text(value: object, *, maximum: int, words: int, optional: bool = False) -> str | None:
    if not isinstance(value, str):
        raise ValueError("Expected text.")
    normalized = " ".join(value.split())
    if not normalized and optional:
        return None
    if not normalized or len(normalized) > maximum or len(normalized.split()) > words:
        raise ValueError("Expected one short phrase.")
    if _CONTACT.search(normalized):
        raise ValueError("Contact details are not permitted in a class profile.")
    return normalized


def _choice(value: object, allowed: set[Any]) -> Any:
    if value not in allowed:
        raise ValueError("Unsupported profile choice.")
    return value


def _choices(value: object, allowed: set[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("Choose at least one profile option.")
    normalized = list(dict.fromkeys(str(item) for item in value))
    if set(normalized) - allowed:
        raise ValueError("Unsupported profile choices.")
    if "ns" in normalized and len(normalized) > 1:
        raise ValueError("Not sure cannot be combined with other choices.")
    if "none" in normalized and len(normalized) > 1:
        raise ValueError("None cannot be combined with other choices.")
    return normalized


def _opaque_source_key(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Action source key must be text.")
    normalized = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", normalized):
        raise ValueError("Action source key must be an opaque identifier.")
    return normalized


def _due_timestamp(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value.strip()) > 50:
        raise ValueError("Review due time is invalid.")
    normalized = value.strip()
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Review due time must be ISO-8601.") from exc
    return normalized


def _profile(row: Any) -> dict[str, Any]:
    try:
        value = json.loads(str(row["setup_profile_json"] or "{}"))
    except json.JSONDecodeError:
        value = {}
    return value if isinstance(value, dict) else {}


def touch_class_activity(
    *, telegram_user_id: int, class_id: int, database_path: Path | None = None
) -> bool:
    """Update activity without invalidating a revisioned read-only keyboard."""
    _require_classes()
    with database_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE classes
            SET last_active_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ? AND user_id = (
                SELECT id FROM users WHERE telegram_user_id = ?
            )
            """,
            (_positive(class_id, "Class ID"), _positive(telegram_user_id, "Telegram user ID")),
        )
        return cursor.rowcount == 1


def update_profile_field(
    *,
    telegram_user_id: int,
    class_id: int,
    field: str,
    value: Any,
    expected_revision: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Update exactly one owned active-class profile field and its explicit setup value."""
    _require_classes()
    if field not in PROFILE_FIELDS:
        raise ValueError("Unsupported class profile field.")
    with database_connection(database_path) as connection:
        row = _owned_class(connection, telegram_user_id, class_id)
        if (
            row is None
            or row["status"] != "active"
            or int(row["revision"]) != _positive(expected_revision, "Expected revision")
        ):
            return None
        profile = _profile(row)
        assignments: dict[str, Any] = {}

        if field == "display_name":
            normalized = _text(value, maximum=60, words=10)
            assignments["display_name"] = normalized
            profile["display_name"] = normalized
        elif field == "level":
            normalized = _choice(value, _LEVELS)
            assignments["level"] = None if normalized == "not_sure" else normalized
            profile["level_choice"] = normalized
        elif field == "age_group":
            normalized = _choice(value, _AGES)
            assignments["age_group"] = None if normalized == "not_sure" else normalized
            profile["age_group_choice"] = normalized
        elif field == "learner_count_band":
            normalized = _choice(value, _SIZES)
            assignments["learner_count_band"] = None if normalized == "not_sure" else normalized
            profile["learner_count_band_choice"] = normalized
        elif field == "lesson_duration_minutes":
            normalized = _choice(value, _DURATIONS)
            assignments[field] = None if normalized == "not_sure" else normalized
            profile["duration_choice"] = normalized
        elif field == "goal":
            normalized = _choice(value, _GOALS)
            assignments["goal"] = normalized
            profile["goal_choice"] = normalized
        elif field == "weak_areas":
            normalized = _choices(value, _WEAK)
            assignments["weak_areas_json"] = json.dumps(normalized, sort_keys=True)
            profile["weak_areas"] = normalized
        elif field == "equipment":
            normalized = _choices(value, _EQUIPMENT)
            assignments["equipment_json"] = json.dumps(normalized, sort_keys=True)
            profile["equipment"] = normalized
        elif field == "teaching_preferences":
            normalized = _choices(value, _PREFERENCES)
            assignments["teaching_preferences_json"] = json.dumps(normalized, sort_keys=True)
            profile["teaching_preferences"] = normalized
        else:
            if not isinstance(value, dict):
                raise ValueError("Coursebook edit is invalid.")
            state = value.get("coursebook_state")
            if state not in {"provided", "skipped"}:
                raise ValueError("Coursebook state is invalid.")
            book = None
            unit = None
            if state == "provided":
                book = _text(value.get("coursebook"), maximum=60, words=10)
                raw_unit = value.get("coursebook_unit")
                unit = (
                    _text(raw_unit, maximum=30, words=5, optional=True)
                    if isinstance(raw_unit, str)
                    else None
                )
            assignments.update({"coursebook": book, "coursebook_unit": unit})
            profile.update(
                {
                    "coursebook_state": state,
                    "coursebook": book,
                    "coursebook_unit": unit,
                }
            )

        assignments["setup_profile_json"] = json.dumps(
            profile, ensure_ascii=False, sort_keys=True
        )
        sql_assignments = [f"{column} = ?" for column in assignments]
        sql_assignments.extend(
            [
                "revision = revision + 1",
                "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
                "last_active_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
            ]
        )
        parameters = list(assignments.values()) + [class_id, row["user_id"], expected_revision]
        cursor = connection.execute(
            f"""
            UPDATE classes SET {', '.join(sql_assignments)}
            WHERE id = ? AND user_id = ? AND status = 'active' AND revision = ?
            """,
            parameters,
        )
        if cursor.rowcount != 1:
            return None
        updated = connection.execute(
            "SELECT * FROM classes WHERE id = ? AND user_id = ?",
            (class_id, row["user_id"]),
        ).fetchone()
        return dict(updated) if updated is not None else None


def set_class_archived(
    *,
    telegram_user_id: int,
    class_id: int,
    archive: bool,
    expected_revision: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Archive or restore after the UI's explicit confirmation, preserving linked rows."""
    _require_classes()
    expected_status = "active" if archive else "archived"
    new_status = "archived" if archive else "active"
    archived_value = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')" if archive else "NULL"
    with database_connection(database_path) as connection:
        row = _owned_class(connection, telegram_user_id, class_id)
        if row is None:
            return None
        cursor = connection.execute(
            f"""
            UPDATE classes
            SET status = ?, archived_at = {archived_value},
                revision = revision + 1,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                last_active_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ? AND user_id = ? AND status = ? AND revision = ?
            """,
            (
                new_status,
                class_id,
                row["user_id"],
                expected_status,
                _positive(expected_revision, "Expected revision"),
            ),
        )
        if cursor.rowcount != 1:
            return None
        updated = connection.execute(
            "SELECT * FROM classes WHERE id = ? AND user_id = ?",
            (class_id, row["user_id"]),
        ).fetchone()
        return dict(updated) if updated is not None else None


def create_class_action_item(
    *,
    telegram_user_id: int,
    class_id: int,
    item_type: str,
    source_key: str,
    due_at: str | None = None,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Register a bounded, content-free Today item for later evidence/review workflows."""
    _require_classes()
    if item_type not in ACTION_ITEM_TYPES:
        raise ValueError("Unsupported class action item.")
    normalized_source = _opaque_source_key(source_key)
    normalized_due = _due_timestamp(due_at)
    with database_connection(database_path) as connection:
        row = _owned_class(connection, telegram_user_id, class_id)
        if row is None or row["status"] != "active":
            return None
        connection.execute(
            """
            INSERT OR IGNORE INTO class_action_items (
                class_id, user_id, item_type, source_key, due_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (class_id, row["user_id"], item_type, normalized_source, normalized_due),
        )
        connection.execute(
            "UPDATE classes SET last_active_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
            "WHERE id = ? AND user_id = ?",
            (class_id, row["user_id"]),
        )
        item = connection.execute(
            """
            SELECT * FROM class_action_items
            WHERE user_id = ? AND class_id = ? AND item_type = ? AND source_key = ?
            """,
            (row["user_id"], class_id, item_type, normalized_source),
        ).fetchone()
        return dict(item) if item is not None else None


def resolve_class_action_item(
    *,
    telegram_user_id: int,
    item_id: int,
    resolution: str,
    database_path: Path | None = None,
) -> bool:
    """Complete or dismiss one owned Today item; retries are idempotent."""
    _require_classes()
    if resolution not in {"completed", "dismissed"}:
        raise ValueError("Unsupported action-item resolution.")
    with database_connection(database_path) as connection:
        owner_id = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?",
            (_positive(telegram_user_id, "Telegram user ID"),),
        ).fetchone()
        if owner_id is None:
            return False
        row = connection.execute(
            "SELECT * FROM class_action_items WHERE id = ? AND user_id = ?",
            (_positive(item_id, "Action item ID"), int(owner_id["id"])),
        ).fetchone()
        if row is None:
            return False
        if row["status"] == resolution:
            return True
        if row["status"] != "pending":
            return False
        cursor = connection.execute(
            """
            UPDATE class_action_items
            SET status = ?, resolved_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ? AND user_id = ? AND status = 'pending'
            """,
            (resolution, item_id, int(owner_id["id"])),
        )
        if cursor.rowcount != 1:
            return False
        connection.execute(
            "UPDATE classes SET last_active_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
            "WHERE id = ? AND user_id = ?",
            (row["class_id"], int(owner_id["id"])),
        )
        return True


def class_dashboard_snapshot(
    *, telegram_user_id: int, class_id: int, database_path: Path | None = None
) -> dict[str, Any] | None:
    """Return the bounded, owner-scoped facts needed for one phone-sized class home."""
    _require_classes()
    with database_connection(database_path) as connection:
        class_row = _owned_class(connection, telegram_user_id, class_id)
        if class_row is None:
            return None
        user_id = int(class_row["user_id"])
        planned = connection.execute(
            """
            SELECT id, material_id, title, scheduled_for, lifecycle_state AS status
            FROM class_lessons
            WHERE user_id = ? AND class_id = ? AND lifecycle_state = 'planned'
            ORDER BY scheduled_for IS NULL, scheduled_for, id
            LIMIT 1
            """,
            (user_id, class_id),
        ).fetchone()
        last_outcome = connection.execute(
            """
            SELECT o.id, o.result, o.confidence, o.support_needed, o.status,
                   o.difficulty_categories_json, o.completion_status,
                   o.facts_version, o.updated_at, l.title AS lesson_title
            FROM lesson_outcomes AS o
            JOIN class_lessons AS l ON l.id = o.class_lesson_id
            WHERE o.user_id = ? AND o.class_id = ? AND o.status IN ('saved', 'approved')
            ORDER BY o.updated_at DESC, o.id DESC LIMIT 1
            """,
            (user_id, class_id),
        ).fetchone()
        last_outcome_value = dict(last_outcome) if last_outcome is not None else None
        difficulty = None
        if last_outcome_value is not None:
            try:
                categories = json.loads(
                    str(last_outcome_value.get("difficulty_categories_json") or "[]")
                )
            except json.JSONDecodeError:
                categories = []
            last_outcome_value["difficulty_categories"] = (
                categories if isinstance(categories, list) else []
            )
            if (
                last_outcome_value["result"] in {"not_met", "partly_met"}
                or last_outcome_value["support_needed"] in {"some", "substantial"}
                or any(item != "none" for item in last_outcome_value["difficulty_categories"])
            ):
                difficulty = last_outcome_value
        action_counts = {
            str(row["item_type"]): int(row["item_count"])
            for row in connection.execute(
                """
                SELECT item_type, COUNT(*) AS item_count FROM class_action_items
                WHERE user_id = ? AND class_id = ? AND status = 'pending'
                  AND (item_type != 'review_due' OR due_at IS NULL
                       OR due_at <= strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                GROUP BY item_type
                """,
                (user_id, class_id),
            ).fetchall()
        }
        history = connection.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM class_lessons WHERE user_id = ? AND class_id = ?) AS lessons,
              (SELECT COUNT(DISTINCT class_lesson_id) FROM lesson_outcomes
                 WHERE user_id = ? AND class_id = ? AND status != 'archived') AS outcomes,
              (SELECT COUNT(*) FROM materials WHERE user_id = ? AND class_id = ?) AS materials,
              (SELECT COUNT(*) FROM class_lessons WHERE user_id = ? AND class_id = ?
                 AND lifecycle_state = 'generated') AS generated,
              (SELECT COUNT(*) FROM class_lessons WHERE user_id = ? AND class_id = ?
                 AND lifecycle_state = 'planned') AS planned,
              (SELECT COUNT(*) FROM class_lessons WHERE user_id = ? AND class_id = ?
                 AND lifecycle_state = 'taught') AS taught,
              (SELECT COUNT(*) FROM class_lessons WHERE user_id = ? AND class_id = ?
                 AND lifecycle_state = 'cancelled') AS cancelled
            """,
            (
                user_id, class_id, user_id, class_id, user_id, class_id,
                user_id, class_id, user_id, class_id, user_id, class_id,
                user_id, class_id,
            ),
        ).fetchone()
        return {
            "class": dict(class_row),
            "next_planned_lesson": dict(planned) if planned is not None else None,
            "last_outcome": last_outcome_value,
            "unresolved_difficulty": difficulty,
            "due_review_count": action_counts.get("review_due", 0),
            "pending_analysis_count": action_counts.get("analysis_approval", 0),
            "history_counts": dict(history) if history is not None else {},
            "outcome_recording_rate_percent": (
                int(round((int(history["outcomes"]) / int(history["taught"])) * 100))
                if history is not None and int(history["taught"]) else 0
            ),
            "no_history": not history or not any(int(history[key]) for key in history.keys()),
        }


def today_queue(
    *, telegram_user_id: int, limit: int = 20, database_path: Path | None = None
) -> list[dict[str, Any]]:
    """Build the five-kind Today queue from durable owner-scoped state."""
    _require_classes()
    if limit < 1 or limit > 50:
        raise ValueError("Today queue limit must be between 1 and 50.")
    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?",
            (_positive(telegram_user_id, "Telegram user ID"),),
        ).fetchone()
        if user is None:
            return []
        user_id = int(user["id"])
        items: list[dict[str, Any]] = []
        draft = connection.execute(
            "SELECT id, step FROM class_setup_drafts WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if draft is not None:
            items.append(
                {
                    "kind": "unfinished_setup",
                    "priority": 0,
                    "class_id": None,
                    "display_name": "Unfinished class setup",
                    "revision": 0,
                    "object_id": int(draft["id"]),
                    "detail": str(draft["step"]),
                }
            )
        missing = connection.execute(
            """
            SELECT l.id, l.class_id, l.title, c.display_name, c.revision
            FROM class_lessons AS l
            JOIN classes AS c ON c.id = l.class_id AND c.user_id = l.user_id
            WHERE l.user_id = ? AND c.status = 'active' AND l.lifecycle_state = 'taught'
              AND NOT EXISTS (
                SELECT 1 FROM lesson_outcomes AS o
                WHERE o.class_lesson_id = l.id AND o.user_id = l.user_id
                  AND o.status != 'archived'
              )
              AND NOT EXISTS (
                SELECT 1 FROM lesson_outcome_reminders AS r
                WHERE r.class_lesson_id = l.id AND r.user_id = l.user_id
                  AND r.status = 'pending'
                  AND r.next_prompt_at_utc > strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
              )
            ORDER BY COALESCE(l.taught_at, l.updated_at) DESC, l.id DESC
            """,
            (user_id,),
        ).fetchall()
        for row in missing:
            items.append(
                {
                    "kind": "missing_outcome",
                    "priority": 1,
                    "class_id": int(row["class_id"]),
                    "display_name": str(row["display_name"]),
                    "revision": int(row["revision"]),
                    "object_id": int(row["id"]),
                    "detail": str(row["title"]),
                }
            )
        action_rows = connection.execute(
            """
            SELECT i.id, i.item_type, i.due_at, i.class_id,
                   c.display_name, c.revision
            FROM class_action_items AS i
            JOIN classes AS c ON c.id = i.class_id AND c.user_id = i.user_id
            WHERE i.user_id = ? AND i.status = 'pending' AND c.status = 'active'
              AND (i.item_type != 'review_due' OR i.due_at IS NULL
                   OR i.due_at <= strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            ORDER BY i.due_at IS NULL, i.due_at, i.id
            """,
            (user_id,),
        ).fetchall()
        for row in action_rows:
            kind = "pending_analysis" if row["item_type"] == "analysis_approval" else "review_due"
            items.append(
                {
                    "kind": kind,
                    "priority": 2 if kind == "pending_analysis" else 4,
                    "class_id": int(row["class_id"]),
                    "display_name": str(row["display_name"]),
                    "revision": int(row["revision"]),
                    "object_id": int(row["id"]),
                    "detail": str(row["due_at"] or "Ready now"),
                }
            )
        planned = connection.execute(
            """
            SELECT l.id, l.class_id, l.title, l.scheduled_for,
                   c.display_name, c.revision
            FROM class_lessons AS l
            JOIN classes AS c ON c.id = l.class_id AND c.user_id = l.user_id
            WHERE l.user_id = ? AND c.status = 'active' AND l.lifecycle_state = 'planned'
            ORDER BY l.scheduled_for IS NULL, l.scheduled_for, l.id
            """,
            (user_id,),
        ).fetchall()
        for row in planned:
            items.append(
                {
                    "kind": "planned_lesson",
                    "priority": 3,
                    "class_id": int(row["class_id"]),
                    "display_name": str(row["display_name"]),
                    "revision": int(row["revision"]),
                    "object_id": int(row["id"]),
                    "detail": str(row["title"]),
                }
            )
        items.sort(key=lambda item: (int(item["priority"]), int(item["object_id"])))
        return items[:limit]
