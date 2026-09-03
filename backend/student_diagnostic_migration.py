from __future__ import annotations

import sqlite3

_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def apply_student_diagnostic_schema(connection: sqlite3.Connection) -> None:
    """Create tables for Student Profiles, Diagnostic Tracking, Assessments, and AI Recommendations."""
    connection.executescript(
        f"""
        -- 1. Students Table
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            full_name TEXT NOT NULL CHECK (length(trim(full_name)) BETWEEN 1 AND 120),
            age INTEGER CHECK (age IS NULL OR (age >= 3 AND age <= 100)),
            native_language TEXT NOT NULL DEFAULT 'Persian',
            learning_profile_json TEXT NOT NULL DEFAULT '{{}}',
            goals_json TEXT NOT NULL DEFAULT '{{}}',
            preferences_json TEXT NOT NULL DEFAULT '{{}}',
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (class_id, user_id) REFERENCES classes(id, user_id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_students_class_user ON students(class_id, user_id, status);

        -- 2. Student Skill Scores (After each lesson, scored 0-20; <10 triggers Area for Development)
        CREATE TABLE IF NOT EXISTS student_skill_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            lesson_id INTEGER,
            skill TEXT NOT NULL CHECK (skill IN (
                'listening', 'speaking', 'reading', 'writing', 'grammar', 'vocabulary', 'pronunciation'
            )),
            score REAL NOT NULL CHECK (score >= 0.0 AND score <= 20.0),
            notes TEXT,
            recorded_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
            FOREIGN KEY (lesson_id) REFERENCES class_lessons(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_skill_scores_student ON student_skill_scores(student_id, skill);

        -- 3. Student Error Profile (Examples, category, frequency, status)
        CREATE TABLE IF NOT EXISTS student_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            example_text TEXT NOT NULL CHECK (length(trim(example_text)) >= 1),
            category TEXT NOT NULL CHECK (category IN (
                'listening', 'speaking', 'reading', 'writing', 'grammar', 'vocabulary', 'pronunciation'
            )),
            frequency TEXT NOT NULL DEFAULT 'medium' CHECK (frequency IN ('low', 'medium', 'high')),
            status TEXT NOT NULL DEFAULT 'improving' CHECK (status IN ('improving', 'persistent', 'solved')),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            updated_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_errors_student ON student_errors(student_id, status);

        -- 4. Class Assessments (Formal & Informal, configured at the class level)
        CREATE TABLE IF NOT EXISTS class_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            assessment_type TEXT NOT NULL CHECK (assessment_type IN ('formal', 'informal')),
            subtype TEXT NOT NULL CHECK (subtype IN (
                'placement', 'midterm', 'final', 'ielts', 'speaking',
                'observation', 'classroom_task', 'mini_quiz', 'writing_sample'
            )),
            title TEXT NOT NULL CHECK (length(trim(title)) >= 2),
            max_score REAL NOT NULL DEFAULT 100.0 CHECK (max_score > 0),
            administered_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (class_id, user_id) REFERENCES classes(id, user_id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_class_assessments ON class_assessments(class_id, assessment_type);

        -- 5. Student Assessment Results (Individual scores for a class assessment)
        CREATE TABLE IF NOT EXISTS student_assessment_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assessment_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            score REAL CHECK (score IS NULL OR score >= 0.0),
            notes TEXT,
            recorded_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (assessment_id) REFERENCES class_assessments(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            UNIQUE(assessment_id, student_id)
        );
        CREATE INDEX IF NOT EXISTS idx_assessment_results_student ON student_assessment_results(student_id);

        -- 6. Student Engagement, Confidence & Motivation Logs
        CREATE TABLE IF NOT EXISTS student_engagement_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            lesson_id INTEGER,
            engagement_metrics_json TEXT NOT NULL DEFAULT '{{}}',
            confidence_scores_json TEXT NOT NULL DEFAULT '{{}}',
            motivation_json TEXT NOT NULL DEFAULT '{{}}',
            recorded_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
            FOREIGN KEY (lesson_id) REFERENCES class_lessons(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_engagement_student ON student_engagement_logs(student_id);

        -- 7. Student AI Next-Step Recommendations
        CREATE TABLE IF NOT EXISTS student_ai_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            recommendation_text TEXT NOT NULL,
            prompt_summary TEXT,
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ai_rec_student ON student_ai_recommendations(student_id);
        """
    )
