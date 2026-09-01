from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 19
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def apply_schema_v19(connection: sqlite3.Connection) -> None:
    """Persist 3-tier differentiation (Support/Core/Challenge) and 1-tap emergency adaptations."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS material_differentiations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            diff_uuid TEXT NOT NULL UNIQUE CHECK (length(trim(diff_uuid)) BETWEEN 8 AND 100),
            user_id INTEGER NOT NULL,
            class_id INTEGER,
            source_material_id INTEGER NOT NULL,
            objective TEXT NOT NULL CHECK (length(trim(objective)) > 0),
            support_route_markdown TEXT NOT NULL CHECK (length(trim(support_route_markdown)) > 0),
            core_route_markdown TEXT NOT NULL CHECK (length(trim(core_route_markdown)) > 0),
            challenge_route_markdown TEXT NOT NULL CHECK (length(trim(challenge_route_markdown)) > 0),
            delivery_guidance_markdown TEXT NOT NULL CHECK (length(trim(delivery_guidance_markdown)) > 0),
            prompt_contract TEXT NOT NULL CHECK (length(trim(prompt_contract)) BETWEEN 1 AND 100),
            prompt_version TEXT NOT NULL CHECK (length(trim(prompt_version)) BETWEEN 1 AND 100),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL,
            FOREIGN KEY (source_material_id) REFERENCES materials(id) ON DELETE CASCADE
        )
        """
    )

    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS material_adaptations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            adaptation_uuid TEXT NOT NULL UNIQUE CHECK (length(trim(adaptation_uuid)) BETWEEN 8 AND 100),
            user_id INTEGER NOT NULL,
            class_id INTEGER,
            source_material_id INTEGER NOT NULL,
            adaptation_type TEXT NOT NULL CHECK (
                adaptation_type IN (
                    'shorter', 'longer_plus15', 'fast_finisher', 'easier_scaffold',
                    'harder_extension', 'no_tech_low_resource', 'large_class',
                    'more_communicative', 'more_exam_focused'
                )
            ),
            title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 200),
            changes_summary TEXT NOT NULL CHECK (length(trim(changes_summary)) > 0),
            adapted_content_markdown TEXT NOT NULL CHECK (length(trim(adapted_content_markdown)) > 0),
            prompt_contract TEXT NOT NULL CHECK (length(trim(prompt_contract)) BETWEEN 1 AND 100),
            prompt_version TEXT NOT NULL CHECK (length(trim(prompt_version)) BETWEEN 1 AND 100),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL,
            FOREIGN KEY (source_material_id) REFERENCES materials(id) ON DELETE CASCADE
        )
        """
    )

    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_material_diff_source ON material_differentiations(source_material_id);",
        "CREATE INDEX IF NOT EXISTS idx_material_diff_user ON material_differentiations(user_id, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_material_adap_source ON material_adaptations(source_material_id);",
        "CREATE INDEX IF NOT EXISTS idx_material_adap_user ON material_adaptations(user_id, created_at DESC);",
    )
    for statement in indexes:
        connection.execute(statement)

    triggers = (
        """
        CREATE TRIGGER IF NOT EXISTS trg_material_diff_owner_v19
        BEFORE INSERT ON material_differentiations
        WHEN NOT EXISTS (
            SELECT 1 FROM materials
            WHERE id = NEW.source_material_id AND user_id = NEW.user_id
              AND class_id IS NEW.class_id
        )
        BEGIN SELECT RAISE(ABORT, 'differentiation source material owner mismatch'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_material_adap_owner_v19
        BEFORE INSERT ON material_adaptations
        WHEN NOT EXISTS (
            SELECT 1 FROM materials
            WHERE id = NEW.source_material_id AND user_id = NEW.user_id
              AND class_id IS NEW.class_id
        )
        BEGIN SELECT RAISE(ABORT, 'adaptation source material owner mismatch'); END
        """,
    )
    for trigger in triggers:
        connection.execute(trigger)

    # Differentiations and adaptations are immutable derivatives. Their
    # source, tenant, and class links must never be reassigned after creation.
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_material_diff_owner_update_v19
        BEFORE UPDATE OF user_id, class_id, source_material_id ON material_differentiations
        WHEN NEW.user_id IS NOT OLD.user_id
          OR NEW.class_id IS NOT OLD.class_id
          OR NEW.source_material_id IS NOT OLD.source_material_id
        BEGIN
            SELECT RAISE(ABORT, 'differentiation source link is immutable');
        END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_material_adap_owner_update_v19
        BEFORE UPDATE OF user_id, class_id, source_material_id ON material_adaptations
        WHEN NEW.user_id IS NOT OLD.user_id
          OR NEW.class_id IS NOT OLD.class_id
          OR NEW.source_material_id IS NOT OLD.source_material_id
        BEGIN
            SELECT RAISE(ABORT, 'adaptation source link is immutable');
        END
        """
    )

    connection.execute("INSERT OR IGNORE INTO schema_versions (version) VALUES (19);")
