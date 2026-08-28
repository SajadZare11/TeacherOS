from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 8
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def apply_schema_v8(connection: sqlite3.Connection) -> None:
    """Add the small durable state needed by the Day 8 dashboard and Today queue."""
    if "last_active_at" not in _columns(connection, "classes"):
        connection.execute("ALTER TABLE classes ADD COLUMN last_active_at TEXT")
    connection.execute(
        "UPDATE classes SET last_active_at = COALESCE(last_active_at, updated_at, created_at)"
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS class_action_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            item_type TEXT NOT NULL CHECK (
                item_type IN ('analysis_approval', 'review_due')
            ),
            source_key TEXT NOT NULL CHECK (length(trim(source_key)) BETWEEN 1 AND 100),
            status TEXT NOT NULL DEFAULT 'pending' CHECK (
                status IN ('pending', 'completed', 'dismissed')
            ),
            due_at TEXT,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            resolved_at TEXT,
            FOREIGN KEY (class_id, user_id)
                REFERENCES classes(id, user_id) ON DELETE CASCADE,
            UNIQUE (user_id, class_id, item_type, source_key)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_class_action_owner_status_due "
        "ON class_action_items(user_id, status, item_type, due_at, id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_classes_owner_last_active "
        "ON classes(user_id, status, last_active_at DESC, id DESC)"
    )
    connection.execute(
        f"""
        CREATE TRIGGER IF NOT EXISTS trg_classes_last_active_insert
        AFTER INSERT ON classes
        WHEN NEW.last_active_at IS NULL
        BEGIN
            UPDATE classes SET last_active_at = {_UTC_NOW} WHERE id = NEW.id;
        END
        """
    )
    connection.execute(
        "INSERT OR IGNORE INTO schema_versions(version, applied_at) "
        f"VALUES (?, {_UTC_NOW})",
        (SCHEMA_VERSION,),
    )
