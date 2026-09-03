from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import class_service
import database
from student_diagnostic_service import (
    create_student,
    get_student,
    list_students_by_class,
    update_student_identity,
    update_learning_profile,
    update_student_goals,
    update_student_preferences,
    record_skill_score,
    get_student_strengths,
    get_student_areas_for_development,
    add_student_error,
    list_student_errors,
    update_error_status,
    create_class_assessment,
    list_class_assessments,
    record_student_assessment_result,
    get_student_assessment_results,
    get_student_longitudinal_progress,
    log_student_engagement,
    get_latest_engagement_and_confidence,
    construct_student_ai_context,
    save_student_recommendation,
    get_latest_student_recommendation,
)


from types import SimpleNamespace
from feature_flags import FEATURE_ENV_VARS


class TestStudentDiagnostics(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="teacheros-student-")
        self.db_path = Path(self.temp.name) / "teacheros.db"
        self.db_patch = patch.object(database, "DATABASE_PATH", self.db_path)
        self.db_patch.start()
        database.initialize_database()

        self.user_id = 999_888
        self.flag_patch = patch.dict(os.environ, {FEATURE_ENV_VARS["classes"]: "true"})
        self.flag_patch.start()

        # Ensure user exists
        with database.database_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (telegram_user_id, first_name) VALUES (?, ?)",
                (self.user_id, "Teacher Reza"),
            )
        # Create a test class
        self.cls = class_service.create_class(
            telegram_user=SimpleNamespace(id=self.user_id),
            display_name="Class Adults B1",
            level="B1",
        )
        self.class_id = int(self.cls["id"])

    def tearDown(self) -> None:
        self.flag_patch.stop()
        self.db_patch.stop()
        self.temp.cleanup()

    def test_section_1_student_identity(self) -> None:
        # Create student
        st = create_student(
            telegram_user_id=self.user_id,
            class_id=self.class_id,
            full_name="Ali Rezaei",
            age=26,
            native_language="Persian",
        )
        self.assertEqual(st["full_name"], "Ali Rezaei")
        self.assertEqual(st["age"], 26)
        self.assertEqual(st["native_language"], "Persian")

        # Update identity
        updated = update_student_identity(
            telegram_user_id=self.user_id,
            student_id=st["id"],
            full_name="Ali Rezaei (Updated)",
            age=27,
            native_language="Azeri",
        )
        self.assertEqual(updated["full_name"], "Ali Rezaei (Updated)")
        self.assertEqual(updated["age"], 27)
        self.assertEqual(updated["native_language"], "Azeri")

    def test_section_2_learning_profile(self) -> None:
        st = create_student(self.user_id, self.class_id, "Sara")
        updated = update_learning_profile(
            self.user_id, st["id"], skill="speaking", cefr="B2", confidence="low"
        )
        self.assertIsNotNone(updated)
        fetched = get_student(self.user_id, st["id"])
        self.assertIn('"speaking": {"cefr": "B2", "confidence": "low"}', fetched["learning_profile_json"])

    def test_section_3_goals(self) -> None:
        st = create_student(self.user_id, self.class_id, "Sara")
        updated = update_student_goals(
            self.user_id,
            st["id"],
            long_term_goals=["IELTS 7.0+", "Study Abroad"],
            short_term_goal="10 minutes conversation without switching to Persian",
        )
        self.assertIsNotNone(updated)
        fetched = get_student(self.user_id, st["id"])
        self.assertIn("IELTS 7.0+", fetched["goals_json"])
        self.assertIn("10 minutes conversation without switching to Persian", fetched["goals_json"])

    def test_section_4_preferences_and_behavior(self) -> None:
        st = create_student(self.user_id, self.class_id, "Sara")
        updated = update_student_preferences(
            self.user_id,
            st["id"],
            preferred_activities=["pair work", "role play", "video"],
            learning_behaviors=["participates actively", "responds well to visual support"],
        )
        self.assertIsNotNone(updated)
        fetched = get_student(self.user_id, st["id"])
        self.assertIn("pair work", fetched["preferences_json"])
        self.assertIn("responds well to visual support", fetched["preferences_json"])

    def test_sections_5_and_6_strengths_and_areas_for_development(self) -> None:
        st = create_student(self.user_id, self.class_id, "Mehdi")
        # Session 1: Speaking 16, Listening 8 (below 10, note required)
        record_skill_score(self.user_id, st["id"], "speaking", 16.0)
        record_skill_score(self.user_id, st["id"], "listening", 8.0, notes="Struggles with connected speech / contractions")

        # Score below 10 without note must raise error
        with self.assertRaises(ValueError):
            record_skill_score(self.user_id, st["id"], "grammar", 7.0, notes="")

        # Session 2: Speaking 18
        record_skill_score(self.user_id, st["id"], "speaking", 18.0)

        # Verify Section 5: Strengths mean score
        strengths = get_student_strengths(self.user_id, st["id"])
        self.assertEqual(strengths["speaking"], 17.0)  # (16 + 18) / 2
        self.assertEqual(strengths["listening"], 8.0)

        # Verify Section 6: Areas for development
        areas = get_student_areas_for_development(self.user_id, st["id"])
        self.assertEqual(len(areas), 1)
        self.assertEqual(areas[0]["skill"], "listening")
        self.assertIn("Struggles with connected speech", areas[0]["notes"])

    def test_section_7_error_profile(self) -> None:
        st = create_student(self.user_id, self.class_id, "Neda")
        err = add_student_error(
            self.user_id,
            st["id"],
            example_text="She don't likes coffee.",
            category="grammar",
            frequency="high",
            status="persistent",
        )
        self.assertEqual(err["status"], "persistent")
        self.assertEqual(err["frequency"], "high")

        # Update status
        updated_err = update_error_status(self.user_id, err["id"], "improving")
        self.assertEqual(updated_err["status"], "improving")

        all_errs = list_student_errors(self.user_id, st["id"])
        self.assertEqual(len(all_errs), 1)

    def test_section_8_class_assessments_and_student_results(self) -> None:
        # Class-level setup
        midterm = create_class_assessment(
            self.user_id, self.class_id, "formal", "midterm", "Midterm Exam Units 1-5", max_score=100.0
        )
        speaking = create_class_assessment(
            self.user_id, self.class_id, "informal", "classroom_task", "Speaking Role Play", max_score=20.0
        )
        self.assertEqual(len(list_class_assessments(self.user_id, self.class_id)), 2)

        # Student scoring
        st = create_student(self.user_id, self.class_id, "Neda")
        res = record_student_assessment_result(
            self.user_id, midterm["id"], st["id"], score=88.5, notes="Great reading comprehension"
        )
        self.assertEqual(res["score"], 88.5)

        student_results = get_student_assessment_results(self.user_id, st["id"])
        self.assertEqual(len(student_results), 1)
        self.assertEqual(student_results[0]["assessment_title"], "Midterm Exam Units 1-5")

    def test_section_9_skill_progress(self) -> None:
        st = create_student(self.user_id, self.class_id, "Farhad")
        record_skill_score(self.user_id, st["id"], "reading", 14.0)
        record_skill_score(self.user_id, st["id"], "reading", 17.0)
        progress = get_student_longitudinal_progress(self.user_id, st["id"])
        self.assertEqual(len(progress["skill_history"]), 2)

    def test_section_10_engagement_confidence_motivation(self) -> None:
        st = create_student(self.user_id, self.class_id, "Farhad")
        eng = {
            "attendance": "present",
            "punctuality": "on_time",
            "participation": "high",
            "homework_completion": "full",
            "risk_taking": "moderate",
        }
        conf = {"speaking": 3, "listening": 4, "reading": 5}
        mot = {
            "current_motivation": "high",
            "primary_motivation": "job_promotion",
            "goal_commitment": "strong",
        }
        log_student_engagement(self.user_id, st["id"], eng, conf, mot)
        latest = get_latest_engagement_and_confidence(self.user_id, st["id"])
        self.assertEqual(latest["engagement"]["participation"], "high")
        self.assertEqual(latest["confidence"]["reading"], 5)
        self.assertEqual(latest["motivation"]["primary_motivation"], "job_promotion")

    def test_section_11_ai_context_and_recommendation(self) -> None:
        st = create_student(self.user_id, self.class_id, "Farhad")
        record_skill_score(self.user_id, st["id"], "speaking", 9.0, notes="Frequent self-correction pauses")
        ctx = construct_student_ai_context(self.user_id, st["id"])
        self.assertEqual(ctx["student"]["full_name"], "Farhad")
        self.assertEqual(len(ctx["areas_for_dev"]), 1)

        saved = save_student_recommendation(
            self.user_id, st["id"], "Focus on fluency drills before accuracy corrections in next session."
        )
        self.assertIn("fluency drills", saved["recommendation_text"])

        latest_rec = get_latest_student_recommendation(self.user_id, st["id"])
        self.assertEqual(latest_rec["recommendation_text"], saved["recommendation_text"])


if __name__ == "__main__":
    unittest.main()
