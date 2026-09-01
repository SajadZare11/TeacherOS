"""TeacherOS Day 26 Migration (Schema v26).

Persists system reliability, performance snapshots, and health observability:
- `system_health_snapshots`: Tracks latency metrics (p50/p95), provider/db failure counts, disk space, and schema state.
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 26
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def apply_schema_v26(connection: sqlite3.Connection) -> None:
    """Apply Schema v26 for system observability and health snapshots."""
    # 1. System Health Snapshots table
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS system_health_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_uuid TEXT NOT NULL UNIQUE,
            latency_p50_ms REAL NOT NULL,
            latency_p95_ms REAL NOT NULL,
            provider_failures_count INTEGER NOT NULL DEFAULT 0,
            db_locks_count INTEGER NOT NULL DEFAULT 0,
            export_failures_count INTEGER NOT NULL DEFAULT 0,
            disk_free_mb REAL NOT NULL,
            schema_version INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW}
        )
        """
    )

    # 2. Indexes
    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_health_snapshot_time ON system_health_snapshots(created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_health_snapshot_uuid ON system_health_snapshots(snapshot_uuid);",
    )
    for statement in indexes:
        connection.execute(statement)

    # 3. Record schema version
    connection.execute("INSERT OR IGNORE INTO schema_versions (version) VALUES (26);")
