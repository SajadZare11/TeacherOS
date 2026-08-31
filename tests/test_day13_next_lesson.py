from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day13-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day13-key")

import class_service  # noqa: E402
import database  # noqa: E402
from class_dashboard_keyboards import (  # noqa: E402
    next_lesson_followup_keyboard,
    next_lesson_modes_keyboard,
    next_lesson_priorities_keyboard,
    next_lesson_recommendation_keyboard,
    next_lesson_sources_keyboard,
    next_lesson_why_keyboard,
)
from class_dashboard_panel import (  # noqa: E402
    get_class_dashboard_text,
    handle_dashboard_callback,
)
from class_dashboard_service import class_dashboard_snapshot  # noqa: E402
from day18_migration import SCHEMA_VERSION  # noqa: E402
from feature_flags import FEATURE_ENV_VARS  # noqa: E402
from lesson_history_service import mark_lesson_taught, schedule_material_lesson  # noqa: E402
from next_lesson_service import (  # noqa: E402
    claim_recommendation_generation,
    complete_next_lesson_plan,
    get_or_create_recommendation,
    get_recommendation,
    ignore_recommendation,
    next_lesson_metrics,
    plan_timing_total,
    record_next_lesson_edit,
    record_next_lesson_followup,
    release_recommendation_generation,
    select_recommendation_mode,
    set_manual_next_lesson_request,
    set_recommendation_priority,
    source_snapshot_hash,
    toggle_recommendation_source,
)
from outcome_checkin_service import save_outcome_facts  # noqa: E402


def teacher(identifier: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        username=f"day13_{identifier}",
        first_name="Day Thirteen",
        last_name="Teacher",
        language_code="en",
    )


def b36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = ""
    while value:
        value, remainder = divmod(value, 36)
        result = alphabet[remainder] + result
    return result or "0"


def callbacks(markup: object) -> list[str]:
    return [
        str(button.callback_data)
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


class Day13NextLessonTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="teacheros-day13-")
        self.path = Path(self.temp.name) / "teacheros.db"
        self.db_patch = patch.object(database, "DATABASE_PATH", self.path)
        self.db_patch.start()
        flags = {value: "false" for value in FEATURE_ENV_VARS.values()}
        flags[FEATURE_ENV_VARS["classes"]] = "true"
        flags[FEATURE_ENV_VARS["continuity"]] = "true"
        self.flag_patch = patch.dict(os.environ, flags, clear=False)
        self.flag_patch.start()
        self.owner = teacher(113_001)
        self.other = teacher(113_002)
        self.class_record = class_service.create_class(
            telegram_user=self.owner,
            display_name="Day 13 Class",
            level="B1",
            cadence="weekly",
            goal="Evidence to action",
        )
        assert self.class_record is not None
        with database.database_connection(self.path) as connection:
            database.ensure_database_user(connection, self.other)

    def tearDown(self) -> None:
        self.flag_patch.stop()
        self.db_patch.stop()
        self.temp.cleanup()

    def _lesson(self, title: str, *, taught: bool = True) -> dict:
        material_id = database.save_generated_material(
            telegram_user=self.owner,
            material_type="lesson",
            title=title,
            content=(
                "# Lesson overview\nTime: 60 minutes\n\n# Materials\nBoard\n\n"
                "# Procedure\n- Warm-up (Time: 10 mins)\n- Input (Time: 20 mins)\n"
                "- Practice (Time: 20 mins)\n- Wrap-up (Time: 10 mins)\n\n"
                "# Assessment\nTask\n\n# Homework\nRevise"
            ),
            class_id=int(self.class_record["id"]),
        )
        planned = schedule_material_lesson(
            telegram_user_id=self.owner.id,
            material_id=material_id,
            date_choice="today",
        )["lesson"]
        if not taught:
            return planned
        taught_lesson, changed = mark_lesson_taught(
            telegram_user_id=self.owner.id, lesson_id=int(planned["id"])
        )
        assert taught_lesson is not None and changed
        return taught_lesson

    def test_schema_v13_is_idempotent_and_owner_scoped(self) -> None:
        with database.database_connection(self.path) as connection:
            versions = [
                row[0]
                for row in connection.execute(
                    "SELECT version FROM schema_versions ORDER BY version"
                ).fetchall()
            ]
            self.assertIn(SCHEMA_VERSION, versions)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("next_lesson_recommendations", tables)
            self.assertIn("next_lesson_recommendation_sources", tables)
            self.assertIn("next_lesson_plans", tables)
            self.assertIn("next_lesson_plan_sources", tables)

    def test_new_class_has_high_uncertainty_and_new_topic_mode(self) -> None:
        rec = get_or_create_recommendation(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        self.assertIsNotNone(rec)
        self.assertEqual(rec["recommended_mode"], "new_topic")
        self.assertEqual(rec["uncertainty"], "high")
        self.assertIn("No included approved outcome records", rec["uncertainty_reason"])
        self.assertTrue(len(rec["objective_labels"]) > 0)
        self.assertEqual(len(rec["sources"]), 0)

    def test_achieved_outcome_proposes_new_topic_medium_uncertainty(self) -> None:
        lesson = self._lesson("Present Perfect Taught")
        save_outcome_facts(
            telegram_user_id=self.owner.id,
            lesson_id=int(lesson["id"]),
            result="achieved",
            difficulty_categories=["none"],
            completion_status="completed",
        )
        rec = get_or_create_recommendation(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        self.assertIsNotNone(rec)
        self.assertEqual(rec["recommended_mode"], "new_topic")
        self.assertEqual(rec["uncertainty"], "medium")
        self.assertIn("one outcome does not establish mastery", rec["rationale"].lower())

    def test_needs_reteaching_outcome_proposes_reteach_mode(self) -> None:
        lesson = self._lesson("Conditionals Taught")
        save_outcome_facts(
            telegram_user_id=self.owner.id,
            lesson_id=int(lesson["id"]),
            result="needs_reteaching",
            difficulty_categories=["language"],
            completion_status="completed",
        )
        rec = get_or_create_recommendation(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        self.assertIsNotNone(rec)
        self.assertEqual(rec["recommended_mode"], "reteach")
        self.assertIn("needs reteaching", rec["rationale"].lower())

    def test_partly_completed_outcome_proposes_continue_unfinished(self) -> None:
        lesson = self._lesson("Passive Voice Taught")
        save_outcome_facts(
            telegram_user_id=self.owner.id,
            lesson_id=int(lesson["id"]),
            result="partly_achieved",
            difficulty_categories=["pace"],
            completion_status="partly_completed",
        )
        rec = get_or_create_recommendation(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        self.assertIsNotNone(rec)
        self.assertEqual(rec["recommended_mode"], "continue_unfinished")
        self.assertIn("continue", rec["rationale"].lower())

    def test_assessment_goal_proposes_assessment_mode(self) -> None:
        exam_class = class_service.create_class(
            telegram_user=self.owner,
            display_name="IELTS Prep",
            level="B2",
            cadence="weekly",
            goal="IELTS exam preparation",
        )
        rec = get_or_create_recommendation(
            telegram_user_id=self.owner.id, class_id=int(exam_class["id"])
        )
        self.assertIsNotNone(rec)
        self.assertEqual(rec["recommended_mode"], "assessment")
        self.assertIn("assessment", rec["rationale"].lower())

    def test_priority_override_changes_recommendation(self) -> None:
        rec = get_or_create_recommendation(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        rec_id = int(rec["id"])
        prio_rec = set_recommendation_priority(
            telegram_user_id=self.owner.id,
            recommendation_id=rec_id,
            priority="continuity",
        )
        self.assertEqual(prio_rec["priority_mode"], "continuity")
        self.assertEqual(prio_rec["recommended_mode"], "continue_unfinished")

        prio_rec2 = set_recommendation_priority(
            telegram_user_id=self.owner.id,
            recommendation_id=rec_id,
            priority="reteaching",
        )
        self.assertEqual(prio_rec2["priority_mode"], "reteaching")
        self.assertEqual(prio_rec2["recommended_mode"], "reteach")

    def test_source_toggling_updates_uncertainty(self) -> None:
        lesson = self._lesson("Modal Verbs Taught")
        save_outcome_facts(
            telegram_user_id=self.owner.id,
            lesson_id=int(lesson["id"]),
            result="achieved",
            difficulty_categories=["none"],
            completion_status="completed",
        )
        rec = get_or_create_recommendation(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        self.assertEqual(rec["uncertainty"], "medium")
        outcome_source = next(
            s for s in rec["sources"] if s["source_type"] == "lesson_outcome"
        )
        toggled = toggle_recommendation_source(
            telegram_user_id=self.owner.id,
            source_link_id=int(outcome_source["id"]),
        )
        self.assertIsNotNone(toggled)
        self.assertEqual(toggled["uncertainty"], "high")

    def test_manual_mode_and_topic_validation(self) -> None:
        rec = get_or_create_recommendation(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        rec_id = int(rec["id"])
        updated = set_manual_next_lesson_request(
            telegram_user_id=self.owner.id,
            recommendation_id=rec_id,
            request="Job Interviews and Professional Introductions",
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["selected_mode"], "manual")
        self.assertEqual(
            updated["teacher_request"],
            "Job Interviews and Professional Introductions",
        )

        with self.assertRaises(ValueError):
            set_manual_next_lesson_request(
                telegram_user_id=self.owner.id,
                recommendation_id=rec_id,
                request="Call me at +12345678901 for questions",
            )
        with self.assertRaises(ValueError):
            set_manual_next_lesson_request(
                telegram_user_id=self.owner.id,
                recommendation_id=rec_id,
                request="Email test@example.com",
            )

    def test_plan_generation_lifecycle_and_timing_verification(self) -> None:
        rec = get_or_create_recommendation(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        rec_id = int(rec["id"])
        select_recommendation_mode(
            telegram_user_id=self.owner.id,
            recommendation_id=rec_id,
            mode="recommendation",
        )
        claimed = claim_recommendation_generation(
            telegram_user_id=self.owner.id, recommendation_id=rec_id
        )
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["status"], "generating")

        content = (
            "# Lesson Overview\nTime: 60 minutes\n\n# Materials\nHandouts\n\n"
            "# Procedure\n- Retrieval (Time: 10 mins)\n- Input (Time: 20 mins)\n"
            "- Practice (Time: 20 mins)\n- Assessment (Time: 10 mins)\n\n"
            "# Assessment\nTask\n\n# Homework\nRevise"
        )
        total = plan_timing_total(content)
        self.assertEqual(total, 60)

        material_id = database.save_generated_material(
            telegram_user=self.owner,
            material_type="lesson",
            title="Generated Next Lesson",
            content=content,
            class_id=int(self.class_record["id"]),
        )
        plan = complete_next_lesson_plan(
            telegram_user_id=self.owner.id,
            recommendation_id=rec_id,
            material_id=material_id,
            validation={"timing": 100, "overall": 100},
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan["timing_total_minutes"], 60)
        self.assertEqual(plan["duration_minutes"], 60)

        completed_rec = get_recommendation(
            telegram_user_id=self.owner.id, recommendation_id=rec_id
        )
        self.assertEqual(completed_rec["status"], "saved")

    def test_teacher_edits_and_followup_metrics(self) -> None:
        rec = get_or_create_recommendation(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        rec_id = int(rec["id"])
        select_recommendation_mode(
            telegram_user_id=self.owner.id,
            recommendation_id=rec_id,
            mode="new_topic",
        )
        claim_recommendation_generation(
            telegram_user_id=self.owner.id, recommendation_id=rec_id
        )
        content = "# Overview\nTime: 60 mins\n\n# Procedure\n- Act (Time: 60 mins)"
        material_id = database.save_generated_material(
            telegram_user=self.owner,
            material_type="lesson",
            title="Next Lesson Plan",
            content=content,
            class_id=int(self.class_record["id"]),
        )
        plan = complete_next_lesson_plan(
            telegram_user_id=self.owner.id,
            recommendation_id=rec_id,
            material_id=material_id,
            validation={"overall": 100},
        )
        plan_id = int(plan["id"])

        self.assertTrue(
            record_next_lesson_edit(
                telegram_user_id=self.owner.id, plan_id=plan_id
            )
        )
        self.assertTrue(
            record_next_lesson_followup(
                telegram_user_id=self.owner.id, plan_id=plan_id, accepted=True
            )
        )

        metrics = next_lesson_metrics()
        self.assertGreaterEqual(metrics["plans_saved"], 1)
        self.assertGreaterEqual(metrics["teacher_edits"], 1)
        self.assertGreaterEqual(metrics["followup_accepted"], 1)
        self.assertEqual(metrics["quality_definition"], "use_not_generation_count")

    def test_multi_tenant_isolation_guards(self) -> None:
        lesson = self._lesson("Reported Speech")
        save_outcome_facts(
            telegram_user_id=self.owner.id,
            lesson_id=int(lesson["id"]),
            result="achieved",
            difficulty_categories=["none"],
            completion_status="completed",
        )
        rec = get_or_create_recommendation(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        rec_id = int(rec["id"])
        self.assertTrue(len(rec["sources"]) > 0)
        source_id = int(rec["sources"][0]["id"])

        # User B cannot read, modify, toggle, or generate User A's recommendation
        self.assertIsNone(
            get_recommendation(
                telegram_user_id=self.other.id, recommendation_id=rec_id
            )
        )
        self.assertIsNone(
            select_recommendation_mode(
                telegram_user_id=self.other.id,
                recommendation_id=rec_id,
                mode="reteach",
            )
        )
        self.assertIsNone(
            toggle_recommendation_source(
                telegram_user_id=self.other.id, source_link_id=source_id
            )
        )
        self.assertIsNone(
            claim_recommendation_generation(
                telegram_user_id=self.other.id, recommendation_id=rec_id
            )
        )
        self.assertFalse(
            ignore_recommendation(
                telegram_user_id=self.other.id, recommendation_id=rec_id
            )
        )

    async def test_dashboard_callbacks_and_navigation(self) -> None:
        class_id = int(self.class_record["id"])
        revision = int(self.class_record["revision"])

        query = AsyncMock()
        query.data = f"v1|cl|plan|{b36(class_id)}|{b36(revision)}"
        update = SimpleNamespace(callback_query=query, effective_user=self.owner)
        context = SimpleNamespace(user_data={})

        await handle_dashboard_callback(
            update,
            context,
            action="plan",
            object_id=b36(class_id),
            revision_text=b36(revision),
        )
        query.edit_message_text.assert_called_once()
        text = query.edit_message_text.call_args[0][0]
        self.assertIn("Plan Next Lesson", text)

        rec = get_or_create_recommendation(
            telegram_user_id=self.owner.id, class_id=class_id
        )
        rec_id = int(rec["id"])

        # Test why callback
        query.reset_mock()
        await handle_dashboard_callback(
            update,
            context,
            action="nlwhy",
            object_id=b36(rec_id),
            revision_text=b36(revision),
        )
        query.edit_message_text.assert_called_once()
        self.assertIn("Why this next?", query.edit_message_text.call_args[0][0])

        # Test mode selection callback
        query.reset_mock()
        await handle_dashboard_callback(
            update,
            context,
            action="nlmset",
            object_id=f"t{b36(rec_id)}",
            revision_text=b36(revision),
        )
        query.edit_message_text.assert_called_once()
        self.assertIn("Mode set to Reteach", query.edit_message_text.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
