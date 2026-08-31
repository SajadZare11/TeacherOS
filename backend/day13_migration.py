from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 13
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def apply_schema_v13(connection: sqlite3.Connection) -> None:
    """Persist owner-scoped next-lesson recommendations and validated plans."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS next_lesson_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_uuid TEXT NOT NULL UNIQUE CHECK (length(trim(draft_uuid)) BETWEEN 8 AND 100),
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'ready' CHECK (
                status IN ('ready', 'generating', 'saved', 'ignored')
            ),
            recommended_mode TEXT NOT NULL CHECK (recommended_mode IN (
                'recommendation', 'continue_unfinished', 'reteach',
                'new_topic', 'assessment', 'manual'
            )),
            selected_mode TEXT CHECK (selected_mode IS NULL OR selected_mode IN (
                'recommendation', 'continue_unfinished', 'reteach',
                'new_topic', 'assessment', 'manual'
            )),
            priority_mode TEXT NOT NULL DEFAULT 'balanced' CHECK (
                priority_mode IN ('balanced', 'continuity', 'reteaching', 'assessment')
            ),
            rationale TEXT NOT NULL CHECK (length(trim(rationale)) BETWEEN 1 AND 2000),
            uncertainty TEXT NOT NULL CHECK (uncertainty IN ('low', 'medium', 'high')),
            uncertainty_reason TEXT NOT NULL CHECK (
                length(trim(uncertainty_reason)) BETWEEN 1 AND 1000
            ),
            teacher_request TEXT CHECK (
                teacher_request IS NULL OR length(trim(teacher_request)) BETWEEN 2 AND 1000
            ),
            duration_minutes INTEGER NOT NULL CHECK (duration_minutes BETWEEN 15 AND 180),
            objective_labels_json TEXT NOT NULL CHECK (
                json_valid(objective_labels_json) AND json_type(objective_labels_json) = 'array'
            ),
            approved_objective_ids_json TEXT NOT NULL DEFAULT '[]' CHECK (
                json_valid(approved_objective_ids_json) AND
                json_type(approved_objective_ids_json) = 'array'
            ),
            objectives_approved_at TEXT,
            input_version INTEGER NOT NULL DEFAULT 1 CHECK (input_version > 0),
            material_id INTEGER,
            last_error_code TEXT CHECK (
                last_error_code IS NULL OR length(last_error_code) BETWEEN 1 AND 100
            ),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (class_id, user_id) REFERENCES classes(id, user_id) ON DELETE CASCADE,
            FOREIGN KEY (material_id, user_id) REFERENCES materials(id, user_id) ON DELETE SET NULL,
            UNIQUE (id, class_id, user_id)
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS next_lesson_recommendation_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recommendation_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            source_type TEXT NOT NULL CHECK (source_type IN (
                'class_objective', 'class_lesson', 'lesson_outcome',
                'class_action_item', 'material'
            )),
            source_record_id INTEGER NOT NULL CHECK (source_record_id > 0),
            source_label TEXT NOT NULL CHECK (length(trim(source_label)) BETWEEN 1 AND 300),
            fact_summary TEXT NOT NULL CHECK (length(trim(fact_summary)) BETWEEN 1 AND 1000),
            included INTEGER NOT NULL DEFAULT 1 CHECK (included IN (0, 1)),
            sort_priority INTEGER NOT NULL DEFAULT 0 CHECK (sort_priority BETWEEN 0 AND 1000),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (recommendation_id, class_id, user_id)
                REFERENCES next_lesson_recommendations(id, class_id, user_id) ON DELETE CASCADE,
            UNIQUE (recommendation_id, source_type, source_record_id),
            UNIQUE (id, recommendation_id, class_id, user_id)
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS next_lesson_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recommendation_id INTEGER NOT NULL UNIQUE,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL UNIQUE,
            selected_mode TEXT NOT NULL CHECK (selected_mode IN (
                'recommendation', 'continue_unfinished', 'reteach',
                'new_topic', 'assessment', 'manual'
            )),
            duration_minutes INTEGER NOT NULL CHECK (duration_minutes BETWEEN 15 AND 180),
            timing_total_minutes INTEGER NOT NULL CHECK (timing_total_minutes BETWEEN 15 AND 180),
            objective_labels_json TEXT NOT NULL CHECK (
                json_valid(objective_labels_json) AND json_type(objective_labels_json) = 'array'
            ),
            validation_json TEXT NOT NULL CHECK (
                json_valid(validation_json) AND json_type(validation_json) = 'object'
            ),
            teacher_edit_count INTEGER NOT NULL DEFAULT 0 CHECK (teacher_edit_count >= 0),
            followup_accepted INTEGER CHECK (followup_accepted IS NULL OR followup_accepted IN (0, 1)),
            saved_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (recommendation_id, class_id, user_id)
                REFERENCES next_lesson_recommendations(id, class_id, user_id) ON DELETE RESTRICT,
            FOREIGN KEY (material_id, user_id) REFERENCES materials(id, user_id) ON DELETE RESTRICT,
            UNIQUE (id, class_id, user_id),
            CHECK (timing_total_minutes = duration_minutes)
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS next_lesson_plan_sources (
            next_lesson_plan_id INTEGER NOT NULL,
            recommendation_source_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_record_id INTEGER NOT NULL,
            source_label TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            PRIMARY KEY (next_lesson_plan_id, recommendation_source_id),
            FOREIGN KEY (next_lesson_plan_id, class_id, user_id)
                REFERENCES next_lesson_plans(id, class_id, user_id) ON DELETE CASCADE,
            FOREIGN KEY (recommendation_source_id)
                REFERENCES next_lesson_recommendation_sources(id) ON DELETE RESTRICT
        )
        """
    )

    indexes = (
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_next_lesson_one_active_v13 "
        "ON next_lesson_recommendations(user_id, class_id) "
        "WHERE status IN ('ready', 'generating')",
        "CREATE INDEX IF NOT EXISTS idx_next_lesson_owner_status_v13 "
        "ON next_lesson_recommendations(user_id, class_id, status, updated_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_next_lesson_sources_v13 "
        "ON next_lesson_recommendation_sources(recommendation_id, included DESC, sort_priority DESC, id)",
        "CREATE INDEX IF NOT EXISTS idx_next_lesson_plans_owner_v13 "
        "ON next_lesson_plans(user_id, class_id, saved_at DESC, id DESC)",
    )
    for statement in indexes:
        connection.execute(statement)

    triggers = (
        """
        CREATE TRIGGER IF NOT EXISTS trg_next_lesson_owner_insert_v13
        BEFORE INSERT ON next_lesson_recommendations
        WHEN NOT EXISTS (
            SELECT 1 FROM classes
            WHERE id = NEW.class_id AND user_id = NEW.user_id AND status = 'active'
        )
        BEGIN SELECT RAISE(ABORT, 'next lesson requires an owned active class'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_next_lesson_owner_update_v13
        BEFORE UPDATE OF class_id, user_id ON next_lesson_recommendations
        WHEN NEW.class_id != OLD.class_id OR NEW.user_id != OLD.user_id
        BEGIN SELECT RAISE(ABORT, 'next lesson ownership is immutable'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_next_lesson_saved_inputs_v13
        BEFORE UPDATE OF recommended_mode, selected_mode, priority_mode, teacher_request,
                         duration_minutes, objective_labels_json, approved_objective_ids_json
        ON next_lesson_recommendations
        WHEN OLD.status IN ('saved', 'ignored')
        BEGIN SELECT RAISE(ABORT, 'completed recommendation inputs are immutable'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_next_lesson_source_owner_insert_v13
        BEFORE INSERT ON next_lesson_recommendation_sources
        WHEN NOT EXISTS (
            SELECT 1 FROM next_lesson_recommendations
            WHERE id = NEW.recommendation_id AND class_id = NEW.class_id AND user_id = NEW.user_id
        ) OR NOT (
            (NEW.source_type = 'class_objective' AND EXISTS (
                SELECT 1 FROM class_objectives WHERE id = NEW.source_record_id
                  AND class_id = NEW.class_id AND user_id = NEW.user_id
            )) OR
            (NEW.source_type = 'class_lesson' AND EXISTS (
                SELECT 1 FROM class_lessons WHERE id = NEW.source_record_id
                  AND class_id = NEW.class_id AND user_id = NEW.user_id
            )) OR
            (NEW.source_type = 'lesson_outcome' AND EXISTS (
                SELECT 1 FROM lesson_outcomes WHERE id = NEW.source_record_id
                  AND class_id = NEW.class_id AND user_id = NEW.user_id
            )) OR
            (NEW.source_type = 'class_action_item' AND EXISTS (
                SELECT 1 FROM class_action_items WHERE id = NEW.source_record_id
                  AND class_id = NEW.class_id AND user_id = NEW.user_id
            )) OR
            (NEW.source_type = 'material' AND EXISTS (
                SELECT 1 FROM materials WHERE id = NEW.source_record_id
                  AND class_id = NEW.class_id AND user_id = NEW.user_id
            ))
        )
        BEGIN SELECT RAISE(ABORT, 'recommendation source ownership mismatch'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_next_lesson_source_frozen_v13
        BEFORE UPDATE OF included ON next_lesson_recommendation_sources
        WHEN EXISTS (
            SELECT 1 FROM next_lesson_recommendations
            WHERE id = OLD.recommendation_id AND status IN ('saved', 'ignored')
        )
        BEGIN SELECT RAISE(ABORT, 'completed recommendation sources are immutable'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_next_lesson_plan_owner_v13
        BEFORE INSERT ON next_lesson_plans
        WHEN NOT EXISTS (
            SELECT 1 FROM next_lesson_recommendations
            WHERE id = NEW.recommendation_id AND class_id = NEW.class_id AND user_id = NEW.user_id
        ) OR NOT EXISTS (
            SELECT 1 FROM materials
            WHERE id = NEW.material_id AND class_id = NEW.class_id AND user_id = NEW.user_id
              AND material_type = 'lesson'
        )
        BEGIN SELECT RAISE(ABORT, 'next lesson plan ownership mismatch'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_next_lesson_plan_links_immutable_v13
        BEFORE UPDATE OF recommendation_id, class_id, user_id, material_id,
                         selected_mode, duration_minutes, timing_total_minutes,
                         objective_labels_json
        ON next_lesson_plans
        BEGIN SELECT RAISE(ABORT, 'next lesson plan links are immutable'); END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_next_lesson_plan_source_owner_v13
        BEFORE INSERT ON next_lesson_plan_sources
        WHEN NOT EXISTS (
            SELECT 1 FROM next_lesson_plans
            WHERE id = NEW.next_lesson_plan_id AND class_id = NEW.class_id
              AND user_id = NEW.user_id
        ) OR NOT EXISTS (
            SELECT 1 FROM next_lesson_recommendation_sources
            WHERE id = NEW.recommendation_source_id AND class_id = NEW.class_id
              AND user_id = NEW.user_id AND included = 1
              AND source_type = NEW.source_type AND source_record_id = NEW.source_record_id
        )
        BEGIN SELECT RAISE(ABORT, 'next lesson plan source ownership mismatch'); END
        """,
    )
    for statement in triggers:
        connection.execute(statement)

    connection.execute(
        "INSERT OR IGNORE INTO schema_versions(version, applied_at) "
        f"VALUES (?, {_UTC_NOW})",
        (SCHEMA_VERSION,),
    )
