from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping
from database import database_connection

SKILLS = ["listening", "speaking", "reading", "writing", "grammar", "vocabulary", "pronunciation"]

SKILL_LABELS_EN = {
    "listening": "Listening",
    "speaking": "Speaking",
    "reading": "Reading",
    "writing": "Writing",
    "grammar": "Grammar",
    "vocabulary": "Vocabulary",
    "pronunciation": "Pronunciation",
}

SKILL_LABELS_FA = {
    "listening": "شنیداری (Listening)",
    "speaking": "گفتاری (Speaking)",
    "reading": "درک مطلب (Reading)",
    "writing": "نگارش (Writing)",
    "grammar": "گرامر (Grammar)",
    "vocabulary": "واژگان (Vocabulary)",
    "pronunciation": "تلفظ (Pronunciation)",
}

CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
CONFIDENCE_LEVELS = ["low", "medium", "high"]

LONG_TERM_GOALS = [
    "IELTS 7.0+",
    "Study Abroad",
    "Job Promotion",
    "Academic English",
    "Immigration",
    "General English",
    "Travel",
    "Speaking Fluency",
]

PREFERRED_ACTIVITIES = [
    "pair work",
    "role play",
    "discussion",
    "games",
    "reading",
    "writing",
    "video",
    "listening",
    "projects",
    "grammar exercises",
]

LEARNING_BEHAVIORS = [
    "participates actively",
    "needs prompting",
    "prefers preparation time",
    "learns well through examples",
    "responds well to visual support",
    "benefits from repetition",
    "benefits from explicit grammar explanation",
]

FORMAL_ASSESSMENTS = ["placement", "midterm", "final", "ielts", "speaking"]
INFORMAL_ASSESSMENTS = ["observation", "classroom_task", "mini_quiz", "writing_sample"]

ENGAGEMENT_VARIABLES = [
    "attendance",
    "punctuality",
    "participation",
    "homework_completion",
    "preparation",
    "engagement",
    "confidence",
    "risk_taking",
    "peer_interaction",
]

MOTIVATION_DIMENSIONS = [
    "current_motivation",
    "primary_motivation",
    "attendance_motivation",
    "goal_commitment",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _get_user_id(connection: Any, telegram_user_id: int) -> int:
    row = connection.execute(
        "SELECT id FROM users WHERE telegram_user_id = ?", (telegram_user_id,)
    ).fetchone()
    if row is None:
        raise ValueError("User not found.")
    return int(row["id"])


# ---------------------------------------------------------------------------
# Section 1 & Core Student CRUD
# ---------------------------------------------------------------------------

def create_student(
    telegram_user_id: int,
    class_id: int,
    full_name: str,
    age: int | None = None,
    native_language: str = "Persian",
) -> dict[str, Any]:
    name_clean = full_name.strip()
    if not (1 <= len(name_clean) <= 120):
        raise ValueError("Student name must be between 1 and 120 characters.")
    if age is not None and not (3 <= age <= 100):
        raise ValueError("Student age must be between 3 and 100.")

    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        # Check class ownership
        class_row = conn.execute(
            "SELECT id FROM classes WHERE id = ? AND user_id = ? AND status = 'active'",
            (class_id, user_id),
        ).fetchone()
        if class_row is None:
            raise ValueError("Class not found or access denied.")

        cursor = conn.execute(
            """
            INSERT INTO students (class_id, user_id, full_name, age, native_language)
            VALUES (?, ?, ?, ?, ?)
            """,
            (class_id, user_id, name_clean, age, native_language.strip() or "Persian"),
        )
        student_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        return dict(row)


def get_student(telegram_user_id: int, student_id: int) -> dict[str, Any] | None:
    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        row = conn.execute(
            """
            SELECT s.*, c.display_name AS class_name
            FROM students s
            JOIN classes c ON c.id = s.class_id
            WHERE s.id = ? AND s.user_id = ? AND s.status = 'active'
            """,
            (student_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def list_students_by_class(telegram_user_id: int, class_id: int) -> list[dict[str, Any]]:
    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        rows = conn.execute(
            """
            SELECT * FROM students
            WHERE class_id = ? AND user_id = ? AND status = 'active'
            ORDER BY full_name ASC, id ASC
            """,
            (class_id, user_id),
        ).fetchall()
        return [dict(r) for r in rows]


def update_student_identity(
    telegram_user_id: int,
    student_id: int,
    full_name: str,
    age: int | None = None,
    native_language: str = "Persian",
) -> dict[str, Any] | None:
    name_clean = full_name.strip()
    if not (1 <= len(name_clean) <= 120):
        raise ValueError("Student name must be between 1 and 120 characters.")
    if age is not None and not (3 <= age <= 100):
        raise ValueError("Student age must be between 3 and 100.")

    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        conn.execute(
            """
            UPDATE students
            SET full_name = ?, age = ?, native_language = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (name_clean, age, native_language.strip() or "Persian", _utc_now(), student_id, user_id),
        )
        row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Section 2: Learning Profile (7 Skills: CEFR & Confidence)
# ---------------------------------------------------------------------------

def update_learning_profile(
    telegram_user_id: int,
    student_id: int,
    skill: str,
    cefr: str,
    confidence: str,
) -> dict[str, Any] | None:
    skill_clean = skill.strip().lower()
    if skill_clean not in SKILLS:
        raise ValueError(f"Invalid skill: {skill}")
    cefr_clean = cefr.strip().upper()
    if cefr_clean not in CEFR_LEVELS:
        raise ValueError(f"Invalid CEFR level: {cefr}")
    conf_clean = confidence.strip().lower()
    if conf_clean not in CONFIDENCE_LEVELS:
        raise ValueError(f"Invalid confidence level: {confidence}")

    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        row = conn.execute(
            "SELECT learning_profile_json FROM students WHERE id = ? AND user_id = ?",
            (student_id, user_id),
        ).fetchone()
        if row is None:
            return None
        profile = json.loads(row["learning_profile_json"] or "{}")
        profile[skill_clean] = {"cefr": cefr_clean, "confidence": conf_clean}
        conn.execute(
            "UPDATE students SET learning_profile_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(profile), _utc_now(), student_id),
        )
        updated = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        return dict(updated) if updated else None


# ---------------------------------------------------------------------------
# Section 3: Goals (Long-term & Short-term)
# ---------------------------------------------------------------------------

def update_student_goals(
    telegram_user_id: int,
    student_id: int,
    long_term_goals: list[str],
    short_term_goal: str,
) -> dict[str, Any] | None:
    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        goals_payload = {
            "long_term": [str(g).strip() for g in long_term_goals if str(g).strip()],
            "short_term": str(short_term_goal).strip(),
        }
        conn.execute(
            "UPDATE students SET goals_json = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (json.dumps(goals_payload), _utc_now(), student_id, user_id),
        )
        row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Section 4: Learning Preferences & Learning Behavior
# ---------------------------------------------------------------------------

def update_student_preferences(
    telegram_user_id: int,
    student_id: int,
    preferred_activities: list[str],
    learning_behaviors: list[str],
) -> dict[str, Any] | None:
    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        pref_payload = {
            "preferred_activities": [str(a).strip() for a in preferred_activities if str(a).strip()],
            "learning_behaviors": [str(b).strip() for b in learning_behaviors if str(b).strip()],
        }
        conn.execute(
            "UPDATE students SET preferences_json = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (json.dumps(pref_payload), _utc_now(), student_id, user_id),
        )
        row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Section 5 (Strengths) & Section 6 (Areas for Development)
# ---------------------------------------------------------------------------

def record_skill_score(
    telegram_user_id: int,
    student_id: int,
    skill: str,
    score: float,
    notes: str | None = None,
    lesson_id: int | None = None,
) -> dict[str, Any]:
    skill_clean = skill.strip().lower()
    if skill_clean not in SKILLS:
        raise ValueError(f"Invalid skill: {skill}")
    if not (0.0 <= score <= 20.0):
        raise ValueError("Score must be between 0 and 20.")
    if score < 10.0 and not (notes and notes.strip()):
        raise ValueError("For scores below 10, an explanatory diagnostic note is required.")

    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        student = conn.execute(
            "SELECT class_id FROM students WHERE id = ? AND user_id = ?",
            (student_id, user_id),
        ).fetchone()
        if student is None:
            raise ValueError("Student not found.")

        cursor = conn.execute(
            """
            INSERT INTO student_skill_scores (student_id, class_id, lesson_id, skill, score, notes, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, int(student["class_id"]), lesson_id, skill_clean, score, notes, _utc_now()),
        )
        row = conn.execute("SELECT * FROM student_skill_scores WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)


def get_student_strengths(telegram_user_id: int, student_id: int) -> dict[str, float]:
    """Computes the mean score (0-20) for each skill across all sessions."""
    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        rows = conn.execute(
            """
            SELECT s.skill, AVG(s.score) as mean_score, COUNT(s.id) as score_count
            FROM student_skill_scores s
            JOIN students st ON st.id = s.student_id
            WHERE s.student_id = ? AND st.user_id = ?
            GROUP BY s.skill
            """,
            (student_id, user_id),
        ).fetchall()
        return {str(r["skill"]): round(float(r["mean_score"]), 1) for r in rows}


def get_student_areas_for_development(telegram_user_id: int, student_id: int) -> list[dict[str, Any]]:
    """Returns all session score entries below 10 with teacher diagnostic notes."""
    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        rows = conn.execute(
            """
            SELECT s.*
            FROM student_skill_scores s
            JOIN students st ON st.id = s.student_id
            WHERE s.student_id = ? AND st.user_id = ? AND s.score < 10.0
            ORDER BY s.recorded_at DESC
            """,
            (student_id, user_id),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Section 7: Error Profile (Example, Category, Frequency, Status)
# ---------------------------------------------------------------------------

def add_student_error(
    telegram_user_id: int,
    student_id: int,
    example_text: str,
    category: str,
    frequency: str = "medium",
    status: str = "improving",
) -> dict[str, Any]:
    cat_clean = category.strip().lower()
    if cat_clean not in SKILLS:
        raise ValueError(f"Invalid category: {category}")
    freq_clean = frequency.strip().lower()
    if freq_clean not in {"low", "medium", "high"}:
        raise ValueError(f"Invalid frequency: {frequency}")
    stat_clean = status.strip().lower()
    if stat_clean not in {"improving", "persistent", "solved"}:
        raise ValueError(f"Invalid status: {status}")
    ex_clean = example_text.strip()
    if not ex_clean:
        raise ValueError("Error example cannot be empty.")

    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        student = conn.execute(
            "SELECT class_id FROM students WHERE id = ? AND user_id = ?",
            (student_id, user_id),
        ).fetchone()
        if student is None:
            raise ValueError("Student not found.")

        cursor = conn.execute(
            """
            INSERT INTO student_errors (student_id, class_id, example_text, category, frequency, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (student_id, int(student["class_id"]), ex_clean, cat_clean, freq_clean, stat_clean),
        )
        row = conn.execute("SELECT * FROM student_errors WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)


def list_student_errors(
    telegram_user_id: int, student_id: int, status: str | None = None
) -> list[dict[str, Any]]:
    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        if status:
            rows = conn.execute(
                """
                SELECT e.* FROM student_errors e
                JOIN students st ON st.id = e.student_id
                WHERE e.student_id = ? AND st.user_id = ? AND e.status = ?
                ORDER BY e.created_at DESC
                """,
                (student_id, user_id, status.strip().lower()),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT e.* FROM student_errors e
                JOIN students st ON st.id = e.student_id
                WHERE e.student_id = ? AND st.user_id = ?
                ORDER BY e.created_at DESC
                """,
                (student_id, user_id),
            ).fetchall()
        return [dict(r) for r in rows]


def update_error_status(
    telegram_user_id: int, error_id: int, new_status: str
) -> dict[str, Any] | None:
    stat_clean = new_status.strip().lower()
    if stat_clean not in {"improving", "persistent", "solved"}:
        raise ValueError(f"Invalid status: {new_status}")

    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        conn.execute(
            """
            UPDATE student_errors
            SET status = ?, updated_at = ?
            WHERE id = ? AND student_id IN (SELECT id FROM students WHERE user_id = ?)
            """,
            (stat_clean, _utc_now(), error_id, user_id),
        )
        row = conn.execute("SELECT * FROM student_errors WHERE id = ?", (error_id,)).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Section 8: Class Assessments (Formal & Informal) and Student Results
# ---------------------------------------------------------------------------

def create_class_assessment(
    telegram_user_id: int,
    class_id: int,
    assessment_type: str,
    subtype: str,
    title: str,
    max_score: float = 100.0,
) -> dict[str, Any]:
    type_clean = assessment_type.strip().lower()
    if type_clean not in {"formal", "informal"}:
        raise ValueError("Assessment type must be 'formal' or 'informal'.")
    sub_clean = subtype.strip().lower()
    valid_subtypes = set(FORMAL_ASSESSMENTS) if type_clean == "formal" else set(INFORMAL_ASSESSMENTS)
    if sub_clean not in valid_subtypes:
        raise ValueError(f"Invalid subtype '{subtype}' for assessment type '{type_clean}'.")
    title_clean = title.strip()
    if len(title_clean) < 2:
        raise ValueError("Title must be at least 2 characters.")

    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        cursor = conn.execute(
            """
            INSERT INTO class_assessments (class_id, user_id, assessment_type, subtype, title, max_score)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (class_id, user_id, type_clean, sub_clean, title_clean, max_score),
        )
        row = conn.execute("SELECT * FROM class_assessments WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)


def list_class_assessments(telegram_user_id: int, class_id: int) -> list[dict[str, Any]]:
    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        rows = conn.execute(
            """
            SELECT * FROM class_assessments
            WHERE class_id = ? AND user_id = ?
            ORDER BY created_at DESC
            """,
            (class_id, user_id),
        ).fetchall()
        return [dict(r) for r in rows]


def record_student_assessment_result(
    telegram_user_id: int,
    assessment_id: int,
    student_id: int,
    score: float,
    notes: str | None = None,
) -> dict[str, Any]:
    if score < 0:
        raise ValueError("Score cannot be negative.")

    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        # Verify assessment & student belong to user
        assess = conn.execute(
            "SELECT * FROM class_assessments WHERE id = ? AND user_id = ?",
            (assessment_id, user_id),
        ).fetchone()
        if assess is None:
            raise ValueError("Assessment not found.")

        conn.execute(
            """
            INSERT INTO student_assessment_results (assessment_id, student_id, score, notes, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(assessment_id, student_id) DO UPDATE SET
                score = excluded.score,
                notes = excluded.notes,
                recorded_at = excluded.recorded_at
            """,
            (assessment_id, student_id, score, notes, _utc_now()),
        )
        row = conn.execute(
            "SELECT * FROM student_assessment_results WHERE assessment_id = ? AND student_id = ?",
            (assessment_id, student_id),
        ).fetchone()
        return dict(row)


def get_student_assessment_results(telegram_user_id: int, student_id: int) -> list[dict[str, Any]]:
    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        rows = conn.execute(
            """
            SELECT r.*, a.title AS assessment_title, a.assessment_type, a.subtype, a.max_score
            FROM student_assessment_results r
            JOIN class_assessments a ON a.id = r.assessment_id
            JOIN students st ON st.id = r.student_id
            WHERE r.student_id = ? AND st.user_id = ?
            ORDER BY r.recorded_at DESC
            """,
            (student_id, user_id),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Section 9: Longitudinal Skill Progress
# ---------------------------------------------------------------------------

def get_student_longitudinal_progress(telegram_user_id: int, student_id: int) -> dict[str, Any]:
    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        student = conn.execute(
            "SELECT * FROM students WHERE id = ? AND user_id = ?",
            (student_id, user_id),
        ).fetchone()
        if student is None:
            raise ValueError("Student not found.")

        scores = conn.execute(
            """
            SELECT skill, score, recorded_at
            FROM student_skill_scores
            WHERE student_id = ?
            ORDER BY recorded_at ASC
            """,
            (student_id,),
        ).fetchall()

        assessments = conn.execute(
            """
            SELECT r.score, a.max_score, a.title, r.recorded_at
            FROM student_assessment_results r
            JOIN class_assessments a ON a.id = r.assessment_id
            WHERE r.student_id = ?
            ORDER BY r.recorded_at ASC
            """,
            (student_id,),
        ).fetchall()

        return {
            "learning_profile": json.loads(student["learning_profile_json"] or "{}"),
            "skill_history": [dict(s) for s in scores],
            "assessment_history": [dict(a) for a in assessments],
        }


# ---------------------------------------------------------------------------
# Section 10: Engagement & Confidence / Motivation
# ---------------------------------------------------------------------------

def log_student_engagement(
    telegram_user_id: int,
    student_id: int,
    engagement_metrics: Mapping[str, str],
    confidence_scores: Mapping[str, int],
    motivation: Mapping[str, str],
    lesson_id: int | None = None,
) -> dict[str, Any]:
    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        student = conn.execute(
            "SELECT class_id FROM students WHERE id = ? AND user_id = ?",
            (student_id, user_id),
        ).fetchone()
        if student is None:
            raise ValueError("Student not found.")

        cursor = conn.execute(
            """
            INSERT INTO student_engagement_logs (
                student_id, class_id, lesson_id, engagement_metrics_json,
                confidence_scores_json, motivation_json, recorded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                student_id,
                int(student["class_id"]),
                lesson_id,
                json.dumps(dict(engagement_metrics)),
                json.dumps(dict(confidence_scores)),
                json.dumps(dict(motivation)),
                _utc_now(),
            ),
        )
        row = conn.execute("SELECT * FROM student_engagement_logs WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)


def get_latest_engagement_and_confidence(telegram_user_id: int, student_id: int) -> dict[str, Any] | None:
    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        row = conn.execute(
            """
            SELECT l.* FROM student_engagement_logs l
            JOIN students st ON st.id = l.student_id
            WHERE l.student_id = ? AND st.user_id = ?
            ORDER BY l.recorded_at DESC LIMIT 1
            """,
            (student_id, user_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "engagement": json.loads(row["engagement_metrics_json"] or "{}"),
            "confidence": json.loads(row["confidence_scores_json"] or "{}"),
            "motivation": json.loads(row["motivation_json"] or "{}"),
            "recorded_at": row["recorded_at"],
        }


# ---------------------------------------------------------------------------
# Section 11: Next Step Recommendation (AI Synthesis)
# ---------------------------------------------------------------------------

def construct_student_ai_context(telegram_user_id: int, student_id: int) -> dict[str, Any]:
    student = get_student(telegram_user_id, student_id)
    if not student:
        raise ValueError("Student not found.")

    strengths = get_student_strengths(telegram_user_id, student_id)
    areas_for_dev = get_student_areas_for_development(telegram_user_id, student_id)
    errors = list_student_errors(telegram_user_id, student_id)
    assessments = get_student_assessment_results(telegram_user_id, student_id)
    engagement = get_latest_engagement_and_confidence(telegram_user_id, student_id)

    profile = json.loads(student.get("learning_profile_json") or "{}")
    goals = json.loads(student.get("goals_json") or "{}")
    preferences = json.loads(student.get("preferences_json") or "{}")

    return {
        "student": student,
        "profile": profile,
        "goals": goals,
        "preferences": preferences,
        "strengths": strengths,
        "areas_for_dev": areas_for_dev[:5],
        "active_errors": [e for e in errors if e["status"] != "solved"][:5],
        "assessments": assessments[:5],
        "engagement": engagement,
    }


def save_student_recommendation(
    telegram_user_id: int, student_id: int, recommendation_text: str
) -> dict[str, Any]:
    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        student = conn.execute(
            "SELECT class_id FROM students WHERE id = ? AND user_id = ?",
            (student_id, user_id),
        ).fetchone()
        if not student:
            raise ValueError("Student not found.")

        cursor = conn.execute(
            """
            INSERT INTO student_ai_recommendations (student_id, class_id, recommendation_text, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (student_id, int(student["class_id"]), recommendation_text, _utc_now()),
        )
        row = conn.execute(
            "SELECT * FROM student_ai_recommendations WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def get_latest_student_recommendation(
    telegram_user_id: int, student_id: int
) -> dict[str, Any] | None:
    with database_connection() as conn:
        user_id = _get_user_id(conn, telegram_user_id)
        row = conn.execute(
            """
            SELECT r.* FROM student_ai_recommendations r
            JOIN students st ON st.id = r.student_id
            WHERE r.student_id = ? AND st.user_id = ?
            ORDER BY r.created_at DESC LIMIT 1
            """,
            (student_id, user_id),
        ).fetchone()
        return dict(row) if row else None
