from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from database import database_connection, ensure_database_user
from feature_flags import feature_enabled


class ClassFeatureDisabledError(RuntimeError):
    """Raised when a class-memory API is called while its rollout flag is off."""


_CLASS_FIELDS = (
    "id",
    "display_name",
    "level",
    "age_group",
    "learner_count_band",
    "cadence",
    "goal",
    "status",
    "revision",
    "created_at",
    "updated_at",
    "archived_at",
    "lesson_duration_minutes",
    "weak_areas_json",
    "coursebook",
    "coursebook_unit",
    "equipment_json",
    "teaching_preferences_json",
    "setup_profile_json",
    "last_active_at",
)
_EDITABLE_CLASS_FIELDS = {
    "display_name",
    "level",
    "age_group",
    "learner_count_band",
    "cadence",
    "goal",
}
_CLASS_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}
_AGE_GROUPS = {"young_learners", "teens", "adults", "mixed"}
_LEARNER_COUNT_BANDS = {"one_to_one", "2_5", "6_12", "13_20", "21_plus"}
_CADENCES = {"ad_hoc", "weekly", "twice_weekly", "three_plus_weekly"}
_OBJECTIVE_STATUSES = {"current", "met", "paused", "archived"}
_LESSON_STATUSES = {"draft", "planned", "taught", "cancelled", "archived"}
_OUTCOME_RESULTS = {"not_assessed", "not_met", "partly_met", "met", "exceeded"}
_OUTCOME_CONFIDENCE = {"low", "medium", "high"}
_SUPPORT_LEVELS = {"none", "some", "substantial"}
_OUTCOME_STATUSES = {"draft", "saved", "approved", "archived"}
_PRIVACY_CLASSES = {"operational", "product", "support", "sensitive"}
_DELIVERY_STATUSES = {"pending", "delivered", "failed"}


def _require_classes() -> None:
    if not feature_enabled("classes"):
        raise ClassFeatureDisabledError("Class memory is not enabled.")


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{label} must be a positive integer.")
    return value


def _required_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} cannot be empty.")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValueError(f"{label} cannot exceed {maximum} characters.")
    return normalized


def _optional_text(value: object, label: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text or null.")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise ValueError(f"{label} cannot exceed {maximum} characters.")
    return normalized


def _enum(value: object, label: str, allowed: set[str], *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    normalized = _required_text(value, label, 100)
    if normalized not in allowed:
        raise ValueError(f"Unsupported {label}.")
    return normalized


def _row_dict(row: Any, fields: tuple[str, ...] | None = None) -> dict[str, Any] | None:
    if row is None:
        return None
    if fields is None:
        return {key: row[key] for key in row.keys()}
    return {field: row[field] for field in fields}


def _owned_user_id(connection: Any, telegram_user_id: int) -> int | None:
    row = connection.execute(
        "SELECT id FROM users WHERE telegram_user_id = ?",
        (_positive_int(telegram_user_id, "Telegram user ID"),),
    ).fetchone()
    return int(row["id"]) if row is not None else None


def _owned_class_row(connection: Any, telegram_user_id: int, class_id: int) -> Any:
    return connection.execute(
        """
        SELECT c.*
        FROM classes AS c
        JOIN users AS u ON u.id = c.user_id
        WHERE c.id = ? AND u.telegram_user_id = ?
        """,
        (
            _positive_int(class_id, "Class ID"),
            _positive_int(telegram_user_id, "Telegram user ID"),
        ),
    ).fetchone()


def create_class(
    *,
    telegram_user: Any,
    display_name: str,
    level: str | None = None,
    age_group: str | None = None,
    learner_count_band: str | None = None,
    cadence: str | None = None,
    goal: str | None = None,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Create a class for the authenticated Telegram user."""
    _require_classes()
    values = (
        _required_text(display_name, "Class name", 120),
        _enum(level, "level", _CLASS_LEVELS, optional=True),
        _enum(age_group, "age group", _AGE_GROUPS, optional=True),
        _enum(
            learner_count_band,
            "learner count band",
            _LEARNER_COUNT_BANDS,
            optional=True,
        ),
        _enum(cadence, "cadence", _CADENCES, optional=True),
        _optional_text(goal, "Class goal", 2000),
    )
    with database_connection(database_path) as connection:
        user_id = ensure_database_user(connection, telegram_user)
        cursor = connection.execute(
            """
            INSERT INTO classes (
                user_id, display_name, level, age_group,
                learner_count_band, cadence, goal
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, *values),
        )
        row = _owned_class_row(connection, int(telegram_user.id), int(cursor.lastrowid))
        result = _row_dict(row, _CLASS_FIELDS)
        if result is None:
            raise RuntimeError("TeacherOS could not create the class.")
        return result


def list_classes(
    *,
    telegram_user_id: int,
    include_archived: bool = False,
    status: str | None = None,
    limit: int = 50,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List only classes owned by the requesting user."""
    _require_classes()
    if limit < 1 or limit > 100:
        raise ValueError("Class list size must be between 1 and 100.")
    if status is not None and status not in {"active", "archived"}:
        raise ValueError("Unsupported class status filter.")
    if status is not None:
        status_clause = "AND c.status = ?"
    else:
        status_clause = "" if include_archived else "AND c.status = 'active'"
    parameters: list[Any] = [_positive_int(telegram_user_id, "Telegram user ID")]
    if status is not None:
        parameters.append(status)
    parameters.append(limit)
    with database_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT c.*
            FROM classes AS c
            JOIN users AS u ON u.id = c.user_id
            WHERE u.telegram_user_id = ? {status_clause}
            ORDER BY c.updated_at DESC, c.id DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [_row_dict(row, _CLASS_FIELDS) or {} for row in rows]


def count_classes(
    *,
    telegram_user_id: int,
    status: str = "active",
    database_path: Path | None = None,
) -> int:
    """Count owned classes for central entitlement decisions."""
    _require_classes()
    if status not in {"active", "archived"}:
        raise ValueError("Unsupported class status filter.")
    with database_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM classes AS c
            JOIN users AS u ON u.id = c.user_id
            WHERE u.telegram_user_id = ? AND c.status = ?
            """,
            (_positive_int(telegram_user_id, "Telegram user ID"), status),
        ).fetchone()
        return int(row[0]) if row is not None else 0


def get_class(
    *,
    telegram_user_id: int,
    class_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Return an owned class; missing and unauthorized IDs are indistinguishable."""
    _require_classes()
    with database_connection(database_path) as connection:
        return _row_dict(
            _owned_class_row(connection, telegram_user_id, class_id),
            _CLASS_FIELDS,
        )


def update_class(
    *,
    telegram_user_id: int,
    class_id: int,
    changes: Mapping[str, Any],
    expected_revision: int | None = None,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Update an owned class, optionally using optimistic concurrency."""
    _require_classes()
    unknown = set(changes) - _EDITABLE_CLASS_FIELDS
    if unknown:
        raise ValueError("Unsupported class field update.")
    if not changes:
        return get_class(
            telegram_user_id=telegram_user_id,
            class_id=class_id,
            database_path=database_path,
        )

    normalized: dict[str, Any] = {}
    for field, value in changes.items():
        if field == "display_name":
            normalized[field] = _required_text(value, "Class name", 120)
        elif field == "level":
            normalized[field] = _enum(value, "level", _CLASS_LEVELS, optional=True)
        elif field == "age_group":
            normalized[field] = _enum(value, "age group", _AGE_GROUPS, optional=True)
        elif field == "learner_count_band":
            normalized[field] = _enum(
                value, "learner count band", _LEARNER_COUNT_BANDS, optional=True
            )
        elif field == "cadence":
            normalized[field] = _enum(value, "cadence", _CADENCES, optional=True)
        elif field == "goal":
            normalized[field] = _optional_text(value, "Class goal", 2000)

    assignments = [f"{field} = ?" for field in normalized]
    assignments.extend(
        [
            "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
            "revision = revision + 1",
        ]
    )
    parameters: list[Any] = list(normalized.values())
    parameters.extend(
        [
            _positive_int(class_id, "Class ID"),
            _positive_int(telegram_user_id, "Telegram user ID"),
        ]
    )
    revision_clause = ""
    if expected_revision is not None:
        parameters.append(_positive_int(expected_revision, "Expected revision"))
        revision_clause = "AND revision = ?"

    with database_connection(database_path) as connection:
        cursor = connection.execute(
            f"""
            UPDATE classes
            SET {', '.join(assignments)}
            WHERE id = ?
              AND user_id = (
                  SELECT id FROM users WHERE telegram_user_id = ?
              )
              {revision_clause}
            """,
            parameters,
        )
        if cursor.rowcount != 1:
            return None
        return _row_dict(
            _owned_class_row(connection, telegram_user_id, class_id),
            _CLASS_FIELDS,
        )


def archive_class(
    *,
    telegram_user_id: int,
    class_id: int,
    database_path: Path | None = None,
) -> bool:
    """Archive an owned class; unauthorized and missing IDs both return False."""
    _require_classes()
    with database_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE classes
            SET status = 'archived',
                archived_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                revision = revision + 1
            WHERE id = ?
              AND status = 'active'
              AND user_id = (
                  SELECT id FROM users WHERE telegram_user_id = ?
              )
            """,
            (
                _positive_int(class_id, "Class ID"),
                _positive_int(telegram_user_id, "Telegram user ID"),
            ),
        )
        return cursor.rowcount == 1


def link_material_to_class(
    *,
    telegram_user_id: int,
    material_id: int,
    class_id: int,
    database_path: Path | None = None,
) -> bool:
    """Link only a requesting user's material to that same user's active class."""
    _require_classes()
    with database_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE materials
            SET class_id = ?
            WHERE id = ?
              AND user_id = (
                  SELECT id FROM users WHERE telegram_user_id = ?
              )
              AND EXISTS (
                  SELECT 1 FROM classes AS c
                  WHERE c.id = ?
                    AND c.user_id = materials.user_id
                    AND c.status = 'active'
              )
            """,
            (
                _positive_int(class_id, "Class ID"),
                _positive_int(material_id, "Material ID"),
                _positive_int(telegram_user_id, "Telegram user ID"),
                class_id,
            ),
        )
        return cursor.rowcount == 1


def unlink_material_from_class(
    *,
    telegram_user_id: int,
    material_id: int,
    database_path: Path | None = None,
) -> bool:
    _require_classes()
    with database_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE materials
            SET class_id = NULL
            WHERE id = ?
              AND class_id IS NOT NULL
              AND user_id = (
                  SELECT id FROM users WHERE telegram_user_id = ?
              )
            """,
            (
                _positive_int(material_id, "Material ID"),
                _positive_int(telegram_user_id, "Telegram user ID"),
            ),
        )
        return cursor.rowcount == 1


def add_class_objective(
    *,
    telegram_user_id: int,
    class_id: int,
    objective: str,
    priority: int = 0,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    _require_classes()
    if not isinstance(priority, int) or isinstance(priority, bool) or not 0 <= priority <= 100:
        raise ValueError("Objective priority must be between 0 and 100.")
    with database_connection(database_path) as connection:
        owner_id = _owned_user_id(connection, telegram_user_id)
        if owner_id is None:
            return None
        cursor = connection.execute(
            """
            INSERT INTO class_objectives (class_id, user_id, objective, priority)
            SELECT id, user_id, ?, ? FROM classes
            WHERE id = ? AND user_id = ? AND status = 'active'
            """,
            (
                _required_text(objective, "Objective", 1000),
                priority,
                _positive_int(class_id, "Class ID"),
                owner_id,
            ),
        )
        if cursor.rowcount != 1:
            return None
        return _row_dict(
            connection.execute(
                "SELECT * FROM class_objectives WHERE id = ? AND user_id = ?",
                (cursor.lastrowid, owner_id),
            ).fetchone()
        )


def create_class_lesson(
    *,
    telegram_user_id: int,
    class_id: int,
    title: str,
    material_id: int | None = None,
    status: str = "draft",
    scheduled_for: str | None = None,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    _require_classes()
    normalized_status = _enum(status, "lesson status", _LESSON_STATUSES)
    with database_connection(database_path) as connection:
        owner_id = _owned_user_id(connection, telegram_user_id)
        if owner_id is None:
            return None
        if material_id is not None:
            material = connection.execute(
                "SELECT 1 FROM materials WHERE id = ? AND user_id = ?",
                (_positive_int(material_id, "Material ID"), owner_id),
            ).fetchone()
            if material is None:
                return None
        cursor = connection.execute(
            """
            INSERT INTO class_lessons (
                class_id, user_id, material_id, title, status, scheduled_for
            )
            SELECT id, user_id, ?, ?, ?, ? FROM classes
            WHERE id = ? AND user_id = ? AND status = 'active'
            """,
            (
                material_id,
                _required_text(title, "Lesson title", 200),
                normalized_status,
                _optional_text(scheduled_for, "Scheduled time", 50),
                _positive_int(class_id, "Class ID"),
                owner_id,
            ),
        )
        if cursor.rowcount != 1:
            return None
        return _row_dict(
            connection.execute(
                "SELECT * FROM class_lessons WHERE id = ? AND user_id = ?",
                (cursor.lastrowid, owner_id),
            ).fetchone()
        )


def record_lesson_outcome(
    *,
    telegram_user_id: int,
    class_id: int,
    class_lesson_id: int,
    result: str,
    confidence: str | None = None,
    support_needed: str | None = None,
    notes: str | None = None,
    status: str = "saved",
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    _require_classes()
    with database_connection(database_path) as connection:
        owner_id = _owned_user_id(connection, telegram_user_id)
        if owner_id is None:
            return None
        cursor = connection.execute(
            """
            INSERT INTO lesson_outcomes (
                class_lesson_id, class_id, user_id, result,
                confidence, support_needed, notes, status
            )
            SELECT id, class_id, user_id, ?, ?, ?, ?, ?
            FROM class_lessons
            WHERE id = ? AND class_id = ? AND user_id = ?
            """,
            (
                _enum(result, "outcome result", _OUTCOME_RESULTS),
                _enum(confidence, "confidence", _OUTCOME_CONFIDENCE, optional=True),
                _enum(
                    support_needed,
                    "support needed",
                    _SUPPORT_LEVELS,
                    optional=True,
                ),
                _optional_text(notes, "Outcome notes", 4000),
                _enum(status, "outcome status", _OUTCOME_STATUSES),
                _positive_int(class_lesson_id, "Class lesson ID"),
                _positive_int(class_id, "Class ID"),
                owner_id,
            ),
        )
        if cursor.rowcount != 1:
            return None
        return _row_dict(
            connection.execute(
                "SELECT * FROM lesson_outcomes WHERE id = ? AND user_id = ?",
                (cursor.lastrowid, owner_id),
            ).fetchone()
        )


def record_product_event(
    *,
    telegram_user: Any,
    event_name: str,
    event_uuid: str | None = None,
    class_id: int | None = None,
    class_lesson_id: int | None = None,
    material_id: int | None = None,
    privacy_class: str = "operational",
    properties: Mapping[str, Any] | None = None,
    delivery_status: str = "pending",
    occurred_at: datetime | None = None,
    database_path: Path | None = None,
) -> int | None:
    """Record an idempotent, owner-scoped product event."""
    _require_classes()
    event_key = event_uuid or str(uuid.uuid4())
    _required_text(event_key, "Event UUID", 100)
    timestamp = occurred_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    occurred_text = timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    with database_connection(database_path) as connection:
        owner_id = ensure_database_user(connection, telegram_user)
        references = (
            ("classes", class_id),
            ("class_lessons", class_lesson_id),
            ("materials", material_id),
        )
        for table, reference_id in references:
            if reference_id is None:
                continue
            row = connection.execute(
                f"SELECT 1 FROM {table} WHERE id = ? AND user_id = ?",
                (_positive_int(reference_id, "Reference ID"), owner_id),
            ).fetchone()
            if row is None:
                return None
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO product_events (
                event_uuid, user_id, class_id, class_lesson_id, material_id,
                event_name, privacy_class, properties_json,
                delivery_status, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_key,
                owner_id,
                class_id,
                class_lesson_id,
                material_id,
                _required_text(event_name, "Event name", 100),
                _enum(privacy_class, "privacy class", _PRIVACY_CLASSES),
                json.dumps(dict(properties or {}), ensure_ascii=False, sort_keys=True),
                _enum(delivery_status, "delivery status", _DELIVERY_STATUSES),
                occurred_text,
            ),
        )
        if cursor.rowcount == 1:
            return int(cursor.lastrowid)
        row = connection.execute(
            "SELECT id FROM product_events WHERE event_uuid = ? AND user_id = ?",
            (event_key, owner_id),
        ).fetchone()
        return int(row["id"]) if row is not None else None
