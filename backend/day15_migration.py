from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 15
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def apply_schema_v15(connection: sqlite3.Connection) -> None:
    """Persist owner-scoped evidence batches and anonymous evidence items."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS evidence_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_uuid TEXT NOT NULL UNIQUE CHECK (length(trim(batch_uuid)) BETWEEN 8 AND 100),
            user_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            evidence_type TEXT NOT NULL CHECK (evidence_type IN (
                'writing', 'speaking_notes', 'quiz_exit_ticket', 'homework_task', 'general_work'
            )),
            topic TEXT CHECK (topic IS NULL OR length(trim(topic)) BETWEEN 1 AND 300),
            lesson_id INTEGER,
            objective_id INTEGER,
            source_format TEXT NOT NULL CHECK (source_format IN (
                'pasted_text', 'telegram_text', 'txt_file', 'docx_file'
            )),
            source_filename TEXT CHECK (
                source_filename IS NULL OR length(trim(source_filename)) BETWEEN 1 AND 255
            ),
            item_count INTEGER NOT NULL DEFAULT 0 CHECK (item_count >= 0),
            retention_policy TEXT NOT NULL DEFAULT '30_days' CHECK (retention_policy IN (
                '7_days', '30_days', 'until_deleted', 'manual_only'
            )),
            privacy_confirmed INTEGER NOT NULL DEFAULT 1 CHECK (privacy_confirmed IN (0, 1)),
            status TEXT NOT NULL DEFAULT 'ready' CHECK (status IN (
                'draft', 'ready', 'analyzed', 'deleted', 'purged'
            )),
            deleted_at TEXT,
            purged_at TEXT,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (class_id, user_id) REFERENCES classes(id, user_id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (lesson_id) REFERENCES class_lessons(id) ON DELETE SET NULL,
            FOREIGN KEY (objective_id) REFERENCES class_objectives(id) ON DELETE SET NULL,
            UNIQUE (id, class_id, user_id)
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS evidence_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            student_label TEXT NOT NULL CHECK (length(trim(student_label)) BETWEEN 1 AND 80),
            content TEXT NOT NULL CHECK (length(trim(content)) BETWEEN 1 AND 25000),
            char_count INTEGER NOT NULL CHECK (char_count > 0),
            word_count INTEGER NOT NULL CHECK (word_count >= 0),
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deleted', 'purged')),
            deleted_at TEXT,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (batch_id, class_id, user_id)
                REFERENCES evidence_batches(id, class_id, user_id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE (id, batch_id, class_id, user_id)
        )
        """
    )

    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_evidence_batches_owner ON evidence_batches(user_id, class_id, status, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_evidence_batches_uuid ON evidence_batches(batch_uuid);",
        "CREATE INDEX IF NOT EXISTS idx_evidence_items_batch ON evidence_items(batch_id, user_id, status, id);",
        "CREATE INDEX IF NOT EXISTS idx_evidence_items_class ON evidence_items(class_id, user_id, status);",
    )
    for statement in indexes:
        connection.execute(statement)

    triggers = (
        """
        CREATE TRIGGER IF NOT EXISTS trg_evidence_batch_owner_insert_v15
        BEFORE INSERT ON evidence_batches
        WHEN NOT EXISTS (
            SELECT 1 FROM classes
            WHERE id = NEW.class_id AND user_id = NEW.user_id AND status = 'active'
        )
        BEGIN SELECT RAISE(ABORT, 'evidence batch requires an owned active class'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_evidence_batch_owner_update_v15
        BEFORE UPDATE OF class_id, user_id ON evidence_batches
        WHEN NEW.class_id != OLD.class_id OR NEW.user_id != OLD.user_id
        BEGIN SELECT RAISE(ABORT, 'evidence batch ownership is immutable'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_evidence_item_owner_insert_v15
        BEFORE INSERT ON evidence_items
        WHEN NOT EXISTS (
            SELECT 1 FROM evidence_batches
            WHERE id = NEW.batch_id AND class_id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT, 'evidence item batch ownership mismatch'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_evidence_item_owner_update_v15
        BEFORE UPDATE OF batch_id, class_id, user_id ON evidence_items
        WHEN NEW.batch_id != OLD.batch_id OR NEW.class_id != OLD.class_id OR NEW.user_id != OLD.user_id
        BEGIN SELECT RAISE(ABORT, 'evidence item ownership is immutable'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_evidence_item_count_insert_v15
        AFTER INSERT ON evidence_items
        BEGIN
            UPDATE evidence_batches
            SET item_count = (
                SELECT COUNT(*) FROM evidence_items
                WHERE batch_id = NEW.batch_id AND status = 'active'
            ),
            updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            WHERE id = NEW.batch_id;
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_evidence_item_count_update_v15
        AFTER UPDATE OF status ON evidence_items
        BEGIN
            UPDATE evidence_batches
            SET item_count = (
                SELECT COUNT(*) FROM evidence_items
                WHERE batch_id = NEW.batch_id AND status = 'active'
            ),
            updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            WHERE id = NEW.batch_id;
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_evidence_item_count_delete_v15
        AFTER DELETE ON evidence_items
        BEGIN
            UPDATE evidence_batches
            SET item_count = (
                SELECT COUNT(*) FROM evidence_items
                WHERE batch_id = OLD.batch_id AND status = 'active'
            ),
            updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            WHERE id = OLD.batch_id;
        END
        """,
    )
    for trigger in triggers:
        connection.execute(trigger)

    # Linked lesson/objective IDs must remain inside the same tenant and class.
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_evidence_batch_links_insert_v15
        BEFORE INSERT ON evidence_batches
        WHEN (NEW.lesson_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM class_lessons
            WHERE id = NEW.lesson_id AND class_id = NEW.class_id AND user_id = NEW.user_id
        )) OR (NEW.objective_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM class_objectives
            WHERE id = NEW.objective_id AND class_id = NEW.class_id AND user_id = NEW.user_id
        ))
        BEGIN SELECT RAISE(ABORT, 'evidence batch linked record ownership mismatch'); END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_evidence_batch_links_update_v15
        BEFORE UPDATE OF lesson_id, objective_id, class_id, user_id ON evidence_batches
        WHEN (NEW.lesson_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM class_lessons
            WHERE id = NEW.lesson_id AND class_id = NEW.class_id AND user_id = NEW.user_id
        )) OR (NEW.objective_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM class_objectives
            WHERE id = NEW.objective_id AND class_id = NEW.class_id AND user_id = NEW.user_id
        ))
        BEGIN SELECT RAISE(ABORT, 'evidence batch linked record ownership mismatch'); END
        """
    )

    connection.execute("INSERT OR IGNORE INTO schema_versions (version) VALUES (15);")
