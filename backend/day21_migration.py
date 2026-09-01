"""TeacherOS Day 21 Migration (Schema v21).

Adds evidence-linked class progress tracking:
- Proposed objective extraction queue (with mandatory teacher approval)
- Traceable objective-to-evidence links (every claim cites source lesson/outcome/analysis)
- Extended objective status tracking ('current', 'needs_support', 'secure', 'paused', 'archived')
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 21
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def apply_schema_v21(connection: sqlite3.Connection) -> None:
    """Apply Schema v21 for evidence-linked class progress."""
    # 1. Proposed objectives extraction queue
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS proposed_class_objectives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_uuid TEXT NOT NULL UNIQUE CHECK (length(trim(proposal_uuid)) BETWEEN 8 AND 100),
            user_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            source_type TEXT NOT NULL CHECK (source_type IN ('lesson', 'evidence_analysis', 'writing_feedback', 'manual')),
            source_id INTEGER,
            objective_text TEXT NOT NULL CHECK (length(trim(objective_text)) BETWEEN 1 AND 1000),
            category TEXT NOT NULL DEFAULT 'general' CHECK (
                category IN ('vocabulary', 'grammar', 'pronunciation', 'functional_language', 'skills', 'exam_strategy', 'general')
            ),
            proposed_status TEXT NOT NULL DEFAULT 'current' CHECK (
                proposed_status IN ('current', 'needs_support', 'secure')
            ),
            confidence TEXT NOT NULL DEFAULT 'medium' CHECK (confidence IN ('low', 'medium', 'high')),
            rationale TEXT NOT NULL CHECK (length(trim(rationale)) > 0),
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            reviewed_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        )
        """
    )

    # 2. Traceable objective-to-evidence claims
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS objective_evidence_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_uuid TEXT NOT NULL UNIQUE CHECK (length(trim(link_uuid)) BETWEEN 8 AND 100),
            objective_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            source_type TEXT NOT NULL CHECK (
                source_type IN ('lesson', 'lesson_outcome', 'evidence_analysis', 'writing_feedback', 'retrieval_review', 'manual_judgment', 'manual')
            ),
            source_id INTEGER,
            support_level TEXT NOT NULL CHECK (
                support_level IN ('introduced', 'observed_working', 'needs_support', 'secure_confirmed')
            ),
            evidence_excerpt TEXT NOT NULL CHECK (length(trim(evidence_excerpt)) > 0),
            teacher_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (teacher_confirmed IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (objective_id) REFERENCES class_objectives(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        )
        """
    )

    # 3. Add extended columns to class_objectives
    obj_cols = _columns(connection, "class_objectives")
    if "category" not in obj_cols:
        connection.execute(
            "ALTER TABLE class_objectives ADD COLUMN category TEXT NOT NULL DEFAULT 'general'"
        )
    if "is_secure" not in obj_cols:
        connection.execute(
            "ALTER TABLE class_objectives ADD COLUMN is_secure INTEGER NOT NULL DEFAULT 0"
        )
    if "secure_confirmed_at" not in obj_cols:
        connection.execute(
            "ALTER TABLE class_objectives ADD COLUMN secure_confirmed_at TEXT"
        )
    if "support_level" not in obj_cols:
        connection.execute(
            "ALTER TABLE class_objectives ADD COLUMN support_level TEXT NOT NULL DEFAULT 'introduced'"
        )

    # 4. Indexes for rapid, owner-scoped progress queries
    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_proposed_obj_class ON proposed_class_objectives(class_id, status, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_proposed_obj_user ON proposed_class_objectives(user_id, status);",
        "CREATE INDEX IF NOT EXISTS idx_obj_ev_links_obj ON objective_evidence_links(objective_id, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_obj_ev_links_class ON objective_evidence_links(class_id, support_level);",
        "CREATE INDEX IF NOT EXISTS idx_obj_ev_links_user ON objective_evidence_links(user_id);",
    )
    for statement in indexes:
        connection.execute(statement)

    # 5. Class ownership triggers
    triggers = (
        """
        CREATE TRIGGER IF NOT EXISTS trg_proposed_obj_owner_v21
        BEFORE INSERT ON proposed_class_objectives
        WHEN NOT EXISTS (
            SELECT 1 FROM classes
            WHERE id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'Proposed objective user_id does not own class_id');
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_obj_ev_link_owner_v21
        BEFORE INSERT ON objective_evidence_links
        WHEN NOT EXISTS (
            SELECT 1 FROM classes
            WHERE id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'Objective evidence link user_id does not own class_id');
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_obj_ev_link_objective_owner_v21
        BEFORE INSERT ON objective_evidence_links
        WHEN NOT EXISTS (
            SELECT 1 FROM class_objectives
            WHERE id = NEW.objective_id AND user_id = NEW.user_id AND class_id = NEW.class_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'Objective evidence link objective ownership mismatch');
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_obj_ev_link_immutable_update_v21
        BEFORE UPDATE OF objective_id, user_id, class_id ON objective_evidence_links
        WHEN NEW.objective_id IS NOT OLD.objective_id
          OR NEW.user_id IS NOT OLD.user_id
          OR NEW.class_id IS NOT OLD.class_id
        BEGIN
            SELECT RAISE(ABORT, 'Objective evidence link ownership is immutable');
        END;
        """,
    )
    for trigger in triggers:
        connection.execute(trigger)

    # 6. Record schema version
    connection.execute("INSERT OR IGNORE INTO schema_versions (version) VALUES (21);")
