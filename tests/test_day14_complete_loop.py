from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day14-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day14-key")

import database
from class_dashboard_panel import set_class_archived
from class_dashboard_service import class_dashboard_snapshot
from class_service import archive_class
from complete_loop_service import (
    evaluate_phase2_ai_golden_set,
    execute_complete_loop,
    simulate_recovery_scenarios,
    verify_multi_tenant_isolation,
)
from lesson_history_service import list_lesson_history
from next_lesson_service import (
    get_or_create_recommendation,
    get_recommendation,
    plan_timing_total,
)
from outcome_checkin_service import get_lesson_outcome
from pdf_document import create_pdf_export
from prompt_contracts import get_prompt_contract
from validators import validate_model_response
from word_document import create_word_export


def _teacher(identifier: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        username=f"day14_user_{identifier}",
        first_name="Teacher",
        last_name=f"Fourteen_{identifier}",
        language_code="en",
    )


class Day14CompleteLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day14-test-")
        self.db_path = Path(self.temp_dir.name) / "teacheros.db"
        database.DATABASE_PATH = self.db_path
        database.initialize_database(self.db_path)

        self.env_patch = {
            "TEACHEROS_FEATURE_CLASSES": "true",
            "TEACHEROS_FEATURE_CONTINUITY": "true",
            "TEACHEROS_FEATURE_EVIDENCE": "true",
            "TEACHEROS_FEATURE_REPORTS": "true",
        }
        self.original_env = {}
        for key, val in self.env_patch.items():
            self.original_env[key] = os.environ.get(key)
            os.environ[key] = val

        self.teacher_a = _teacher(999_141)
        self.teacher_b = _teacher(999_142)

    def tearDown(self) -> None:
        for key, val in self.original_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        self.temp_dir.cleanup()

    def test_full_continuous_teaching_loop_e2e(self) -> None:
        res = execute_complete_loop(
            telegram_user=self.teacher_a,
            class_name="Advanced C1 Debate",
            cefr_level="C1",
            goal="Advanced argumentative speaking",
            lesson_duration_minutes=60,
            database_path=self.db_path,
        )
        self.assertTrue(res["passed"])
        self.assertIsNotNone(res["class_id"])
        self.assertIsNotNone(res["first_material_id"])
        self.assertIsNotNone(res["first_lesson_id"])
        self.assertIsNotNone(res["outcome_id"])
        self.assertIsNotNone(res["recommendation_id"])
        self.assertIsNotNone(res["next_plan_id"])
        self.assertEqual(res["timing_total_minutes"], 60)
        self.assertEqual(res["duration_minutes"], 60)
        self.assertTrue(res["timing_valid"])
        self.assertGreaterEqual(res["plan_source_count"], 1)
        self.assertEqual(res["followup_accepted"], 1)

    def test_resilience_and_restart_recovery(self) -> None:
        recovery = simulate_recovery_scenarios(
            telegram_user=self.teacher_a, database_path=self.db_path
        )
        self.assertTrue(recovery["setup_draft_resumption"])
        self.assertTrue(recovery["generation_interruption_recovery"])
        self.assertTrue(recovery["all_recovery_passed"])

    def test_multi_tenant_isolation_across_loop_stages(self) -> None:
        isolation = verify_multi_tenant_isolation(
            teacher_a=self.teacher_a,
            teacher_b=self.teacher_b,
            database_path=self.db_path,
        )
        self.assertTrue(isolation["dashboard_cross_access_blocked"])
        self.assertTrue(isolation["recommendation_cross_access_blocked"])
        self.assertTrue(isolation["history_cross_access_blocked"])
        self.assertTrue(isolation["outcome_cross_access_blocked"])
        self.assertTrue(isolation["all_isolation_passed"])

    def test_ai_quality_golden_eval_and_worst_10_inspection(self) -> None:
        eval_result = evaluate_phase2_ai_golden_set(mode="fixture")
        self.assertTrue(eval_result["passed"])
        self.assertEqual(eval_result["total_cases"], 40)
        self.assertEqual(eval_result["passed_cases"], 40)
        self.assertEqual(eval_result["safety_invariant_failures"], 0)
        self.assertFalse(eval_result["release_blocked"])
        self.assertEqual(len(eval_result["worst_10_inspection"]), 10)
        for inspection in eval_result["worst_10_inspection"]:
            self.assertTrue(inspection["passed"])
            self.assertTrue(inspection["safety_valid"])
            self.assertTrue(inspection["schema_valid"])

    def test_four_generators_regression_quick_and_class_modes(self) -> None:
        res = execute_complete_loop(
            telegram_user=self.teacher_a,
            class_name="General English B1",
            cefr_level="B1",
            database_path=self.db_path,
        )
        class_id = res["class_id"]

        generators = ("lesson", "activity", "worksheet", "assessment")
        for gen in generators:
            contract = get_prompt_contract(gen)
            self.assertIsNotNone(contract)

            # Quick mode
            quick_content = f"# Overview\nQuick test for {gen}\n" + ("\n- Step (Time: 10 mins)" if gen == "lesson" else "\n# Content\nItems")
            # Class mode
            class_content = f"# Overview\nClass-aware test for {gen} in class #{class_id}\n" + ("\n- Step (Time: 10 mins)" if gen == "lesson" else "\n# Content\nItems")

            quick_mat_id = database.save_generated_material(
                telegram_user=self.teacher_a,
                material_type=gen,
                title=f"Quick {gen}",
                content=quick_content,
                class_id=None,
            )
            class_mat_id = database.save_generated_material(
                telegram_user=self.teacher_a,
                material_type=gen,
                title=f"Class {gen}",
                content=class_content,
                class_id=class_id,
            )
            self.assertGreater(quick_mat_id, 0)
            self.assertGreater(class_mat_id, 0)

    def test_export_word_and_pdf_generation(self) -> None:
        content = (
            "# Lesson Overview\n"
            "Level: B2 | Time: 60 mins\n\n"
            "# Can-Do Objectives\n"
            "- Students can discuss travel experiences.\n\n"
            "# Procedure\n"
            "- Warm-up: Quick photo check (Time: 10 mins)\n"
            "- Main task: Paired storytelling (Time: 50 mins)"
        )
        material = {
            "id": 1,
            "title": "Export Test Lesson",
            "material_type": "lesson",
            "content": content,
            "created_at": "2026-08-31T20:00:00.000000Z",
        }
        docx_stream, docx_name = create_word_export(material)
        pdf_stream, pdf_name = create_pdf_export(material)
        self.assertGreater(len(docx_stream.getvalue()), 100)
        self.assertGreater(len(pdf_stream.getvalue()), 100)

    def test_archive_and_restore_preserves_full_loop_history(self) -> None:
        res = execute_complete_loop(
            telegram_user=self.teacher_a,
            class_name="Archive Restore Verification",
            cefr_level="A2",
            database_path=self.db_path,
        )
        class_id = res["class_id"]

        # Archive class
        archived = archive_class(
            telegram_user_id=self.teacher_a.id, class_id=class_id, database_path=self.db_path
        )
        self.assertTrue(archived)

        dash_archived = class_dashboard_snapshot(
            telegram_user_id=self.teacher_a.id, class_id=class_id, database_path=self.db_path
        )
        self.assertEqual(dash_archived["class"]["status"], "archived")

        # Restore class
        archived_rev = int(dash_archived["class"]["revision"])
        restored = set_class_archived(
            telegram_user_id=self.teacher_a.id,
            class_id=class_id,
            archive=False,
            expected_revision=archived_rev,
            database_path=self.db_path,
        )
        self.assertIsNotNone(restored)

        dash_restored = class_dashboard_snapshot(
            telegram_user_id=self.teacher_a.id, class_id=class_id, database_path=self.db_path
        )
        self.assertEqual(dash_restored["class"]["status"], "active")

        # Verify history, outcome, recommendations still exist
        history = list_lesson_history(
            telegram_user_id=self.teacher_a.id, class_id=class_id, database_path=self.db_path
        )
        self.assertGreaterEqual(len(history), 1)
        outcome = get_lesson_outcome(
            telegram_user_id=self.teacher_a.id,
            lesson_id=res["first_lesson_id"],
            database_path=self.db_path,
        )
        self.assertIsNotNone(outcome)
        rec = get_recommendation(
            telegram_user_id=self.teacher_a.id,
            recommendation_id=res["recommendation_id"],
            database_path=self.db_path,
        )
        self.assertIsNotNone(rec)


if __name__ == "__main__":
    unittest.main()
