"""TeacherOS Day 23 Migration (Schema v23).

Persists editable, evidence-safe class progress reports and revisions:
- `class_progress_reports`: Whole-class, end-of-unit, and reflection reports.
- `progress_report_revisions`: Versioned edit history for audit and edit intensity tracking.
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 23
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def apply_schema_v23(connection: sqlite3.Connection) -> None:
    """Apply Schema v23 for editable, evidence-safe progress reports."""
    # 1. Class progress reports table
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS class_progress_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_uuid TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            report_type TEXT NOT NULL CHECK (
                report_type IN ('whole_class_summary', 'end_of_unit_summary', 'teacher_reflection')
            ),
            title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 3 AND 200),
            reporting_period_start TEXT NOT NULL,
            reporting_period_end TEXT NOT NULL,
            unit_id INTEGER,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'archived')),
            version INTEGER NOT NULL DEFAULT 1,
            learning_covered_text TEXT NOT NULL,
            strengths_text TEXT NOT NULL,
            priorities_text TEXT NOT NULL,
            change_observed_text TEXT NOT NULL,
            next_steps_text TEXT NOT NULL,
            teacher_comments TEXT,
            has_insufficient_evidence INTEGER NOT NULL DEFAULT 0 CHECK (has_insufficient_evidence IN (0, 1)),
            evidence_summary_json TEXT NOT NULL DEFAULT '{{}}',
            source_ids_json TEXT NOT NULL DEFAULT '[]',
            share_safe_verified INTEGER NOT NULL DEFAULT 0 CHECK (share_safe_verified IN (0, 1)),
            approved_at TEXT,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
            FOREIGN KEY (unit_id) REFERENCES class_curriculum_units(id) ON DELETE SET NULL
        )
        """
    )

    # 2. Progress report revisions table (audit trail)
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS progress_report_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            field_changed TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (report_id) REFERENCES class_progress_reports(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # 3. Indexes
    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_prog_rep_class_type ON class_progress_reports(class_id, report_type, status, updated_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_prog_rep_user ON class_progress_reports(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_prog_rep_uuid ON class_progress_reports(report_uuid);",
        "CREATE INDEX IF NOT EXISTS idx_prog_rep_rev_rep ON progress_report_revisions(report_id, version);",
    )
    for statement in indexes:
        connection.execute(statement)

    # 4. Ownership triggers
    triggers = (
        """
        CREATE TRIGGER IF NOT EXISTS trg_progress_report_owner_v23
        BEFORE INSERT ON class_progress_reports
        WHEN NOT EXISTS (
            SELECT 1 FROM classes WHERE id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'Progress report user_id does not own class_id');
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_report_revision_owner_v23
        BEFORE INSERT ON progress_report_revisions
        WHEN NOT EXISTS (
            SELECT 1 FROM class_progress_reports WHERE id = NEW.report_id AND user_id = NEW.user_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'Report revision user_id does not own report_id');
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_progress_report_unit_owner_v23
        BEFORE INSERT ON class_progress_reports
        WHEN NEW.unit_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM class_curriculum_units
            WHERE id = NEW.unit_id AND class_id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'Progress report unit ownership mismatch');
        END;
        """,
    )
    for trigger in triggers:
        connection.execute(trigger)

    # 5. Record schema version
    connection.execute("INSERT OR IGNORE INTO schema_versions (version) VALUES (23);")
