from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 17
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def apply_schema_v17(connection: sqlite3.Connection) -> None:
    """Persist owner-scoped student writing feedback, revision tasks, and dual export copies."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS writing_feedback_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feedback_uuid TEXT NOT NULL UNIQUE CHECK (length(trim(feedback_uuid)) BETWEEN 8 AND 100),
            user_id INTEGER NOT NULL,
            class_id INTEGER,
            evidence_item_id INTEGER,
            student_label TEXT NOT NULL DEFAULT 'Student' CHECK (
                length(trim(student_label)) BETWEEN 1 AND 80
            ),
            student_level TEXT NOT NULL CHECK (
                length(trim(student_level)) BETWEEN 1 AND 10
            ),
            feedback_mode TEXT NOT NULL CHECK (
                feedback_mode IN ('light', 'balanced', 'detailed', 'rubric')
            ),
            task_prompt TEXT,
            rubric_name TEXT,
            rubric_json TEXT,
            feedback_json TEXT NOT NULL CHECK (
                json_valid(feedback_json) AND json_type(feedback_json) = 'object'
            ),
            teacher_comments TEXT,
            revision_task TEXT NOT NULL,
            student_copy_text TEXT NOT NULL,
            teacher_copy_text TEXT NOT NULL,
            estimated_minutes_saved INTEGER NOT NULL DEFAULT 12 CHECK (estimated_minutes_saved >= 0),
            approved INTEGER NOT NULL DEFAULT 0 CHECK (approved IN (0, 1)),
            approved_at TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (
                status IN ('draft', 'approved', 'archived')
            ),
            prompt_contract TEXT NOT NULL CHECK (length(trim(prompt_contract)) BETWEEN 1 AND 100),
            prompt_version TEXT NOT NULL CHECK (length(trim(prompt_version)) BETWEEN 1 AND 100),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL,
            FOREIGN KEY (evidence_item_id) REFERENCES evidence_items(id) ON DELETE SET NULL
        )
        """
    )

    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_writing_feedback_user_created ON writing_feedback_records(user_id, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_writing_feedback_class ON writing_feedback_records(class_id, user_id, status);",
        "CREATE INDEX IF NOT EXISTS idx_writing_feedback_uuid ON writing_feedback_records(feedback_uuid);",
        "CREATE INDEX IF NOT EXISTS idx_writing_feedback_evidence ON writing_feedback_records(evidence_item_id);",
    )
    for statement in indexes:
        connection.execute(statement)

    triggers = (
        """
        CREATE TRIGGER IF NOT EXISTS trg_writing_feedback_class_owner_v17
        BEFORE INSERT ON writing_feedback_records
        WHEN NEW.class_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM classes WHERE id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT, 'writing feedback class ownership mismatch'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_writing_feedback_evidence_owner_v17
        BEFORE INSERT ON writing_feedback_records
        WHEN NEW.evidence_item_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM evidence_items WHERE id = NEW.evidence_item_id AND user_id = NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT, 'writing feedback evidence item ownership mismatch'); END
        """,
    )
    for trigger in triggers:
        connection.execute(trigger)

    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_writing_feedback_links_update_v17
        BEFORE UPDATE OF user_id, class_id, evidence_item_id ON writing_feedback_records
        WHEN NEW.user_id IS NOT OLD.user_id
          OR NEW.class_id IS NOT OLD.class_id
          OR NEW.evidence_item_id IS NOT OLD.evidence_item_id
        BEGIN SELECT RAISE(ABORT, 'writing feedback ownership is immutable'); END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_writing_feedback_evidence_class_insert_v17
        BEFORE INSERT ON writing_feedback_records
        WHEN NEW.evidence_item_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM evidence_items
            WHERE id = NEW.evidence_item_id AND user_id = NEW.user_id
              AND class_id IS NEW.class_id
        )
        BEGIN SELECT RAISE(ABORT, 'writing feedback evidence class mismatch'); END
        """
    )

    connection.execute("INSERT OR IGNORE INTO schema_versions (version) VALUES (17);")
