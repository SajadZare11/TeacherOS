"""TeacherOS Day 28 Migration (Schema v28).

Persists five-teacher release rehearsal sessions, per-task completion metrics,
Single Ease Question (SEQ) scores, and usability journey telemetry:
- `rehearsal_sessions`: Tracks 5-teacher mission sessions, duration, trust scores, and completion rate.
- `rehearsal_task_metrics`: Tracks granular per-task latency, ease scores, hesitation events, and outcome notes.
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 28
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def apply_schema_v28(connection: sqlite3.Connection) -> None:
    """Apply Schema v28 for 5-teacher release rehearsal telemetry."""
    # 1. Rehearsal Sessions table
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS rehearsal_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_uuid TEXT NOT NULL UNIQUE,
            teacher_identifier TEXT NOT NULL,
            persona_name TEXT NOT NULL,
            tasks_total INTEGER NOT NULL DEFAULT 9,
            tasks_completed INTEGER NOT NULL DEFAULT 0,
            total_duration_seconds REAL NOT NULL,
            avg_seq_score REAL NOT NULL,
            trust_score REAL NOT NULL,
            est_minutes_saved INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('in_progress', 'completed', 'blocked')),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW}
        )
        """
    )

    # 2. Rehearsal Task Metrics table
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS rehearsal_task_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            task_key TEXT NOT NULL,
            duration_seconds REAL NOT NULL,
            seq_score INTEGER NOT NULL CHECK (seq_score BETWEEN 1 AND 7),
            hesitation_count INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL CHECK (completed IN (0, 1)),
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (session_id) REFERENCES rehearsal_sessions(id) ON DELETE CASCADE
        )
        """
    )

    # 3. Indexes
    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_rehearsal_session_time ON rehearsal_sessions(created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_rehearsal_session_teacher ON rehearsal_sessions(teacher_identifier);",
        "CREATE INDEX IF NOT EXISTS idx_rehearsal_task_session ON rehearsal_task_metrics(session_id);",
        "CREATE INDEX IF NOT EXISTS idx_rehearsal_task_key ON rehearsal_task_metrics(task_key);",
    )
    for statement in indexes:
        connection.execute(statement)

    # 4. Record schema version
    connection.execute("INSERT OR IGNORE INTO schema_versions (version) VALUES (28);")
