"""TeacherOS Day 25 Migration (Schema v25).

Persists commercial entitlement events and upgrade funnel instrumentation:
- `entitlement_events`: Tracks funnel actions (viewed, dismissed, checkout_started, paid, failed, refunded, cancelled, entitlement_restored).
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 25
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def apply_schema_v25(connection: sqlite3.Connection) -> None:
    """Apply Schema v25 for commercial entitlement events and upgrade tracking."""
    # 1. Entitlement events table
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS entitlement_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_uuid TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            event_type TEXT NOT NULL CHECK (
                event_type IN (
                    'viewed', 'dismissed', 'checkout_started',
                    'paid', 'failed', 'refunded', 'cancelled',
                    'entitlement_restored'
                )
            ),
            plan_code TEXT NOT NULL,
            feature_key TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{{}}',
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # 2. Indexes
    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_entitlement_event_user ON entitlement_events(user_id, event_type, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_entitlement_event_type ON entitlement_events(event_type, plan_code);",
        "CREATE INDEX IF NOT EXISTS idx_entitlement_event_uuid ON entitlement_events(event_uuid);",
    )
    for statement in indexes:
        connection.execute(statement)

    # 3. Record schema version
    connection.execute("INSERT OR IGNORE INTO schema_versions (version) VALUES (25);")
