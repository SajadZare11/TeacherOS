from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 12
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def apply_schema_v12(connection: sqlite3.Connection) -> None:
    """Add the owner-scoped Day 12 outcome check-in and reminder records."""
    first_application = connection.execute(
        "SELECT 1 FROM schema_versions WHERE version = ?", (SCHEMA_VERSION,)
    ).fetchone() is None
    additions = {
        "difficulty_categories_json": (
            "TEXT NOT NULL DEFAULT '[]' CHECK ("
            "json_valid(difficulty_categories_json) AND "
            "json_type(difficulty_categories_json) = 'array')"
        ),
        "completion_status": (
            "TEXT CHECK (completion_status IS NULL OR completion_status IN ("
            "'completed', 'partly_completed', 'not_completed'))"
        ),
        "facts_version": "INTEGER NOT NULL DEFAULT 1 CHECK (facts_version > 0)",
        "capture_source": (
            "TEXT NOT NULL DEFAULT 'legacy' CHECK ("
            "capture_source IN ('legacy', 'three_tap'))"
        ),
        "saved_at": "TEXT",
        "note_updated_at": "TEXT",
    }
    existing = _columns(connection, "lesson_outcomes")
    for name, definition in additions.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE lesson_outcomes ADD COLUMN {name} {definition}")

    connection.execute(
        "UPDATE lesson_outcomes SET saved_at = COALESCE(saved_at, updated_at, created_at) "
        "WHERE status IN ('saved', 'approved')"
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS lesson_outcome_fact_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_uuid TEXT NOT NULL UNIQUE CHECK (length(trim(event_uuid)) BETWEEN 8 AND 100),
            lesson_outcome_id INTEGER NOT NULL,
            class_lesson_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            facts_version INTEGER NOT NULL CHECK (facts_version > 0),
            result TEXT NOT NULL CHECK (result IN (
                'not_assessed', 'not_met', 'partly_met', 'met', 'exceeded'
            )),
            difficulty_categories_json TEXT NOT NULL CHECK (
                json_valid(difficulty_categories_json) AND
                json_type(difficulty_categories_json) = 'array'
            ),
            completion_status TEXT CHECK (
                completion_status IS NULL OR completion_status IN (
                    'completed', 'partly_completed', 'not_completed'
                )
            ),
            note_present INTEGER NOT NULL CHECK (note_present IN (0, 1)),
            note_sha256 TEXT CHECK (note_sha256 IS NULL OR length(note_sha256) = 64),
            reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 100),
            recorded_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (lesson_outcome_id, class_lesson_id, class_id, user_id)
                REFERENCES lesson_outcomes(id, class_lesson_id, class_id, user_id)
                ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS lesson_outcome_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_lesson_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            local_choice TEXT NOT NULL CHECK (
                local_choice IN ('one_hour', 'local_18', 'local_20', 'tomorrow_09')
            ),
            next_prompt_at_utc TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (
                status IN ('pending', 'delivered', 'completed', 'cancelled')
            ),
            prompt_count INTEGER NOT NULL DEFAULT 0 CHECK (
                prompt_count BETWEEN 0 AND 3
            ),
            last_prompted_at_utc TEXT,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (class_lesson_id, class_id, user_id)
                REFERENCES class_lessons(id, class_id, user_id) ON DELETE CASCADE,
            UNIQUE (user_id, class_lesson_id)
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS lesson_outcome_ai_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_outcome_id INTEGER NOT NULL,
            class_lesson_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            suggestion_json TEXT NOT NULL CHECK (
                json_valid(suggestion_json) AND json_type(suggestion_json) = 'object'
            ),
            source_record_ids_json TEXT NOT NULL DEFAULT '[]' CHECK (
                json_valid(source_record_ids_json) AND
                json_type(source_record_ids_json) = 'array'
            ),
            status TEXT NOT NULL DEFAULT 'proposed' CHECK (
                status IN ('proposed', 'accepted', 'dismissed')
            ),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (lesson_outcome_id, class_lesson_id, class_id, user_id)
                REFERENCES lesson_outcomes(id, class_lesson_id, class_id, user_id)
                ON DELETE CASCADE
        )
        """
    )

    indexes = (
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_outcomes_composite_v12 "
        "ON lesson_outcomes(id, class_lesson_id, class_id, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_outcome_facts_owner_lesson_v12 "
        "ON lesson_outcome_fact_revisions(user_id, class_id, class_lesson_id, facts_version)",
        "CREATE INDEX IF NOT EXISTS idx_outcome_reminders_due_v12 "
        "ON lesson_outcome_reminders(status, next_prompt_at_utc, prompt_count, id)",
        "CREATE INDEX IF NOT EXISTS idx_outcome_suggestions_owner_v12 "
        "ON lesson_outcome_ai_suggestions(user_id, class_id, class_lesson_id, status, id)",
    )
    for statement in indexes:
        connection.execute(statement)

    triggers = (
        """
        CREATE TRIGGER IF NOT EXISTS trg_outcome_active_unique_insert_v12
        BEFORE INSERT ON lesson_outcomes
        WHEN NEW.status != 'archived' AND EXISTS (
            SELECT 1 FROM lesson_outcomes
            WHERE user_id = NEW.user_id AND class_lesson_id = NEW.class_lesson_id
              AND status != 'archived'
        )
        BEGIN SELECT RAISE(ABORT, 'lesson already has an active outcome'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_outcome_active_unique_update_v12
        BEFORE UPDATE OF user_id, class_lesson_id, status ON lesson_outcomes
        WHEN NEW.status != 'archived' AND EXISTS (
            SELECT 1 FROM lesson_outcomes
            WHERE user_id = NEW.user_id AND class_lesson_id = NEW.class_lesson_id
              AND status != 'archived' AND id != OLD.id
        )
        BEGIN SELECT RAISE(ABORT, 'lesson already has an active outcome'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_outcome_three_tap_complete_insert_v12
        BEFORE INSERT ON lesson_outcomes
        WHEN NEW.capture_source = 'three_tap' AND NEW.status IN ('saved', 'approved')
          AND (
              NEW.result NOT IN ('not_met', 'partly_met', 'met')
              OR NEW.completion_status IS NULL
              OR NOT json_valid(NEW.difficulty_categories_json)
              OR json_array_length(NEW.difficulty_categories_json) < 1
          )
        BEGIN SELECT RAISE(ABORT, 'three-tap outcome facts are incomplete'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_outcome_three_tap_complete_update_v12
        BEFORE UPDATE ON lesson_outcomes
        WHEN NEW.capture_source = 'three_tap' AND NEW.status IN ('saved', 'approved')
          AND (
              NEW.result NOT IN ('not_met', 'partly_met', 'met')
              OR NEW.completion_status IS NULL
              OR NOT json_valid(NEW.difficulty_categories_json)
              OR json_array_length(NEW.difficulty_categories_json) < 1
          )
        BEGIN SELECT RAISE(ABORT, 'three-tap outcome facts are incomplete'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_outcome_revision_owner_v12
        BEFORE INSERT ON lesson_outcome_fact_revisions
        WHEN NOT EXISTS (
            SELECT 1 FROM lesson_outcomes
            WHERE id = NEW.lesson_outcome_id
              AND class_lesson_id = NEW.class_lesson_id
              AND class_id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT, 'outcome revision ownership mismatch'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_outcome_revision_immutable_update_v12
        BEFORE UPDATE ON lesson_outcome_fact_revisions
        BEGIN SELECT RAISE(ABORT, 'outcome fact revisions are immutable'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_outcome_reminder_owner_insert_v12
        BEFORE INSERT ON lesson_outcome_reminders
        WHEN NOT EXISTS (
            SELECT 1 FROM class_lessons
            WHERE id = NEW.class_lesson_id AND class_id = NEW.class_id
              AND user_id = NEW.user_id AND lifecycle_state = 'taught'
        )
        BEGIN SELECT RAISE(ABORT, 'outcome reminder requires an owned taught lesson'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_outcome_reminder_owner_update_v12
        BEFORE UPDATE OF class_lesson_id, class_id, user_id ON lesson_outcome_reminders
        WHEN NEW.class_lesson_id != OLD.class_lesson_id
          OR NEW.class_id != OLD.class_id OR NEW.user_id != OLD.user_id
        BEGIN SELECT RAISE(ABORT, 'outcome reminder ownership is immutable'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_outcome_suggestion_owner_v12
        BEFORE INSERT ON lesson_outcome_ai_suggestions
        WHEN NOT EXISTS (
            SELECT 1 FROM lesson_outcomes
            WHERE id = NEW.lesson_outcome_id
              AND class_lesson_id = NEW.class_lesson_id
              AND class_id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT, 'outcome suggestion ownership mismatch'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_outcome_completes_reminder_insert_v12
        AFTER INSERT ON lesson_outcomes
        WHEN NEW.status != 'archived'
        BEGIN
            UPDATE lesson_outcome_reminders
            SET status = 'completed', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE user_id = NEW.user_id AND class_lesson_id = NEW.class_lesson_id;
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_outcome_completes_reminder_update_v12
        AFTER UPDATE OF status ON lesson_outcomes
        WHEN NEW.status != 'archived'
        BEGIN
            UPDATE lesson_outcome_reminders
            SET status = 'completed', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE user_id = NEW.user_id AND class_lesson_id = NEW.class_lesson_id;
        END
        """,
    )
    for statement in triggers:
        connection.execute(statement)

    if first_application:
        connection.execute(
            """
            INSERT OR IGNORE INTO lesson_outcome_fact_revisions (
                event_uuid, lesson_outcome_id, class_lesson_id, class_id, user_id,
                facts_version, result, difficulty_categories_json,
                completion_status, note_present, reason, recorded_at
            )
            SELECT 'day12-migration:' || id, id, class_lesson_id, class_id, user_id,
                   facts_version, result, difficulty_categories_json,
                   completion_status, CASE WHEN notes IS NULL OR trim(notes) = '' THEN 0 ELSE 1 END,
                   'day12_migration', COALESCE(updated_at, created_at)
            FROM lesson_outcomes
            """
        )
    connection.execute(
        "INSERT OR IGNORE INTO schema_versions(version, applied_at) "
        f"VALUES (?, {_UTC_NOW})",
        (SCHEMA_VERSION,),
    )
