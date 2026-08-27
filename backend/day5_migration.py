from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 6
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def _column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _add_material_class_column(connection: sqlite3.Connection) -> None:
    if "class_id" not in _column_names(connection, "materials"):
        connection.execute(
            "ALTER TABLE materials ADD COLUMN class_id INTEGER "
            "REFERENCES classes(id) ON DELETE SET NULL"
        )


def apply_schema_v6(connection: sqlite3.Connection) -> None:
    """Apply the additive Day 5 class-memory schema, safely and repeatedly."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            display_name TEXT NOT NULL CHECK (length(trim(display_name)) BETWEEN 1 AND 120),
            level TEXT CHECK (
                level IS NULL OR level IN ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')
            ),
            age_group TEXT CHECK (
                age_group IS NULL OR age_group IN (
                    'young_learners', 'teens', 'adults', 'mixed'
                )
            ),
            learner_count_band TEXT CHECK (
                learner_count_band IS NULL OR learner_count_band IN (
                    'one_to_one', '2_5', '6_12', '13_20', '21_plus'
                )
            ),
            cadence TEXT CHECK (
                cadence IS NULL OR cadence IN (
                    'ad_hoc', 'weekly', 'twice_weekly', 'three_plus_weekly'
                )
            ),
            goal TEXT,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            archived_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE (id, user_id)
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS class_objectives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            objective TEXT NOT NULL CHECK (length(trim(objective)) BETWEEN 1 AND 1000),
            status TEXT NOT NULL DEFAULT 'current' CHECK (
                status IN ('current', 'met', 'paused', 'archived')
            ),
            priority INTEGER NOT NULL DEFAULT 0 CHECK (priority BETWEEN 0 AND 100),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (class_id, user_id) REFERENCES classes(id, user_id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS class_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            material_id INTEGER,
            title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 200),
            status TEXT NOT NULL DEFAULT 'draft' CHECK (
                status IN ('draft', 'planned', 'taught', 'cancelled', 'archived')
            ),
            scheduled_for TEXT,
            taught_at TEXT,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (class_id, user_id) REFERENCES classes(id, user_id) ON DELETE CASCADE,
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE SET NULL,
            UNIQUE (id, class_id, user_id)
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS lesson_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_lesson_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            result TEXT NOT NULL CHECK (
                result IN ('not_assessed', 'not_met', 'partly_met', 'met', 'exceeded')
            ),
            confidence TEXT CHECK (
                confidence IS NULL OR confidence IN ('low', 'medium', 'high')
            ),
            support_needed TEXT CHECK (
                support_needed IS NULL OR support_needed IN ('none', 'some', 'substantial')
            ),
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (
                status IN ('draft', 'saved', 'approved', 'archived')
            ),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (class_lesson_id, class_id, user_id)
                REFERENCES class_lessons(id, class_id, user_id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS product_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_uuid TEXT NOT NULL UNIQUE CHECK (length(trim(event_uuid)) BETWEEN 8 AND 100),
            user_id INTEGER NOT NULL,
            class_id INTEGER,
            class_lesson_id INTEGER,
            material_id INTEGER,
            event_name TEXT NOT NULL CHECK (length(trim(event_name)) BETWEEN 1 AND 100),
            privacy_class TEXT NOT NULL DEFAULT 'operational' CHECK (
                privacy_class IN ('operational', 'product', 'support', 'sensitive')
            ),
            properties_json TEXT NOT NULL DEFAULT '{{}}',
            delivery_status TEXT NOT NULL DEFAULT 'pending' CHECK (
                delivery_status IN ('pending', 'delivered', 'failed')
            ),
            occurred_at TEXT NOT NULL,
            received_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL,
            FOREIGN KEY (class_lesson_id) REFERENCES class_lessons(id) ON DELETE SET NULL,
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE SET NULL
        )
        """
    )

    _add_material_class_column(connection)

    indexes = (
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_materials_id_user ON materials(id, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_materials_user_class_created ON materials(user_id, class_id, created_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_classes_user_status_updated ON classes(user_id, status, updated_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_objectives_owner_class_status ON class_objectives(user_id, class_id, status, priority DESC, id)",
        "CREATE INDEX IF NOT EXISTS idx_lessons_owner_class_status ON class_lessons(user_id, class_id, status, scheduled_for, id)",
        "CREATE INDEX IF NOT EXISTS idx_outcomes_owner_class_lesson ON lesson_outcomes(user_id, class_id, class_lesson_id, status, id)",
        "CREATE INDEX IF NOT EXISTS idx_product_events_owner_occurred ON product_events(user_id, occurred_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_product_events_owner_class ON product_events(user_id, class_id, event_name, occurred_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_product_events_delivery ON product_events(delivery_status, received_at, id)",
    )
    for statement in indexes:
        connection.execute(statement)

    triggers = (
        """
        CREATE TRIGGER IF NOT EXISTS trg_materials_class_owner_insert
        BEFORE INSERT ON materials
        WHEN NEW.class_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM classes WHERE id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT, 'ownership mismatch'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_materials_class_owner_update
        BEFORE UPDATE OF class_id, user_id ON materials
        WHEN NEW.class_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM classes WHERE id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT, 'ownership mismatch'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_lessons_material_owner_insert
        BEFORE INSERT ON class_lessons
        WHEN NEW.material_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM materials WHERE id = NEW.material_id AND user_id = NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT, 'ownership mismatch'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_lessons_material_owner_update
        BEFORE UPDATE OF material_id, user_id ON class_lessons
        WHEN NEW.material_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM materials WHERE id = NEW.material_id AND user_id = NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT, 'ownership mismatch'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_product_events_owner_insert
        BEFORE INSERT ON product_events
        WHEN (NEW.class_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM classes WHERE id = NEW.class_id AND user_id = NEW.user_id
              ))
          OR (NEW.class_lesson_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM class_lessons WHERE id = NEW.class_lesson_id AND user_id = NEW.user_id
              ))
          OR (NEW.material_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM materials WHERE id = NEW.material_id AND user_id = NEW.user_id
              ))
        BEGIN SELECT RAISE(ABORT, 'ownership mismatch'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_product_events_owner_update
        BEFORE UPDATE OF user_id, class_id, class_lesson_id, material_id ON product_events
        WHEN (NEW.class_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM classes WHERE id = NEW.class_id AND user_id = NEW.user_id
              ))
          OR (NEW.class_lesson_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM class_lessons WHERE id = NEW.class_lesson_id AND user_id = NEW.user_id
              ))
          OR (NEW.material_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM materials WHERE id = NEW.material_id AND user_id = NEW.user_id
              ))
        BEGIN SELECT RAISE(ABORT, 'ownership mismatch'); END
        """,
    )
    for statement in triggers:
        connection.execute(statement)

    connection.execute(
        "INSERT OR IGNORE INTO schema_versions(version, applied_at) "
        f"VALUES (?, {_UTC_NOW})",
        (SCHEMA_VERSION,),
    )
