"""TeacherOS Day 27 Migration (Schema v27).

Persists security audit events, unauthorized access attempts, prompt injection defenses,
and privacy data deletion tracking:
- `security_audit_logs`: Records tamper events, cross-user denial actions, injection blocks, and GDPR purge operations.
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 27
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def apply_schema_v27(connection: sqlite3.Connection) -> None:
    """Apply Schema v27 for security audit logging and tamper event tracking."""
    # 1. Security Audit Logs table
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS security_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_uuid TEXT NOT NULL UNIQUE,
            user_id INTEGER,
            event_type TEXT NOT NULL,
            severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
            target_resource TEXT,
            details_json TEXT NOT NULL DEFAULT '{{}}',
            ip_address TEXT,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )

    # 2. Indexes
    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_security_audit_time ON security_audit_logs(created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_security_audit_event ON security_audit_logs(event_type, severity);",
        "CREATE INDEX IF NOT EXISTS idx_security_audit_user ON security_audit_logs(user_id);",
    )
    for statement in indexes:
        connection.execute(statement)

    # 3. Record schema version
    connection.execute("INSERT OR IGNORE INTO schema_versions (version) VALUES (27);")
