from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from database import database_connection
from config import get_usage_timezone


DATE_CHOICES = {"today", "tomorrow", "next_class", "later"}


def _event_uuid(prefix: str) -> str:
    return f"{prefix}:{secrets.token_hex(12)}"


def _scheduled_date(choice: str, cadence: object, *, today: date | None = None) -> str | None:
    if choice not in DATE_CHOICES:
        raise ValueError("Unknown lesson date choice.")
    base = today or datetime.now(get_usage_timezone()).date()
    if choice == "today":
        return base.isoformat()
    if choice == "tomorrow":
        return (base + timedelta(days=1)).isoformat()
    if choice == "later":
        return None
    gap = {
        "three_plus_weekly": 2,
        "twice_weekly": 3,
        "weekly": 7,
        "ad_hoc": 7,
    }.get(str(cadence or ""), 7)
    return (base + timedelta(days=gap)).isoformat()


def _owned_lesson(connection: Any, telegram_user_id: int, lesson_id: int) -> Any:
    return connection.execute(
        """
        SELECT l.*, c.display_name, c.revision AS class_revision, c.status AS class_status
        FROM class_lessons AS l
        JOIN users AS u ON u.id = l.user_id
        JOIN classes AS c ON c.id = l.class_id AND c.user_id = l.user_id
        WHERE u.telegram_user_id = ? AND l.id = ?
        """,
        (telegram_user_id, lesson_id),
    ).fetchone()


def get_owned_class_lesson(
    *, telegram_user_id: int, lesson_id: int, database_path: Path | None = None
) -> dict[str, Any] | None:
    if telegram_user_id < 1 or lesson_id < 1:
        return None
    with database_connection(database_path) as connection:
        row = _owned_lesson(connection, telegram_user_id, lesson_id)
        return dict(row) if row is not None else None


def list_lesson_history(
    *, telegram_user_id: int, class_id: int, limit: int = 30,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return one class's lifecycle records in true oldest-to-newest order."""
    if telegram_user_id < 1 or class_id < 1 or limit < 1 or limit > 100:
        raise ValueError("Invalid lesson-history request.")
    with database_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT l.id, l.material_id, l.title, l.lifecycle_state,
                   l.scheduled_for, l.taught_at, l.cancelled_at,
                   l.created_at, l.updated_at, l.lifecycle_version
            FROM class_lessons AS l
            JOIN users AS u ON u.id = l.user_id
            JOIN classes AS c ON c.id = l.class_id AND c.user_id = l.user_id
            WHERE u.telegram_user_id = ? AND c.id = ?
            ORDER BY l.created_at, l.id
            LIMIT ?
            """,
            (telegram_user_id, class_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def schedule_material_lesson(
    *, telegram_user_id: int, material_id: int, date_choice: str,
    replace: bool = False, database_path: Path | None = None,
) -> dict[str, Any]:
    """Transition one generated lesson to planned, or report the current-plan conflict."""
    with database_connection(database_path) as connection:
        material = connection.execute(
            """
            SELECT m.id, m.user_id, m.class_id, m.title, c.cadence
            FROM materials AS m
            JOIN users AS u ON u.id = m.user_id
            JOIN classes AS c ON c.id = m.class_id AND c.user_id = m.user_id
            WHERE u.telegram_user_id = ? AND m.id = ?
              AND m.material_type = 'lesson' AND c.status = 'active'
            """,
            (telegram_user_id, material_id),
        ).fetchone()
        if material is None:
            return {"status": "unavailable", "lesson": None, "conflict": None}
        scheduled_for = _scheduled_date(date_choice, material["cadence"])
        lesson = connection.execute(
            "SELECT * FROM class_lessons WHERE origin_key = ? OR "
            "(origin_key IS NULL AND user_id = ? AND material_id = ?) "
            "ORDER BY id LIMIT 1",
            (f"material:{material_id}", material["user_id"], material_id),
        ).fetchone()
        if lesson is None:
            cursor = connection.execute(
                """
                INSERT INTO class_lessons (
                    class_id, user_id, material_id, title, status,
                    lifecycle_state, origin_key
                ) VALUES (?, ?, ?, ?, 'draft', 'generated', ?)
                """,
                (
                    material["class_id"], material["user_id"], material_id,
                    material["title"], f"material:{material_id}",
                ),
            )
            lesson_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO class_lesson_transitions (
                    event_uuid, class_lesson_id, class_id, user_id,
                    from_state, to_state, reason
                ) VALUES (?, ?, ?, ?, NULL, 'generated', 'legacy_material_linked')
                """,
                (
                    _event_uuid("lesson-generated"), lesson_id,
                    material["class_id"], material["user_id"],
                ),
            )
            lesson = connection.execute(
                "SELECT * FROM class_lessons WHERE id = ?", (lesson_id,)
            ).fetchone()
        state = str(lesson["lifecycle_state"])
        if state == "planned":
            if lesson["scheduled_for"] != scheduled_for:
                connection.execute(
                    "UPDATE class_lessons SET scheduled_for = ?, updated_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
                    (scheduled_for, lesson["id"]),
                )
            current = connection.execute(
                "SELECT * FROM class_lessons WHERE id = ?", (lesson["id"],)
            ).fetchone()
            return {"status": "already_planned", "lesson": dict(current), "conflict": None}
        if state != "generated":
            return {"status": "unavailable", "lesson": dict(lesson), "conflict": None}

        conflict = connection.execute(
            """
            SELECT * FROM class_lessons
            WHERE user_id = ? AND class_id = ? AND lifecycle_state = 'planned'
              AND id != ? ORDER BY scheduled_for IS NULL, scheduled_for, id LIMIT 1
            """,
            (material["user_id"], material["class_id"], lesson["id"]),
        ).fetchone()
        if conflict is not None and not replace:
            return {"status": "conflict", "lesson": dict(lesson), "conflict": dict(conflict)}
        if conflict is not None:
            now = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
            connection.execute(
                f"""
                UPDATE class_lessons
                SET lifecycle_state = 'cancelled', status = 'cancelled',
                    cancelled_at = {now}, updated_at = {now},
                    lifecycle_version = lifecycle_version + 1
                WHERE id = ? AND lifecycle_state = 'planned'
                """,
                (conflict["id"],),
            )
            connection.execute(
                """
                INSERT INTO class_lesson_transitions (
                    event_uuid, class_lesson_id, class_id, user_id,
                    from_state, to_state, reason, scheduled_for_snapshot
                ) VALUES (?, ?, ?, ?, 'planned', 'cancelled',
                          'replaced_by_new_plan', ?)
                """,
                (
                    _event_uuid("lesson-replaced"), conflict["id"],
                    material["class_id"], material["user_id"], conflict["scheduled_for"],
                ),
            )

        cursor = connection.execute(
            """
            UPDATE class_lessons
            SET lifecycle_state = 'planned', status = 'planned', scheduled_for = ?,
                cancelled_at = NULL, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                lifecycle_version = lifecycle_version + 1
            WHERE id = ? AND lifecycle_state = 'generated'
            """,
            (scheduled_for, lesson["id"]),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Lesson plan transition was not applied.")
        connection.execute(
            """
            INSERT INTO class_lesson_transitions (
                event_uuid, class_lesson_id, class_id, user_id,
                from_state, to_state, reason, scheduled_for_snapshot
            ) VALUES (?, ?, ?, ?, 'generated', 'planned', 'teacher_selected', ?)
            """,
            (
                _event_uuid("lesson-planned"), lesson["id"], material["class_id"],
                material["user_id"], scheduled_for,
            ),
        )
        connection.execute(
            "UPDATE classes SET last_active_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
            "WHERE id = ? AND user_id = ?",
            (material["class_id"], material["user_id"]),
        )
        current = connection.execute(
            "SELECT * FROM class_lessons WHERE id = ?", (lesson["id"],)
        ).fetchone()
        return {
            "status": "replaced" if conflict is not None else "planned",
            "lesson": dict(current),
            "conflict": dict(conflict) if conflict is not None else None,
        }


def mark_lesson_taught(
    *, telegram_user_id: int, lesson_id: int, database_path: Path | None = None
) -> tuple[dict[str, Any] | None, bool]:
    """Idempotently transition one owned planned lesson to taught."""
    with database_connection(database_path) as connection:
        lesson = _owned_lesson(connection, telegram_user_id, lesson_id)
        if lesson is None:
            return None, False
        state = str(lesson["lifecycle_state"])
        if state == "taught":
            return dict(lesson), False
        if state != "planned" or lesson["class_status"] != "active":
            return dict(lesson), False
        now = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
        cursor = connection.execute(
            f"""
            UPDATE class_lessons
            SET lifecycle_state = 'taught', status = 'taught', taught_at = {now},
                updated_at = {now}, lifecycle_version = lifecycle_version + 1
            WHERE id = ? AND lifecycle_state = 'planned'
            """,
            (lesson_id,),
        )
        if cursor.rowcount != 1:
            current = _owned_lesson(connection, telegram_user_id, lesson_id)
            return (dict(current) if current is not None else None), False
        connection.execute(
            """
            INSERT INTO class_lesson_transitions (
                event_uuid, class_lesson_id, class_id, user_id,
                from_state, to_state, reason, scheduled_for_snapshot
            ) VALUES (?, ?, ?, ?, 'planned', 'taught', 'teacher_confirmed', ?)
            """,
            (
                _event_uuid("lesson-taught"), lesson_id, lesson["class_id"],
                lesson["user_id"], lesson["scheduled_for"],
            ),
        )
        current = _owned_lesson(connection, telegram_user_id, lesson_id)
        return (dict(current) if current is not None else None), True


def cancel_planned_lesson(
    *, telegram_user_id: int, lesson_id: int, database_path: Path | None = None
) -> tuple[dict[str, Any] | None, bool]:
    """Idempotently cancel one plan while preserving its linked material."""
    with database_connection(database_path) as connection:
        lesson = _owned_lesson(connection, telegram_user_id, lesson_id)
        if lesson is None:
            return None, False
        state = str(lesson["lifecycle_state"])
        if state == "cancelled":
            return dict(lesson), False
        if state != "planned" or lesson["class_status"] != "active":
            return dict(lesson), False
        now = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
        cursor = connection.execute(
            f"""
            UPDATE class_lessons
            SET lifecycle_state = 'cancelled', status = 'cancelled',
                cancelled_at = {now}, updated_at = {now},
                lifecycle_version = lifecycle_version + 1
            WHERE id = ? AND lifecycle_state = 'planned'
            """,
            (lesson_id,),
        )
        if cursor.rowcount != 1:
            current = _owned_lesson(connection, telegram_user_id, lesson_id)
            return (dict(current) if current is not None else None), False
        connection.execute(
            """
            INSERT INTO class_lesson_transitions (
                event_uuid, class_lesson_id, class_id, user_id,
                from_state, to_state, reason, scheduled_for_snapshot
            ) VALUES (?, ?, ?, ?, 'planned', 'cancelled', 'teacher_cancelled', ?)
            """,
            (
                _event_uuid("lesson-cancelled"), lesson_id, lesson["class_id"],
                lesson["user_id"], lesson["scheduled_for"],
            ),
        )
        current = _owned_lesson(connection, telegram_user_id, lesson_id)
        return (dict(current) if current is not None else None), True


def lesson_conversion_metrics(
    *, telegram_user_id: int, class_id: int | None = None,
    database_path: Path | None = None,
) -> dict[str, int]:
    """Count recorded lifecycle conversions without inferring teaching or mastery."""
    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (telegram_user_id,)
        ).fetchone()
        if user is None:
            return {"generated_to_planned": 0, "planned_to_taught": 0}
        where = "user_id = ?"
        parameters: list[Any] = [int(user["id"])]
        if class_id is not None:
            where += " AND class_id = ?"
            parameters.append(class_id)
        rows = connection.execute(
            f"""
            SELECT from_state, to_state, COUNT(*) AS total
            FROM class_lesson_transitions WHERE {where}
              AND ((from_state = 'generated' AND to_state = 'planned')
                OR (from_state = 'planned' AND to_state = 'taught'))
            GROUP BY from_state, to_state
            """,
            parameters,
        ).fetchall()
        values = {(str(row["from_state"]), str(row["to_state"])): int(row["total"]) for row in rows}
        return {
            "generated_to_planned": values.get(("generated", "planned"), 0),
            "planned_to_taught": values.get(("planned", "taught"), 0),
        }
