from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from class_service import ClassFeatureDisabledError
from database import database_connection, ensure_database_user
from feature_flags import feature_enabled
from subscription_service import class_creation_access_for_user


SETUP_STEPS = (
    "name",
    "level",
    "age",
    "size",
    "duration",
    "goal",
    "weak",
    "book",
    "equipment",
    "preference",
    "review",
)
REQUIRED_FIELDS = (
    "display_name",
    "level_choice",
    "age_group_choice",
    "learner_count_band_choice",
    "duration_choice",
    "goal_choice",
    "weak_areas",
    "coursebook_state",
    "equipment",
    "teaching_preferences",
)


class ClassLimitReachedError(RuntimeError):
    def __init__(self, access: dict[str, Any]) -> None:
        super().__init__("The active class limit has been reached.")
        self.access = access


def _require_classes() -> None:
    if not feature_enabled("classes"):
        raise ClassFeatureDisabledError("Class setup is not enabled.")


def _draft_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    try:
        payload = json.loads(str(row["payload_json"] or "{}"))
    except json.JSONDecodeError:
        payload = {}
    return {
        "id": int(row["id"]),
        "step": str(row["step"]),
        "payload": payload if isinstance(payload, dict) else {},
        "idempotency_key": str(row["idempotency_key"]),
        "revision": int(row["revision"]),
        "started_at": str(row["started_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _owned_draft(connection: Any, telegram_user_id: int) -> Any:
    return connection.execute(
        """
        SELECT d.* FROM class_setup_drafts AS d
        JOIN users AS u ON u.id = d.user_id
        WHERE u.telegram_user_id = ?
        """,
        (telegram_user_id,),
    ).fetchone()


def get_setup_draft(
    *, telegram_user_id: int, database_path: Path | None = None
) -> dict[str, Any] | None:
    _require_classes()
    with database_connection(database_path) as connection:
        return _draft_dict(_owned_draft(connection, telegram_user_id))


def start_setup_draft(
    *,
    telegram_user: Any,
    template: dict[str, Any] | None = None,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Start one durable draft; callers must confirm before replacing an existing one."""
    _require_classes()
    payload: dict[str, Any] = {
        "weak_areas": [],
        "equipment": [],
        "teaching_preferences": [],
    }
    if template:
        payload.update(
            {
                "level_choice": template.get("level") or "not_sure",
                "age_group_choice": template.get("age_group") or "not_sure",
                "learner_count_band_choice": template.get("learner_count_band") or "not_sure",
                "duration_choice": template.get("lesson_duration_minutes") or "not_sure",
                "goal_choice": template.get("goal") or "general_english",
                "coursebook": template.get("coursebook"),
                "coursebook_unit": template.get("coursebook_unit"),
                "coursebook_state": "provided" if template.get("coursebook") else "skipped",
                "weak_areas": _json_list(template.get("weak_areas_json")) or ["ns"],
                "equipment": _json_list(template.get("equipment_json")) or ["ns"],
                "teaching_preferences": _json_list(
                    template.get("teaching_preferences_json")
                ) or ["ns"],
                "template_used": True,
            }
        )
    key = str(uuid.uuid4())
    with database_connection(database_path) as connection:
        user_id = ensure_database_user(connection, telegram_user)
        existing = _owned_draft(connection, int(telegram_user.id))
        if existing is not None:
            result = _draft_dict(existing)
            if result is None:
                raise RuntimeError("TeacherOS could not load the class draft.")
            return result
        connection.execute(
            """
            INSERT INTO class_setup_drafts (
                user_id, idempotency_key, step, payload_json
            ) VALUES (?, ?, 'name', ?)
            """,
            (user_id, key, json.dumps(payload, sort_keys=True)),
        )
        _insert_setup_event(
            connection,
            event_uuid=f"setup-started-{key}",
            user_id=user_id,
            event_name="class_setup_started",
            properties={"template_used": bool(template)},
        )
        result = _draft_dict(_owned_draft(connection, int(telegram_user.id)))
        if result is None:
            raise RuntimeError("TeacherOS could not start the class draft.")
        return result


def save_setup_draft(
    *,
    telegram_user_id: int,
    expected_revision: int,
    step: str,
    payload: dict[str, Any],
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    _require_classes()
    if step not in SETUP_STEPS:
        raise ValueError("Unknown class setup step.")
    with database_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE class_setup_drafts
            SET step = ?, payload_json = ?, revision = revision + 1,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE user_id = (SELECT id FROM users WHERE telegram_user_id = ?)
              AND revision = ?
            """,
            (
                step,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                telegram_user_id,
                expected_revision,
            ),
        )
        if cursor.rowcount != 1:
            return None
        return _draft_dict(_owned_draft(connection, telegram_user_id))


def discard_setup_draft(
    *, telegram_user_id: int, database_path: Path | None = None
) -> bool:
    _require_classes()
    with database_connection(database_path) as connection:
        row = _owned_draft(connection, telegram_user_id)
        if row is None:
            return False
        user_id = int(row["user_id"])
        key = str(row["idempotency_key"])
        step = str(row["step"])
        connection.execute("DELETE FROM class_setup_drafts WHERE id = ?", (row["id"],))
        _insert_setup_event(
            connection,
            event_uuid=f"setup-abandoned-{key}",
            user_id=user_id,
            event_name="class_setup_abandoned",
            properties={
                "abandoned_at_field": step,
                "setup_seconds": _elapsed_seconds(str(row["started_at"])),
            },
        )
        return True


def complete_setup(
    *,
    telegram_user_id: int,
    draft_id: int,
    database_path: Path | None = None,
) -> tuple[dict[str, Any], bool]:
    """Create exactly one class for a complete draft and return (class, created)."""
    _require_classes()
    with database_connection(database_path) as connection:
        already_created = connection.execute(
            """
            SELECT c.* FROM classes AS c
            JOIN users AS u ON u.id = c.user_id
            WHERE c.setup_draft_id = ? AND u.telegram_user_id = ?
            """,
            (draft_id, telegram_user_id),
        ).fetchone()
        if already_created is not None:
            return dict(already_created), False
        access = class_creation_access_for_user(telegram_user_id)
        if not access["allowed"]:
            raise ClassLimitReachedError(access)
        row = _owned_draft(connection, telegram_user_id)
        if row is None or int(row["id"]) != draft_id:
            raise ValueError("No resumable class setup draft was found.")
        draft = _draft_dict(row)
        if draft is None:
            raise ValueError("The class setup draft could not be read.")
        payload = draft["payload"]
        missing = [field for field in REQUIRED_FIELDS if field not in payload]
        if not payload.get("display_name"):
            missing.append("display_name")
        for field in ("weak_areas", "equipment", "teaching_preferences"):
            if not payload.get(field):
                missing.append(field)
        if payload.get("coursebook_state") not in {"provided", "skipped"}:
            missing.append("coursebook_state")
        if missing:
            raise ValueError("The class setup draft is incomplete.")
        key = draft["idempotency_key"]
        existing = connection.execute(
            """
            SELECT c.* FROM classes AS c
            JOIN users AS u ON u.id = c.user_id
            WHERE c.setup_idempotency_key = ? AND u.telegram_user_id = ?
            """,
            (key, telegram_user_id),
        ).fetchone()
        if existing is not None:
            return dict(existing), False

        level_choice = payload["level_choice"]
        age_choice = payload["age_group_choice"]
        size_choice = payload["learner_count_band_choice"]
        duration_choice = payload["duration_choice"]
        user_id = int(row["user_id"])
        try:
            cursor = connection.execute(
                """
                INSERT INTO classes (
                    user_id, display_name, level, age_group, learner_count_band,
                    goal, lesson_duration_minutes, weak_areas_json, coursebook,
                    coursebook_unit, equipment_json, teaching_preferences_json,
                    setup_profile_json, setup_idempotency_key, setup_draft_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    payload["display_name"],
                    None if level_choice == "not_sure" else level_choice,
                    None if age_choice == "not_sure" else age_choice,
                    None if size_choice == "not_sure" else size_choice,
                    payload["goal_choice"],
                    None if duration_choice == "not_sure" else int(duration_choice),
                    json.dumps(payload["weak_areas"], sort_keys=True),
                    payload.get("coursebook"),
                    payload.get("coursebook_unit"),
                    json.dumps(payload["equipment"], sort_keys=True),
                    json.dumps(payload["teaching_preferences"], sort_keys=True),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    key,
                    draft_id,
                ),
            )
        except sqlite3.IntegrityError:
            existing = connection.execute(
                "SELECT * FROM classes WHERE setup_idempotency_key = ? AND user_id = ?",
                (key, user_id),
            ).fetchone()
            if existing is None:
                raise
            return dict(existing), False
        class_id = int(cursor.lastrowid)
        connection.execute("DELETE FROM class_setup_drafts WHERE id = ?", (row["id"],))
        _insert_setup_event(
            connection,
            event_uuid=f"setup-completed-{key}",
            user_id=user_id,
            event_name="class_setup_completed",
            class_id=class_id,
            properties={
                "template_used": bool(payload.get("template_used")),
                "setup_seconds": _elapsed_seconds(str(row["started_at"])),
            },
        )
        created = connection.execute(
            "SELECT * FROM classes WHERE id = ? AND user_id = ?",
            (class_id, user_id),
        ).fetchone()
        if created is None:
            raise RuntimeError("TeacherOS could not load the completed class.")
        return dict(created), True


def _json_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _elapsed_seconds(started_at: str) -> int:
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - started).total_seconds()))


def _insert_setup_event(
    connection: Any,
    *,
    event_uuid: str,
    user_id: int,
    event_name: str,
    properties: dict[str, Any],
    class_id: int | None = None,
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO product_events (
            event_uuid, user_id, class_id, event_name, privacy_class,
            properties_json, delivery_status, occurred_at
        ) VALUES (?, ?, ?, ?, 'product', ?, 'pending',
                  strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        """,
        (event_uuid, user_id, class_id, event_name, json.dumps(properties, sort_keys=True)),
    )
