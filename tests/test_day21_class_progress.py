"""Tests for TeacherOS Day 21 Evidence-Linked Class Progress."""
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
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day21-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day21-key")

import database
from class_progress_keyboards import (
    health_card_keyboard,
    objective_detail_keyboard,
    objective_status_picker_keyboard,
    objectives_list_keyboard,
    progress_overview_keyboard,
    proposed_objective_review_keyboard,
    proposed_objectives_keyboard,
    timeline_browser_keyboard,
)
from class_progress_panel import handle_progress_callback
from class_progress_service import (
    approve_proposed_objective,
    get_class_health_card,
    get_class_progress_overview,
    get_objective_detail_with_sources,
    handle_deleted_source,
    link_objective_evidence,
    list_class_objectives,
    list_pending_proposed_objectives,
    propose_objective,
    reject_proposed_objective,
    update_objective_status,
)
from class_service import create_class
from day22_migration import apply_schema_v22
from day25_migration import SCHEMA_VERSION
from feature_flags import FEATURE_ENV_VARS


class Day21ClassProgressTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day21-test-")
        self.db_path = Path(self.temp_dir.name) / "teacheros.db"
        database.initialize_database(self.db_path)

        self.flags_patcher = patch.dict(
            os.environ,
            {
                FEATURE_ENV_VARS["classes"]: "true",
                FEATURE_ENV_VARS["continuity"]: "true",
                FEATURE_ENV_VARS["evidence"]: "true",
            },
        )
        self.flags_patcher.start()

        self.orig_db_path = database.DATABASE_PATH
        database.DATABASE_PATH = self.db_path

        self.teacher_a = SimpleNamespace(
            id=210_101,
            username="teacher_a",
            first_name="Alice",
            last_name="Teacher",
            language_code="en",
        )
        self.teacher_b = SimpleNamespace(
            id=210_102,
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
            display_name="B2 Spoken Communication",
            level="B2",
            age_group="adults",
            learner_count_band="6_12",
            goal="Fluency and discourse management",
            database_path=self.db_path,
        )
        self.class_a_id = int(self.class_a["id"])

    def tearDown(self) -> None:
        database.DATABASE_PATH = self.orig_db_path
        self.flags_patcher.stop()
        self.temp_dir.cleanup()

    def test_schema_v21_initialized(self) -> None:
        """Verify schema version 21 and table creation."""
        with database.database_connection(self.db_path) as conn:
            ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
            self.assertGreaterEqual(ver, 21)
            t1 = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='proposed_class_objectives'"
            ).fetchone()
            t2 = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='objective_evidence_links'"
            ).fetchone()
            self.assertIsNotNone(t1)
            self.assertIsNotNone(t2)

    def test_proposed_objective_extraction_and_teacher_approval_gate(self) -> None:
        """Verify proposed objectives require explicit teacher approval to enter active context."""
        # 1. Propose 2 objectives
        prop1 = propose_objective(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            objective_text="Express opinions tentatively with modal hedges",
            source_type="lesson",
            source_id=101,
            category="functional_language",
            proposed_status="current",
            rationale="Extracted from speaking lesson plan",
            database_path=self.db_path,
        )
        prop2 = propose_objective(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            objective_text="Correct subject-verb agreement in complex noun phrases",
            source_type="evidence_analysis",
            source_id=201,
            category="grammar",
            proposed_status="needs_support",
            rationale="Identified in writing analysis",
            database_path=self.db_path,
        )

        pending = list_pending_proposed_objectives(
            user_id=self.user_a_id, class_id=self.class_a_id, database_path=self.db_path
        )
        self.assertEqual(len(pending), 2)

        # 2. Teacher approves prop1
        approved = approve_proposed_objective(
            user_id=self.user_a_id,
            proposal_id=prop1["id"],
            target_status="current",
            database_path=self.db_path,
        )
        self.assertIsNotNone(approved)
        self.assertEqual(approved["status"], "current")
        self.assertIn("Express opinions", approved["objective"])

        # 3. Teacher rejects prop2
        rejected = reject_proposed_objective(
            user_id=self.user_a_id,
            proposal_id=prop2["id"],
            database_path=self.db_path,
        )
        self.assertTrue(rejected)

        # 4. Check remaining pending proposals
        remaining = list_pending_proposed_objectives(
            user_id=self.user_a_id, class_id=self.class_a_id, database_path=self.db_path
        )
        self.assertEqual(len(remaining), 0)

        # 5. Check adopted class objectives
        active_objs = list_class_objectives(
            user_id=self.user_a_id, class_id=self.class_a_id, status_filter="current", database_path=self.db_path
        )
        self.assertEqual(len(active_objs), 1)

    def test_objective_status_transitions_and_teacher_confirmed_secure(self) -> None:
        """Verify explicit teacher updates between current, needs_support, secure, paused, and archived."""
        prop = propose_objective(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            objective_text="Use third conditional for past regrets",
            source_type="lesson",
            database_path=self.db_path,
        )
        obj = approve_proposed_objective(
            user_id=self.user_a_id,
            proposal_id=prop["id"],
            database_path=self.db_path,
        )
        obj_id = int(obj["id"])

        # Needs support
        st_sup = update_objective_status(
            user_id=self.user_a_id,
            objective_id=obj_id,
            new_status="needs_support",
            teacher_note="Learners forgot 'had + V3' auxiliary",
            database_path=self.db_path,
        )
        self.assertEqual(st_sup["status"], "needs_support")
        self.assertEqual(st_sup["is_secure"], 0)

        # Confirm secure
        st_sec = update_objective_status(
            user_id=self.user_a_id,
            objective_id=obj_id,
            new_status="secure",
            teacher_note="All learners produced accurate conditional sentences in pair work.",
            database_path=self.db_path,
        )
        self.assertEqual(st_sec["status"], "secure")
        self.assertEqual(st_sec["is_secure"], 1)
        self.assertIsNotNone(st_sec["secure_confirmed_at"])

        # Pause
        st_pau = update_objective_status(
            user_id=self.user_a_id,
            objective_id=obj_id,
            new_status="paused",
            database_path=self.db_path,
        )
        self.assertEqual(st_pau["status"], "paused")

    def test_one_hundred_percent_evidence_traceability(self) -> None:
        """Verify all progress claims cite underlying source records."""
        prop = propose_objective(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            objective_text="Paraphrase complex paragraphs",
            source_type="lesson",
            source_id=301,
            database_path=self.db_path,
        )
        obj = approve_proposed_objective(
            user_id=self.user_a_id,
            proposal_id=prop["id"],
            database_path=self.db_path,
        )
        obj_id = int(obj["id"])

        # Link concrete evidence outcome
        link_objective_evidence(
            user_id=self.user_a_id,
            objective_id=obj_id,
            class_id=self.class_a_id,
            source_type="lesson_outcome",
            source_id=401,
            support_level="observed_working",
            evidence_excerpt="8/10 students successfully paraphrased target text.",
            database_path=self.db_path,
        )

        detail = get_objective_detail_with_sources(
            user_id=self.user_a_id,
            objective_id=obj_id,
            database_path=self.db_path,
        )
        self.assertIsNotNone(detail)
        self.assertGreaterEqual(len(detail["evidence_links"]), 2)
        excerpts = [lnk["evidence_excerpt"] for lnk in detail["evidence_links"]]
        self.assertTrue(any("paraphrased target text" in e for e in excerpts))

    def test_class_health_card_prioritizes_instructional_decisions(self) -> None:
        """Verify health card diagnoses state correctly and suggests concrete next action."""
        # 1. Fresh class with no lessons/objectives
        fresh_health = get_class_health_card(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            database_path=self.db_path,
        )
        self.assertEqual(fresh_health["status"], "fresh_class")
        self.assertEqual(fresh_health["action_type"], "plan_lesson")

        # 2. Add an objective with needs_support
        prop = propose_objective(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            objective_text="Relative clauses",
            source_type="lesson",
            database_path=self.db_path,
        )
        obj = approve_proposed_objective(user_id=self.user_a_id, proposal_id=prop["id"], database_path=self.db_path)
        update_objective_status(user_id=self.user_a_id, objective_id=obj["id"], new_status="needs_support", database_path=self.db_path)

        needs_sup_health = get_class_health_card(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            database_path=self.db_path,
        )
        self.assertEqual(needs_sup_health["status"], "needs_support")
        self.assertIn("Reinforce Target", needs_sup_health["headline"])

    def test_progress_overview_assembly_and_honest_counts(self) -> None:
        """Verify progress overview aggregates counts and timelines without fake percentages."""
        overview = get_class_progress_overview(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            database_path=self.db_path,
        )
        self.assertEqual(overview["class_id"], self.class_a_id)
        self.assertIn("objectives_count", overview)
        self.assertIn("health_card", overview)
        self.assertIn("recent_timeline", overview)
        # Verify no percentage dials
        self.assertNotIn("mastery_percentage", overview)
        self.assertNotIn("class_rank", overview)

    def test_deleted_source_orphan_safety(self) -> None:
        """Verify deleting source materials nullifies pointers safely."""
        prop = propose_objective(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            objective_text="Inversion with negative adverbs",
            source_type="lesson",
            source_id=999,
            database_path=self.db_path,
        )
        obj = approve_proposed_objective(user_id=self.user_a_id, proposal_id=prop["id"], database_path=self.db_path)

        affected = handle_deleted_source(source_type="lesson", source_id=999, database_path=self.db_path)
        self.assertGreaterEqual(affected, 1)

        detail = get_objective_detail_with_sources(user_id=self.user_a_id, objective_id=obj["id"], database_path=self.db_path)
        self.assertIsNotNone(detail)
        self.assertEqual(detail["status"], "current")

    def test_multi_tenant_isolation(self) -> None:
        """Verify Teacher B cannot view, modify, or insert into Teacher A's progress data."""
        prop = propose_objective(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            objective_text="Class A Target",
            source_type="manual",
            database_path=self.db_path,
        )
        obj = approve_proposed_objective(user_id=self.user_a_id, proposal_id=prop["id"], database_path=self.db_path)
        obj_id = int(obj["id"])

        # Cross-access
        self.assertIsNone(get_objective_detail_with_sources(user_id=self.user_b_id, objective_id=obj_id, database_path=self.db_path))
        self.assertIsNone(update_objective_status(user_id=self.user_b_id, objective_id=obj_id, new_status="paused", database_path=self.db_path))
        self.assertEqual(list_pending_proposed_objectives(user_id=self.user_b_id, class_id=self.class_a_id, database_path=self.db_path), [])

        # Cross-class proposal trigger
        with self.assertRaises(Exception):
            propose_objective(
                user_id=self.user_b_id,
                class_id=self.class_a_id,
                objective_text="Cross proposal attempt",
                source_type="manual",
                database_path=self.db_path,
            )

    def test_telegram_keyboards_bounded_64_bytes(self) -> None:
        """Verify all progress inline keyboards strictly respect 64-byte limits."""
        keyboards = [
            progress_overview_keyboard(self.class_a_id, 1, pending_proposals_count=3),
            objectives_list_keyboard(self.class_a_id, 1, [], "current"),
            objective_detail_keyboard(101, self.class_a_id, 1),
            objective_status_picker_keyboard(101, self.class_a_id, 1, "current"),
            proposed_objectives_keyboard(self.class_a_id, 1, []),
            proposed_objective_review_keyboard(201, self.class_a_id, 1),
            health_card_keyboard(self.class_a_id, 1, "plan_lesson"),
            health_card_keyboard(self.class_a_id, 1, "review_session"),
            health_card_keyboard(self.class_a_id, 1, "record_outcome", lesson_id=301),
            timeline_browser_keyboard(self.class_a_id, 1),
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

    async def test_panel_callbacks_dispatching(self) -> None:
        """Verify Telegram panel callbacks for overview, objectives, proposals, and health card."""
        prop = propose_objective(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            objective_text="Express hypothetical past conditions",
            source_type="lesson",
            database_path=self.db_path,
        )
        prop_id = int(prop["id"])

        update = MagicMock()
        update.effective_user = self.teacher_a
        update.callback_query = MagicMock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        # 1. Progress home callback
        update.callback_query.data = f"v1|pr|home|{self.class_a_id:x}|1"
        await handle_progress_callback(update, context)
        update.callback_query.edit_message_text.assert_awaited()
        call_text = update.callback_query.edit_message_text.call_args[0][0]
        self.assertIn("Evidence-Linked Progress", call_text)

        # 2. View proposed callback
        update.callback_query.data = f"v1|pr|props|{self.class_a_id:x}|1"
        await handle_progress_callback(update, context)
        call_text = update.callback_query.edit_message_text.call_args[0][0]
        self.assertIn("Proposed Objectives", call_text)

        # 3. Approve proposal callback
        update.callback_query.data = f"v1|pr|apact|{prop_id:x}|1"
        await handle_progress_callback(update, context)
        call_text = update.callback_query.edit_message_text.call_args[0][0]
        self.assertIn("Adopted into Syllabus", call_text)

        # 4. Health card callback
        update.callback_query.data = f"v1|pr|hlth|{self.class_a_id:x}|1"
        await handle_progress_callback(update, context)
        call_text = update.callback_query.edit_message_text.call_args[0][0]
        self.assertIn("Class Health Card", call_text)


if __name__ == "__main__":
    unittest.main()
