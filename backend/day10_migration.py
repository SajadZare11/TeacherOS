from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 10
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def apply_schema_v10(connection: sqlite3.Connection) -> None:
    """Persist Day 10 class-aware generation provenance and objective links."""
    additions = {
        "ai_prompt_contract": "TEXT",
        "ai_prompt_version": "TEXT",
        "ai_prompt_hash_sha256": "TEXT",
        "ai_context_hash_sha256": "TEXT",
        "ai_source_record_ids_json": "TEXT NOT NULL DEFAULT '{}'",
        "quality_scores_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    existing = _columns(connection, "materials")
    for name, definition in additions.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE materials ADD COLUMN {name} {definition}")

    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS material_objective_links (
            material_id INTEGER NOT NULL,
            objective_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            PRIMARY KEY (material_id, objective_id),
            FOREIGN KEY (material_id, user_id)
                REFERENCES materials(id, user_id) ON DELETE CASCADE,
            FOREIGN KEY (objective_id) REFERENCES class_objectives(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id, user_id)
                REFERENCES classes(id, user_id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_material_objectives_owner_class "
        "ON material_objective_links(user_id, class_id, objective_id, material_id)"
    )
    for operation in ("INSERT", "UPDATE"):
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_material_objectives_owner_{operation.lower()}
            BEFORE {operation} ON material_objective_links
            WHEN NOT EXISTS (
                    SELECT 1 FROM materials
                    WHERE id = NEW.material_id AND user_id = NEW.user_id
                      AND class_id = NEW.class_id
                )
              OR NOT EXISTS (
                    SELECT 1 FROM class_objectives
                    WHERE id = NEW.objective_id AND user_id = NEW.user_id
                      AND class_id = NEW.class_id
                )
            BEGIN SELECT RAISE(ABORT, 'ownership mismatch'); END
            """
        )

    connection.execute(
        "INSERT OR IGNORE INTO schema_versions(version, applied_at) "
        f"VALUES (?, {_UTC_NOW})",
        (SCHEMA_VERSION,),
    )
