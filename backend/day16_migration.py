from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 16
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def apply_schema_v16(connection: sqlite3.Connection) -> None:
    """Persist owner-scoped evidence analysis findings, uncertainty, and teacher approvals."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS evidence_analysis_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_uuid TEXT NOT NULL UNIQUE CHECK (length(trim(analysis_uuid)) BETWEEN 8 AND 100),
            batch_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            response_count INTEGER NOT NULL CHECK (response_count > 0),
            findings_json TEXT NOT NULL CHECK (
                json_valid(findings_json) AND json_type(findings_json) = 'object'
            ),
            uncertainty TEXT NOT NULL CHECK (uncertainty IN ('low', 'medium', 'high')),
            uncertainty_reason TEXT NOT NULL CHECK (
                length(trim(uncertainty_reason)) BETWEEN 1 AND 1000
            ),
            limited_evidence_notice TEXT CHECK (
                limited_evidence_notice IS NULL OR length(trim(limited_evidence_notice)) BETWEEN 1 AND 1000
            ),
            approved INTEGER NOT NULL DEFAULT 0 CHECK (approved IN (0, 1)),
            approved_summary TEXT CHECK (
                approved_summary IS NULL OR length(trim(approved_summary)) BETWEEN 1 AND 5000
            ),
            approved_at TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (
                status IN ('draft', 'approved', 'rejected', 'archived')
            ),
            prompt_contract TEXT NOT NULL CHECK (length(trim(prompt_contract)) BETWEEN 1 AND 100),
            prompt_version TEXT NOT NULL CHECK (length(trim(prompt_version)) BETWEEN 1 AND 100),
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
        "CREATE INDEX IF NOT EXISTS idx_evidence_analysis_batch ON evidence_analysis_results(batch_id, user_id, status, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_evidence_analysis_class ON evidence_analysis_results(class_id, user_id, status);",
        "CREATE INDEX IF NOT EXISTS idx_evidence_analysis_uuid ON evidence_analysis_results(analysis_uuid);",
    )
    for statement in indexes:
        connection.execute(statement)

    triggers = (
        """
        CREATE TRIGGER IF NOT EXISTS trg_evidence_analysis_owner_insert_v16
        BEFORE INSERT ON evidence_analysis_results
        WHEN NOT EXISTS (
            SELECT 1 FROM evidence_batches
            WHERE id = NEW.batch_id AND class_id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT, 'evidence analysis batch ownership mismatch'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_evidence_analysis_owner_update_v16
        BEFORE UPDATE OF batch_id, class_id, user_id ON evidence_analysis_results
        WHEN NEW.batch_id != OLD.batch_id OR NEW.class_id != OLD.class_id OR NEW.user_id != OLD.user_id
        BEGIN SELECT RAISE(ABORT, 'evidence analysis ownership is immutable'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_evidence_analysis_approved_immutable_v16
        BEFORE UPDATE OF findings_json, response_count, uncertainty ON evidence_analysis_results
        WHEN OLD.approved = 1 AND NEW.approved = 1
        BEGIN SELECT RAISE(ABORT, 'approved analysis findings are immutable'); END
        """,
    )
    for trigger in triggers:
        connection.execute(trigger)

    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_evidence_analysis_approval_guard_v16
        BEFORE UPDATE OF approved ON evidence_analysis_results
        WHEN OLD.approved = 1 AND NEW.approved != 1
        BEGIN SELECT RAISE(ABORT, 'approved analysis cannot be unapproved'); END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_evidence_analysis_active_source_v16
        BEFORE INSERT ON evidence_analysis_results
        WHEN NOT EXISTS (
            SELECT 1
            FROM evidence_batches AS b
            JOIN classes AS c ON c.id = b.class_id AND c.user_id = b.user_id
            WHERE b.id = NEW.batch_id AND b.class_id = NEW.class_id
              AND b.user_id = NEW.user_id AND b.status NOT IN ('deleted', 'purged')
              AND c.status = 'active'
        )
        BEGIN SELECT RAISE(ABORT, 'evidence analysis requires an active source'); END
        """
    )

    connection.execute("INSERT OR IGNORE INTO schema_versions (version) VALUES (16);")
