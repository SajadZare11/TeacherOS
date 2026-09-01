"""TeacherOS Day 24 Migration (Schema v24).

Persists UI preferences, language localization settings, and pinned class materials:
- `user_ui_preferences`: Teacher UI language (en/fa), compact mode, onboarding flag, and active class memory.
- `user_pinned_materials`: Fast favorite/pinned materials per class for immediate classroom reuse.
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 24
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def apply_schema_v24(connection: sqlite3.Connection) -> None:
    """Apply Schema v24 for UI preferences, localization, and favorites."""
    # 1. User UI Preferences table
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS user_ui_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            language_code TEXT NOT NULL DEFAULT 'en' CHECK (language_code IN ('en', 'fa')),
            compact_mode INTEGER NOT NULL DEFAULT 0 CHECK (compact_mode IN (0, 1)),
            onboarding_completed INTEGER NOT NULL DEFAULT 0 CHECK (onboarding_completed IN (0, 1)),
            last_active_class_id INTEGER,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (last_active_class_id) REFERENCES classes(id) ON DELETE SET NULL
        )
        """
    )

    # 2. Pinned materials table
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS user_pinned_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            pinned_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
            UNIQUE (user_id, class_id, material_id)
        )
        """
    )

    # 3. Indexes
    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_ui_pref_user ON user_ui_preferences(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_pinned_mat_user_class ON user_pinned_materials(user_id, class_id, pinned_at DESC);",
    )
    for statement in indexes:
        connection.execute(statement)

    # 4. Ownership triggers
    triggers = (
        """
        CREATE TRIGGER IF NOT EXISTS trg_pinned_material_owner_v24
        BEFORE INSERT ON user_pinned_materials
        WHEN NOT EXISTS (
            SELECT 1 FROM classes WHERE id = NEW.class_id AND user_id = NEW.user_id
        ) OR NOT EXISTS (
            SELECT 1 FROM materials WHERE id = NEW.material_id AND user_id = NEW.user_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'Pinned material user_id must own both class_id and material_id');
        END;
        """,
    )
    for trigger in triggers:
        connection.execute(trigger)

    # 5. Record schema version
    connection.execute("INSERT OR IGNORE INTO schema_versions (version) VALUES (24);")
