from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 7
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _add_column(
    connection: sqlite3.Connection,
    table: str,
    name: str,
    definition: str,
) -> None:
    if name not in _columns(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def apply_schema_v7(connection: sqlite3.Connection) -> None:
    """Add durable, resumable Day 7 setup state without rewriting class rows."""
    additions = (
        ("lesson_duration_minutes", "INTEGER CHECK (lesson_duration_minutes IS NULL OR lesson_duration_minutes IN (30, 45, 60, 90))"),
        ("weak_areas_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("coursebook", "TEXT"),
        ("coursebook_unit", "TEXT"),
        ("equipment_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("teaching_preferences_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("setup_profile_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("setup_idempotency_key", "TEXT"),
        ("setup_draft_id", "INTEGER"),
    )
    for name, definition in additions:
        _add_column(connection, "classes", name, definition)

    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS class_setup_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            idempotency_key TEXT NOT NULL UNIQUE,
            step TEXT NOT NULL CHECK (step IN (
                'name', 'level', 'age', 'size', 'duration', 'goal',
                'weak', 'book', 'equipment', 'preference', 'review'
            )),
            payload_json TEXT NOT NULL DEFAULT '{{}}',
            revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
            started_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_classes_setup_idempotency "
        "ON classes(setup_idempotency_key) WHERE setup_idempotency_key IS NOT NULL"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_classes_setup_draft "
        "ON classes(setup_draft_id) WHERE setup_draft_id IS NOT NULL"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_setup_drafts_owner_updated "
        "ON class_setup_drafts(user_id, updated_at DESC)"
    )
    connection.execute(
        "INSERT OR IGNORE INTO schema_versions(version, applied_at) "
        f"VALUES (?, {_UTC_NOW})",
        (SCHEMA_VERSION,),
    )
