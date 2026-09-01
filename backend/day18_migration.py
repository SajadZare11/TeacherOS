from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 18
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def apply_schema_v18(connection: sqlite3.Connection) -> None:
    """Connect approved evidence analysis directly to targeted teaching follow-up actions and class library materials."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS analysis_followup_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            followup_uuid TEXT NOT NULL UNIQUE CHECK (length(trim(followup_uuid)) BETWEEN 8 AND 100),
            user_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            analysis_id INTEGER NOT NULL,
            finding_target_title TEXT NOT NULL CHECK (length(trim(finding_target_title)) BETWEEN 1 AND 200),
            action_type TEXT NOT NULL CHECK (
                action_type IN (
                    'reteach_lesson', 'targeted_worksheet', 'differentiated_practice',
                    'group_activity', 'reassessment', 'homework'
                )
            ),
            duration_minutes INTEGER NOT NULL DEFAULT 30 CHECK (duration_minutes BETWEEN 5 AND 180),
            material_id INTEGER,
            content_markdown TEXT NOT NULL CHECK (length(trim(content_markdown)) > 0),
            teacher_notes TEXT,
            status TEXT NOT NULL DEFAULT 'generated' CHECK (
                status IN ('generated', 'accepted', 'scheduled', 'archived')
            ),
            prompt_contract TEXT NOT NULL CHECK (length(trim(prompt_contract)) BETWEEN 1 AND 100),
            prompt_version TEXT NOT NULL CHECK (length(trim(prompt_version)) BETWEEN 1 AND 100),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
            FOREIGN KEY (analysis_id) REFERENCES evidence_analysis_results(id) ON DELETE CASCADE,
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE SET NULL
        )
        """
    )

    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS material_evidence_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            analysis_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
            FOREIGN KEY (analysis_id) REFERENCES evidence_analysis_results(id) ON DELETE CASCADE,
            UNIQUE(material_id, analysis_id)
        )
        """
    )

    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_analysis_followup_user_class ON analysis_followup_actions(user_id, class_id, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_analysis_followup_analysis ON analysis_followup_actions(analysis_id);",
        "CREATE INDEX IF NOT EXISTS idx_analysis_followup_uuid ON analysis_followup_actions(followup_uuid);",
        "CREATE INDEX IF NOT EXISTS idx_material_evidence_analysis ON material_evidence_links(analysis_id);",
        "CREATE INDEX IF NOT EXISTS idx_material_evidence_material ON material_evidence_links(material_id);",
    )
    for statement in indexes:
        connection.execute(statement)

    triggers = (
        """
        CREATE TRIGGER IF NOT EXISTS trg_analysis_followup_owner_v18
        BEFORE INSERT ON analysis_followup_actions
        WHEN NOT EXISTS (
            SELECT 1 FROM evidence_analysis_results
            WHERE id = NEW.analysis_id AND user_id = NEW.user_id AND class_id = NEW.class_id
        )
        BEGIN SELECT RAISE(ABORT, 'analysis followup ownership or class mismatch'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_analysis_followup_approved_check_v18
        BEFORE INSERT ON analysis_followup_actions
        WHEN NOT EXISTS (
            SELECT 1 FROM evidence_analysis_results
            WHERE id = NEW.analysis_id AND approved = 1
        )
        BEGIN SELECT RAISE(ABORT, 'cannot create teaching follow-up action from unapproved analysis'); END
        """,
    )
    for trigger in triggers:
        connection.execute(trigger)

    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_analysis_followup_links_update_v18
        BEFORE UPDATE OF user_id, class_id, analysis_id, material_id ON analysis_followup_actions
        WHEN NEW.user_id IS NOT OLD.user_id
          OR NEW.class_id IS NOT OLD.class_id
          OR NEW.analysis_id IS NOT OLD.analysis_id
          OR NEW.material_id IS NOT OLD.material_id
        BEGIN SELECT RAISE(ABORT, 'analysis follow-up links are immutable'); END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_analysis_followup_material_owner_insert_v18
        BEFORE INSERT ON analysis_followup_actions
        WHEN NEW.material_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM materials
            WHERE id = NEW.material_id AND user_id = NEW.user_id
              AND class_id = NEW.class_id
        )
        BEGIN SELECT RAISE(ABORT, 'analysis follow-up material ownership mismatch'); END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_material_evidence_link_owner_insert_v18
        BEFORE INSERT ON material_evidence_links
        WHEN NOT EXISTS (
            SELECT 1
            FROM materials AS m
            JOIN evidence_analysis_results AS a ON a.id = NEW.analysis_id
            WHERE m.id = NEW.material_id
              AND m.user_id = a.user_id
              AND m.class_id IS a.class_id
        )
        BEGIN SELECT RAISE(ABORT, 'material evidence link ownership mismatch'); END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_material_evidence_link_immutable_update_v18
        BEFORE UPDATE ON material_evidence_links
        BEGIN SELECT RAISE(ABORT, 'material evidence links are immutable'); END
        """
    )

    connection.execute("INSERT OR IGNORE INTO schema_versions (version) VALUES (18);")
