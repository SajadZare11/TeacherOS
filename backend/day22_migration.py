"""TeacherOS Day 22 Migration (Schema v22).

Persists CEFR curriculum alignment and communicative discipline:
- `class_curriculum_units`: Lightweight coursebook & unit tracker (no copyrighted text scraping).
- `cefr_objective_mappings`: Maps objectives to CEFR communicative modes & competence categories.
- `golden_curriculum_evaluations`: Evaluator calibration records on golden lesson set.
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 22
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def apply_schema_v22(connection: sqlite3.Connection) -> None:
    """Apply Schema v22 for CEFR curriculum discipline and unit alignment."""
    # 1. Class curriculum units (lightweight coursebook / unit tracking)
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS class_curriculum_units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            unit_number TEXT NOT NULL DEFAULT '1' CHECK (length(trim(unit_number)) BETWEEN 1 AND 30),
            unit_title TEXT NOT NULL CHECK (length(trim(unit_title)) BETWEEN 1 AND 200),
            coursebook_name TEXT CHECK (coursebook_name IS NULL OR length(trim(coursebook_name)) BETWEEN 1 AND 150),
            exam_syllabus_target TEXT CHECK (exam_syllabus_target IS NULL OR length(trim(exam_syllabus_target)) BETWEEN 1 AND 150),
            curriculum_notes TEXT,
            status TEXT NOT NULL DEFAULT 'current' CHECK (status IN ('planned', 'current', 'completed', 'skipped')),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        )
        """
    )

    # 2. CEFR objective mappings (reception, production, interaction, mediation)
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS cefr_objective_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            objective_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            cefr_level TEXT NOT NULL CHECK (cefr_level IN ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')),
            communicative_mode TEXT NOT NULL CHECK (
                communicative_mode IN (
                    'reception_reading', 'reception_listening',
                    'production_speaking', 'production_writing',
                    'interaction_spoken', 'interaction_written',
                    'mediation'
                )
            ),
            competence_category TEXT NOT NULL CHECK (
                competence_category IN (
                    'linguistic_grammar', 'linguistic_vocabulary', 'linguistic_phonology',
                    'sociolinguistic', 'pragmatic_functional'
                )
            ),
            can_do_statement TEXT NOT NULL CHECK (length(trim(can_do_statement)) BETWEEN 5 AND 1000),
            coverage_status TEXT NOT NULL DEFAULT 'not_covered' CHECK (
                coverage_status IN ('not_covered', 'partly_covered', 'covered', 'secure')
            ),
            teacher_overridden INTEGER NOT NULL DEFAULT 0 CHECK (teacher_overridden IN (0, 1)),
            uncertainty_note TEXT,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (objective_id) REFERENCES class_objectives(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        )
        """
    )

    # 3. Golden set curriculum evaluations (experienced teacher calibration)
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS golden_curriculum_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER,
            evaluator_name TEXT NOT NULL CHECK (length(trim(evaluator_name)) BETWEEN 1 AND 100),
            can_do_clarity_pass INTEGER NOT NULL CHECK (can_do_clarity_pass IN (0, 1)),
            task_authenticity_pass INTEGER NOT NULL CHECK (task_authenticity_pass IN (0, 1)),
            assessment_alignment_pass INTEGER NOT NULL CHECK (assessment_alignment_pass IN (0, 1)),
            scaffolding_pass INTEGER NOT NULL CHECK (scaffolding_pass IN (0, 1)),
            overall_pass INTEGER NOT NULL CHECK (overall_pass IN (0, 1)),
            disagreement_notes TEXT,
            evaluated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE SET NULL
        )
        """
    )

    # 4. Indexes
    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_curr_units_class_status ON class_curriculum_units(class_id, status, updated_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_curr_units_user ON class_curriculum_units(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_cefr_map_obj ON cefr_objective_mappings(objective_id);",
        "CREATE INDEX IF NOT EXISTS idx_cefr_map_class_mode ON cefr_objective_mappings(class_id, communicative_mode, coverage_status);",
        "CREATE INDEX IF NOT EXISTS idx_cefr_map_user ON cefr_objective_mappings(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_golden_eval_mat ON golden_curriculum_evaluations(material_id);",
    )
    for statement in indexes:
        connection.execute(statement)

    # 5. Ownership triggers
    triggers = (
        """
        CREATE TRIGGER IF NOT EXISTS trg_curriculum_unit_owner_v22
        BEFORE INSERT ON class_curriculum_units
        WHEN NOT EXISTS (
            SELECT 1 FROM classes WHERE id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'Curriculum unit user_id does not own class_id');
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_cefr_mapping_owner_v22
        BEFORE INSERT ON cefr_objective_mappings
        WHEN NOT EXISTS (
            SELECT 1 FROM classes WHERE id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'CEFR mapping user_id does not own class_id');
        END;
        """,
    )
    for trigger in triggers:
        connection.execute(trigger)

    # 6. Record schema version
    connection.execute("INSERT OR IGNORE INTO schema_versions (version) VALUES (22);")
