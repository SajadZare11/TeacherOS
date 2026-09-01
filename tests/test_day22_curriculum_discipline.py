"""Tests for TeacherOS Day 22 CEFR Curriculum Discipline & Communicative Pedagogy."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day22-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day22-key")

import database
from cefr_curriculum_validator import (
    evaluate_lesson_curriculum_discipline,
    validate_can_do_wording,
    validate_check_for_learning,
    validate_communicative_outcome,
    validate_scaffolding,
)
from class_service import create_class
from curriculum_discipline_service import (
    get_class_curriculum_coverage,
    get_current_curriculum_unit,
    get_golden_set_calibration_metrics,
    list_curriculum_units,
    map_objective_to_cefr,
    override_cefr_mapping,
    record_golden_set_calibration,
    save_curriculum_unit,
)
from curriculum_keyboards import (
    cefr_coverage_keyboard,
    cefr_mapping_detail_keyboard,
    curriculum_home_keyboard,
    mode_picker_keyboard,
    unit_editor_cancel_keyboard,
)
from curriculum_panel import handle_curriculum_callback, handle_curriculum_message
from day27_migration import SCHEMA_VERSION
from feature_flags import FEATURE_ENV_VARS


class Day22CurriculumDisciplineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day22-test-")
        self.db_path = Path(self.temp_dir.name) / "teacheros.db"
        database.initialize_database(self.db_path)

        self.flags_patcher = patch.dict(
            os.environ,
            {
                FEATURE_ENV_VARS["classes"]: "true",
                FEATURE_ENV_VARS["continuity"]: "true",
            },
        )
        self.flags_patcher.start()

        self.orig_db_path = database.DATABASE_PATH
        database.DATABASE_PATH = self.db_path

        self.teacher_a = SimpleNamespace(
            id=220_101,
            username="teacher_a",
            first_name="Alice",
            last_name="Teacher",
            language_code="en",
        )
        self.teacher_b = SimpleNamespace(
            id=220_102,
            username="teacher_b",
            first_name="Bob",
            last_name="Teacher",
            language_code="en",
        )

        with database.database_connection(self.db_path) as conn:
            self.user_a_id = database.ensure_database_user(conn, self.teacher_a)
            self.user_b_id = database.ensure_database_user(conn, self.teacher_b)

        self.class_a = create_class(
            telegram_user=self.teacher_a,
            display_name="C1 Professional Writing & Speaking",
            level="C1",
            age_group="adults",
            learner_count_band="6_12",
            goal="Executive reports and stakeholder negotiations",
            database_path=self.db_path,
        )
        self.class_a_id = int(self.class_a["id"])

    def tearDown(self) -> None:
        database.DATABASE_PATH = self.orig_db_path
        self.flags_patcher.stop()
        self.temp_dir.cleanup()

    def test_schema_v22_initialized(self) -> None:
        """Verify schema version 22 and table creation."""
        with database.database_connection(self.db_path) as conn:
            ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
            self.assertGreaterEqual(ver, 22)
            t1 = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='class_curriculum_units'"
            ).fetchone()
            t2 = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='cefr_objective_mappings'"
            ).fetchone()
            t3 = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='golden_curriculum_evaluations'"
            ).fetchone()
            self.assertIsNotNone(t1)
            self.assertIsNotNone(t2)
            self.assertIsNotNone(t3)

    def test_coursebook_unit_lifecycle_and_profile_sync(self) -> None:
        """Verify adding units, demoting prior current unit, and syncing coursebook to class profile."""
        unit1 = save_curriculum_unit(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            unit_number="1",
            unit_title="Managing Global Teams",
            coursebook_name="Business Partner C1",
            exam_syllabus_target="Cambridge BEC Higher",
            curriculum_notes="Focus on indirect speech in performance reviews",
            status="current",
            database_path=self.db_path,
        )
        self.assertIsNotNone(unit1)
        self.assertEqual(unit1["unit_title"], "Managing Global Teams")

        # Save Unit 2 as current (should demote Unit 1)
        unit2 = save_curriculum_unit(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            unit_number="2",
            unit_title="Crisis Management & PR",
            coursebook_name="Business Partner C1",
            status="current",
            database_path=self.db_path,
        )
        self.assertIsNotNone(unit2)

        active = get_current_curriculum_unit(
            user_id=self.user_a_id, class_id=self.class_a_id, database_path=self.db_path
        )
        self.assertEqual(active["id"], unit2["id"])

        all_units = list_curriculum_units(
            user_id=self.user_a_id, class_id=self.class_a_id, database_path=self.db_path
        )
        self.assertEqual(len(all_units), 2)
        self.assertEqual(all_units[0]["status"], "completed")

    def test_cefr_objective_mapping_and_teacher_override(self) -> None:
        """Verify mapping objective to CEFR communicative mode and teacher override."""
        with database.database_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO class_objectives (class_id, user_id, objective, status, priority)
                VALUES (?, ?, 'Draft executive summaries using concise passive phrasing', 'current', 10)
                """,
                (self.class_a_id, self.user_a_id),
            )
            obj_id = cursor.lastrowid

        mapping = map_objective_to_cefr(
            user_id=self.user_a_id,
            objective_id=obj_id,
            class_id=self.class_a_id,
            cefr_level="C1",
            communicative_mode="production_writing",
            competence_category="linguistic_grammar",
            can_do_statement="Can write clear, smoothly flowing summaries of complex reports.",
            coverage_status="covered",
            database_path=self.db_path,
        )
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping["teacher_overridden"], 0)

        # Teacher overrides mode to written interaction
        overridden = override_cefr_mapping(
            user_id=self.user_a_id,
            mapping_id=mapping["id"],
            communicative_mode="interaction_written",
            teacher_note="Teacher shifted focus to email correspondence with clients",
            database_path=self.db_path,
        )
        self.assertEqual(overridden["teacher_overridden"], 1)
        self.assertEqual(overridden["communicative_mode"], "interaction_written")

    def test_cefr_coverage_summary(self) -> None:
        """Verify covered, partly covered, and mode distribution aggregation."""
        with database.database_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO class_objectives (class_id, user_id, objective, status, priority)
                VALUES (?, ?, 'Negotiate contract terms', 'current', 10)
                """,
                (self.class_a_id, self.user_a_id),
            )
            obj_id = cursor.lastrowid

        map_objective_to_cefr(
            user_id=self.user_a_id,
            objective_id=obj_id,
            class_id=self.class_a_id,
            cefr_level="C1",
            communicative_mode="interaction_spoken",
            competence_category="pragmatic_functional",
            can_do_statement="Can negotiate terms persuasively in real-time meetings.",
            coverage_status="partly_covered",
            database_path=self.db_path,
        )

        cov = get_class_curriculum_coverage(
            user_id=self.user_a_id, class_id=self.class_a_id, database_path=self.db_path
        )
        self.assertEqual(cov["total_mapped_objectives"], 1)
        self.assertEqual(cov["partly_covered_count"], 1)
        self.assertEqual(cov["communicative_mode_distribution"]["interaction_spoken"], 1)

    def test_communicative_validators(self) -> None:
        """Verify can-do wording, communicative outcomes, scaffolding, and check for learning."""
        # 1. Observable action verbs vs. vague statements
        can_do_pass, _ = validate_can_do_wording("Students can negotiate a compromise and explain trade-offs.")
        self.assertTrue(can_do_pass)

        vague_fail, _ = validate_can_do_wording("Students will learn about the history of trade and know the topic.")
        self.assertFalse(vague_fail)

        # 2. Flagship communicative lesson evaluation
        flagship_plan = (
            "Title: Executive Negotiations\n"
            "Level: C1 · 60 minutes\n\n"
            "Objectives:\n"
            "- Students can describe and negotiate win-win trade-offs.\n\n"
            "Staging:\n"
            "- Warm-up (10 mins): Elicit negotiation tactics.\n"
            "- Controlled practice (15 mins): Matching phrases with hedging.\n"
            "- Roleplay Simulation (25 mins): In pairs, resolve contract disagreement.\n"
            "- Check for Learning (10 mins): Peer assessment rubric and exit ticket CCQs.\n\n"
            "Pronunciation: Intonation in polite counter-proposals."
        )
        eval_flagship = evaluate_lesson_curriculum_discipline(flagship_plan, level="C1", duration_minutes=60)
        self.assertTrue(eval_flagship.passed)
        self.assertGreaterEqual(eval_flagship.overall_score, 80)

        # 3. Generic topical plan rejection
        generic_plan = (
            "Topic: General Conversation about Travel\n"
            "We will talk about travel and learn about cities.\n"
            "Students will practice English together for 60 minutes."
        )
        eval_generic = evaluate_lesson_curriculum_discipline(generic_plan, level="B1", duration_minutes=60)
        self.assertFalse(eval_generic.passed)
        self.assertIn("communicative_outcome", eval_generic.missing_criteria)

    def test_golden_set_calibration_metrics(self) -> None:
        """Verify evaluator calibration pass rate calculations."""
        record_golden_set_calibration(
            material_id=None,
            evaluator_name="DELTA Lead Trainer 1",
            can_do_clarity_pass=True,
            task_authenticity_pass=True,
            assessment_alignment_pass=True,
            scaffolding_pass=True,
            database_path=self.db_path,
        )
        record_golden_set_calibration(
            material_id=None,
            evaluator_name="DELTA Lead Trainer 2",
            can_do_clarity_pass=True,
            task_authenticity_pass=True,
            assessment_alignment_pass=True,
            scaffolding_pass=True,
            database_path=self.db_path,
        )
        metrics = get_golden_set_calibration_metrics(database_path=self.db_path)
        self.assertEqual(metrics["total_evaluations"], 2)
        self.assertEqual(metrics["evaluator_count"], 2)
        self.assertEqual(metrics["overall_pass_rate_percent"], 100.0)
        self.assertTrue(metrics["meets_85_percent_gate"])

    def test_multi_tenant_isolation(self) -> None:
        """Verify Teacher B cannot view, modify, or insert into Teacher A's curriculum data."""
        unit = save_curriculum_unit(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            unit_title="Secret Class A Unit",
            database_path=self.db_path,
        )
        self.assertIsNone(get_current_curriculum_unit(user_id=self.user_b_id, class_id=self.class_a_id, database_path=self.db_path))

        with self.assertRaises(Exception):
            save_curriculum_unit(
                user_id=self.user_b_id,
                class_id=self.class_a_id,
                unit_title="Hacked unit",
                database_path=self.db_path,
            )

    def test_telegram_keyboards_bounded_64_bytes(self) -> None:
        """Verify all curriculum inline keyboards strictly respect 64-byte limits."""
        keyboards = [
            curriculum_home_keyboard(self.class_a_id, 1, has_unit=True),
            curriculum_home_keyboard(self.class_a_id, 1, has_unit=False),
            cefr_coverage_keyboard(self.class_a_id, 1, [], "all"),
            cefr_mapping_detail_keyboard(101, self.class_a_id, 1),
            mode_picker_keyboard(101, self.class_a_id, 1),
            unit_editor_cancel_keyboard(self.class_a_id, 1),
        ]

        for kb in keyboards:
            for row in kb.inline_keyboard:
                for btn in row:
                    cb_data = btn.callback_data
                    if cb_data:
                        self.assertLessEqual(
                            len(cb_data.encode("utf-8")),
                            64,
                            f"Callback data exceeds 64 bytes: {cb_data}",
                        )

    async def test_panel_callbacks_and_text_input(self) -> None:
        """Verify Telegram panel callbacks for curriculum home, editing, and CEFR mode switching."""
        update = MagicMock()
        update.effective_user = self.teacher_a
        update.callback_query = MagicMock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        # 1. Curriculum Home callback
        update.callback_query.data = f"v1|cu|home|{self.class_a_id:x}|1"
        await handle_curriculum_callback(update, context)
        update.callback_query.edit_message_text.assert_awaited()
        call_text = update.callback_query.edit_message_text.call_args[0][0]
        self.assertIn("Curriculum & CEFR Alignment", call_text)

        # 2. Start unit edit callback
        update.callback_query.data = f"v1|cu|uedit|{self.class_a_id:x}|1"
        await handle_curriculum_callback(update, context)
        self.assertEqual(context.user_data["curriculum_edit"]["state"], "unit_text")

        # 3. Submit unit text via MessageHandler
        update.message.text = "4 | Cross-Cultural Communication | Cambridge Touchstone 4 | Focus on idioms"
        await handle_curriculum_message(update, context)
        update.message.reply_text.assert_awaited()
        msg_text = update.message.reply_text.call_args[0][0]
        self.assertIn("Active Coursebook Unit Saved", msg_text)
        self.assertIn("Cross-Cultural Communication", msg_text)


if __name__ == "__main__":
    unittest.main()
