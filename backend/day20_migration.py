from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 20
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def apply_schema_v20(connection: sqlite3.Connection) -> None:
    """Persist transparent retrieval and spaced-review queue items and audit logs."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS retrieval_review_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_uuid TEXT NOT NULL UNIQUE CHECK (length(trim(item_uuid)) BETWEEN 8 AND 100),
            user_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            category TEXT NOT NULL CHECK (
                category IN (
                    'vocabulary', 'grammar', 'pronunciation',
                    'functional_language', 'common_error', 'exam_strategy'
                )
            ),
            prompt_text TEXT NOT NULL CHECK (length(trim(prompt_text)) > 0),
            target_answer TEXT NOT NULL CHECK (length(trim(target_answer)) > 0),
            notes TEXT,
            source_type TEXT NOT NULL CHECK (
                source_type IN ('lesson', 'evidence_analysis', 'writing_feedback', 'manual')
            ),
            source_id INTEGER,
            interval_stage INTEGER NOT NULL DEFAULT 0 CHECK (interval_stage >= 0),
            interval_days_json TEXT NOT NULL DEFAULT '[2, 7, 21, 45]',
            confidence TEXT NOT NULL DEFAULT 'medium' CHECK (confidence IN ('low', 'medium', 'high')),
            status TEXT NOT NULL DEFAULT 'active' CHECK (
                status IN ('active', 'due', 'snoozed', 'paused', 'mastered', 'archived')
            ),
            introduced_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            last_reviewed_at TEXT,
            next_review_date TEXT NOT NULL,
            snoozed_until TEXT,
            review_count INTEGER NOT NULL DEFAULT 0 CHECK (review_count >= 0),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        )
        """
    )

    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS retrieval_review_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            review_date TEXT NOT NULL,
            result TEXT NOT NULL CHECK (result IN ('remembered', 'partly_remembered', 'forgotten')),
            stage_before INTEGER NOT NULL,
            stage_after INTEGER NOT NULL,
            next_date_after TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (item_id) REFERENCES retrieval_review_items(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        )
        """
    )

    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_retrieval_user_class_status ON retrieval_review_items(user_id, class_id, status, next_review_date);",
        "CREATE INDEX IF NOT EXISTS idx_retrieval_class_due ON retrieval_review_items(class_id, next_review_date);",
        "CREATE INDEX IF NOT EXISTS idx_retrieval_item_uuid ON retrieval_review_items(item_uuid);",
        "CREATE INDEX IF NOT EXISTS idx_retrieval_logs_item ON retrieval_review_logs(item_id, created_at DESC);",
    )
    for statement in indexes:
        connection.execute(statement)

    triggers = (
        """
        CREATE TRIGGER IF NOT EXISTS trg_retrieval_class_owner_v20
        BEFORE INSERT ON retrieval_review_items
        WHEN NOT EXISTS (
            SELECT 1 FROM classes WHERE id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT, 'retrieval item class owner mismatch'); END
        """,
    )
    for trigger in triggers:
        connection.execute(trigger)

    connection.execute("INSERT OR IGNORE INTO schema_versions (version) VALUES (20);")
