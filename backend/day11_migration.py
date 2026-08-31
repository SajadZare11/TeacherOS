from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 11
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def apply_schema_v11(connection: sqlite3.Connection) -> None:
    """Add the durable, auditable Day 11 lesson lifecycle."""
    first_application = connection.execute(
        "SELECT 1 FROM schema_versions WHERE version = ?", (SCHEMA_VERSION,)
    ).fetchone() is None
    additions = {
        "lifecycle_state": (
            "TEXT NOT NULL DEFAULT 'generated' CHECK ("
            "lifecycle_state IN ('generated', 'planned', 'taught', 'cancelled'))"
        ),
        "lifecycle_version": "INTEGER NOT NULL DEFAULT 1 CHECK (lifecycle_version > 0)",
        "cancelled_at": "TEXT",
        "origin_key": "TEXT",
    }
    existing = _columns(connection, "class_lessons")
    for name, definition in additions.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE class_lessons ADD COLUMN {name} {definition}")

    # Preserve every historical row while translating the legacy Day 5 status.
    if first_application:
        connection.execute(
            """
            UPDATE class_lessons
            SET lifecycle_state = CASE status
                WHEN 'planned' THEN 'planned'
                WHEN 'taught' THEN 'taught'
                WHEN 'cancelled' THEN 'cancelled'
                WHEN 'archived' THEN 'cancelled'
                ELSE 'generated'
            END,
            cancelled_at = CASE
                WHEN status IN ('cancelled', 'archived') THEN COALESCE(cancelled_at, updated_at)
                ELSE cancelled_at
            END
            """
        )
        # Backfill immutable identity only where an older database has one unambiguous link.
        connection.execute(
            """
            UPDATE class_lessons
            SET origin_key = 'material:' || material_id
            WHERE material_id IS NOT NULL AND origin_key IS NULL
              AND material_id IN (
                  SELECT material_id FROM class_lessons
                  WHERE material_id IS NOT NULL
                  GROUP BY material_id HAVING COUNT(*) = 1
              )
            """
        )

    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS class_lesson_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_uuid TEXT NOT NULL UNIQUE CHECK (length(trim(event_uuid)) BETWEEN 8 AND 100),
            class_lesson_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            from_state TEXT CHECK (
                from_state IS NULL OR
                from_state IN ('generated', 'planned', 'taught', 'cancelled')
            ),
            to_state TEXT NOT NULL CHECK (
                to_state IN ('generated', 'planned', 'taught', 'cancelled')
            ),
            reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 100),
            scheduled_for_snapshot TEXT,
            occurred_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (class_lesson_id, class_id, user_id)
                REFERENCES class_lessons(id, class_id, user_id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_class_lessons_origin_key "
        "ON class_lessons(origin_key) WHERE origin_key IS NOT NULL"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_lessons_lifecycle_owner_class "
        "ON class_lessons(user_id, class_id, lifecycle_state, scheduled_for, id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_lesson_transitions_conversion "
        "ON class_lesson_transitions(user_id, class_id, from_state, to_state, occurred_at, id)"
    )

    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_lesson_material_class_insert_v11
        BEFORE INSERT ON class_lessons
        WHEN NEW.material_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM materials
            WHERE id = NEW.material_id AND user_id = NEW.user_id
              AND class_id = NEW.class_id AND material_type = 'lesson'
        )
        BEGIN SELECT RAISE(ABORT, 'lesson material ownership mismatch'); END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_lesson_legacy_status_insert_v11
        AFTER INSERT ON class_lessons
        WHEN NEW.lifecycle_state = 'generated'
          AND NEW.status IN ('planned', 'taught', 'cancelled', 'archived')
        BEGIN
            UPDATE class_lessons
            SET lifecycle_state = CASE NEW.status
                    WHEN 'planned' THEN 'planned'
                    WHEN 'taught' THEN 'taught'
                    ELSE 'cancelled'
                END,
                cancelled_at = CASE
                    WHEN NEW.status IN ('cancelled', 'archived')
                    THEN strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ELSE cancelled_at
                END
            WHERE id = NEW.id;
            INSERT OR IGNORE INTO class_lesson_transitions (
                event_uuid, class_lesson_id, class_id, user_id,
                from_state, to_state, reason, scheduled_for_snapshot
            ) VALUES (
                'legacy-insert:' || NEW.id, NEW.id, NEW.class_id, NEW.user_id,
                NULL,
                CASE NEW.status WHEN 'planned' THEN 'planned'
                    WHEN 'taught' THEN 'taught' ELSE 'cancelled' END,
                'legacy_service_insert', NEW.scheduled_for
            );
        END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_lesson_material_immutable_v11
        BEFORE UPDATE OF material_id, origin_key ON class_lessons
        WHEN OLD.material_id IS NOT NEW.material_id OR OLD.origin_key IS NOT NEW.origin_key
        BEGIN SELECT RAISE(ABORT, 'lesson material link is immutable'); END
        """
    )
    connection.execute("DROP TRIGGER IF EXISTS trg_lesson_lifecycle_transition_v11")
    connection.execute(
        """
        CREATE TRIGGER trg_lesson_lifecycle_transition_v11
        BEFORE UPDATE OF lifecycle_state ON class_lessons
        WHEN NEW.lifecycle_state != OLD.lifecycle_state
          AND NOT (
            (OLD.lifecycle_state = 'generated' AND NEW.lifecycle_state = 'planned')
            OR (OLD.lifecycle_state = 'planned' AND NEW.lifecycle_state IN ('taught', 'cancelled'))
            OR (OLD.lifecycle_state = 'generated' AND OLD.status = 'taught'
                AND NEW.lifecycle_state = 'taught')
            OR (OLD.lifecycle_state = 'generated' AND OLD.status IN ('cancelled', 'archived')
                AND NEW.lifecycle_state = 'cancelled')
          )
        BEGIN SELECT RAISE(ABORT, 'invalid lesson lifecycle transition'); END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_lesson_material_delete_guard_v11
        BEFORE DELETE ON materials
        WHEN EXISTS (SELECT 1 FROM class_lessons WHERE material_id = OLD.id)
        BEGIN SELECT RAISE(ABORT, 'lesson history keeps its material'); END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_material_lesson_link_immutable_v11
        BEFORE UPDATE OF class_id, user_id ON materials
        WHEN EXISTS (SELECT 1 FROM class_lessons WHERE material_id = OLD.id)
          AND (NEW.class_id IS NOT OLD.class_id OR NEW.user_id != OLD.user_id)
        BEGIN SELECT RAISE(ABORT, 'lesson material class link is immutable'); END
        """
    )
    for operation in ("INSERT", "UPDATE"):
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_outcome_requires_taught_{operation.lower()}_v11
            BEFORE {operation} ON lesson_outcomes
            WHEN NOT EXISTS (
                SELECT 1 FROM class_lessons
                WHERE id = NEW.class_lesson_id AND class_id = NEW.class_id
                  AND user_id = NEW.user_id AND lifecycle_state = 'taught'
            )
            BEGIN SELECT RAISE(ABORT, 'lesson outcome requires a taught lesson'); END
            """
        )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_lesson_transition_owner_v11
        BEFORE INSERT ON class_lesson_transitions
        WHEN NOT EXISTS (
            SELECT 1 FROM class_lessons
            WHERE id = NEW.class_lesson_id AND class_id = NEW.class_id
              AND user_id = NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT, 'ownership mismatch'); END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_lesson_transition_immutable_update_v11
        BEFORE UPDATE ON class_lesson_transitions
        BEGIN SELECT RAISE(ABORT, 'lesson transitions are immutable'); END
        """
    )

    if first_application:
        connection.execute(
            """
            INSERT OR IGNORE INTO class_lesson_transitions (
                event_uuid, class_lesson_id, class_id, user_id,
                from_state, to_state, reason, scheduled_for_snapshot, occurred_at
            )
            SELECT 'day11-migration:' || id || ':' || lifecycle_state,
                   id, class_id, user_id, NULL, lifecycle_state,
                   'day11_migration', scheduled_for, created_at
            FROM class_lessons
            """
        )
    connection.execute(
        "INSERT OR IGNORE INTO schema_versions(version, applied_at) "
        f"VALUES (?, {_UTC_NOW})",
        (SCHEMA_VERSION,),
    )
