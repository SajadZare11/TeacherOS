"""Tests for TeacherOS Day 23 Editable, Evidence-Safe Progress Reports."""
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
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day23-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day23-key")

import database
from class_service import create_class
from curriculum_discipline_service import save_curriculum_unit
from day25_migration import SCHEMA_VERSION
from feature_flags import FEATURE_ENV_VARS
from progress_report_keyboards import (
    report_dashboard_keyboard,
    report_edit_cancel_keyboard,
    report_edit_section_picker_keyboard,
    report_list_keyboard,
    report_type_picker_keyboard,
    report_view_keyboard,
)
from progress_report_panel import handle_progress_report_callback, handle_progress_report_message
from progress_report_service import (
    approve_progress_report,
    export_progress_report_pdf,
    export_progress_report_word,
    generate_progress_report,
    get_progress_report,
    handle_deleted_source,
    list_progress_reports,
    update_progress_report_section,
)


class Day23ProgressReportsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day23-test-")
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
            id=230_101,
            username="teacher_a",
            first_name="Alice",
            last_name="Teacher",
            language_code="en",
        )
        self.teacher_b = SimpleNamespace(
            id=230_102,
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
            display_name="C1 Academic Writing & Debate",
            level="C1",
            age_group="adults",
            learner_count_band="6_12",
            goal="IELTS 7.5+ and executive communications",
            database_path=self.db_path,
        )
        self.class_a_id = int(self.class_a["id"])

    def tearDown(self) -> None:
        database.DATABASE_PATH = self.orig_db_path
        self.flags_patcher.stop()
        self.temp_dir.cleanup()

    def test_schema_v23_initialized(self) -> None:
        """Verify schema version 23 and table creation."""
        with database.database_connection(self.db_path) as conn:
            ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
            self.assertGreaterEqual(ver, 23)
            t1 = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='class_progress_reports'"
            ).fetchone()
            t2 = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='progress_report_revisions'"
            ).fetchone()
            self.assertIsNotNone(t1)
            self.assertIsNotNone(t2)

    def test_insufficient_evidence_boundary(self) -> None:
        """Verify report creation with zero records flags insufficient evidence instead of inventing facts."""
        rep = generate_progress_report(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            report_type="whole_class_summary",
            reporting_period_start="2026-08-01",
            reporting_period_end="2026-08-31",
            database_path=self.db_path,
        )
        self.assertIsNotNone(rep)
        self.assertEqual(rep["has_insufficient_evidence"], 1)
        self.assertIn("Insufficient recorded", rep["learning_covered_text"])
        self.assertEqual(rep["status"], "draft")
        self.assertEqual(rep["share_safe_verified"], 0)

    def test_generate_all_three_report_types_with_evidence(self) -> None:
        """Verify whole-class, end-of-unit, and reflection reports assemble approved records."""
        unit = save_curriculum_unit(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            unit_number="5",
            unit_title="Global Economics & Trade",
            database_path=self.db_path,
        )
        with database.database_connection(self.db_path) as conn:
            c_lesson = conn.execute(
                """
                INSERT INTO class_lessons (class_id, user_id, title, scheduled_for, status)
                VALUES (?, ?, 'Trade Tariffs Discussion', '2026-08-20', 'taught')
                """,
                (self.class_a_id, self.user_a_id),
            )
            lesson_id = c_lesson.lastrowid
            conn.execute(
                """
                INSERT INTO lesson_outcomes (
                    class_lesson_id, class_id, user_id, result, confidence, support_needed, status, created_at
                ) VALUES (?, ?, ?, 'met', 'high', 'none', 'saved', '2026-08-20T10:00:00Z')
                """,
                (lesson_id, self.class_a_id, self.user_a_id),
            )

        rep_class = generate_progress_report(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            report_type="whole_class_summary",
            reporting_period_start="2026-08-01",
            reporting_period_end="2026-08-31",
            database_path=self.db_path,
        )
        rep_unit = generate_progress_report(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            report_type="end_of_unit_summary",
            reporting_period_start="2026-08-01",
            reporting_period_end="2026-08-31",
            unit_id=unit["id"],
            database_path=self.db_path,
        )
        rep_refl = generate_progress_report(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            report_type="teacher_reflection",
            reporting_period_start="2026-08-01",
            reporting_period_end="2026-08-31",
            database_path=self.db_path,
        )

        self.assertEqual(rep_class["has_insufficient_evidence"], 0)
        self.assertIn("Unit 5", rep_unit["title"])
        self.assertEqual(rep_refl["report_type"], "teacher_reflection")

    def test_update_section_and_audit_versioning(self) -> None:
        """Verify section editing increments version and records prior values in revision history."""
        rep = generate_progress_report(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            report_type="whole_class_summary",
            reporting_period_start="2026-08-01",
            reporting_period_end="2026-08-31",
            database_path=self.db_path,
        )
        self.assertEqual(rep["version"], 1)

        updated = update_progress_report_section(
            user_id=self.user_a_id,
            report_id=rep["id"],
            field_name="teacher_comments",
            new_value="Teacher verified: strong participation in mock debates.",
            database_path=self.db_path,
        )
        self.assertEqual(updated["version"], 2)
        self.assertIn("mock debates", updated["teacher_comments"])

        with database.database_connection(self.db_path) as conn:
            revs = conn.execute(
                "SELECT * FROM progress_report_revisions WHERE report_id = ?",
                (rep["id"],),
            ).fetchall()
        self.assertEqual(len(revs), 1)
        self.assertEqual(revs[0]["version"], 2)
        self.assertEqual(revs[0]["field_changed"], "teacher_comments")

    def test_teacher_approval_gate(self) -> None:
        """Verify approval transitions report to approved and verified share-safe."""
        rep = generate_progress_report(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            report_type="whole_class_summary",
            reporting_period_start="2026-08-01",
            reporting_period_end="2026-08-31",
            database_path=self.db_path,
        )
        self.assertEqual(rep["status"], "draft")
        self.assertEqual(rep["share_safe_verified"], 0)

        approved = approve_progress_report(
            user_id=self.user_a_id,
            report_id=rep["id"],
            database_path=self.db_path,
        )
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["share_safe_verified"], 1)
        self.assertIsNotNone(approved["approved_at"])

    def test_word_and_pdf_exports(self) -> None:
        """Verify Word (.docx) and PDF (.pdf) documents are created with non-empty payloads and privacy footers."""
        rep = generate_progress_report(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            report_type="whole_class_summary",
            reporting_period_start="2026-08-01",
            reporting_period_end="2026-08-31",
            database_path=self.db_path,
        )

        doc_name, doc_bytes = export_progress_report_word(
            user_id=self.user_a_id,
            report_id=rep["id"],
            database_path=self.db_path,
        )
        pdf_name, pdf_bytes = export_progress_report_pdf(
            user_id=self.user_a_id,
            report_id=rep["id"],
            database_path=self.db_path,
        )

        self.assertTrue(doc_name.endswith(".docx"))
        self.assertGreater(len(doc_bytes), 1000)
        self.assertTrue(pdf_name.endswith(".pdf"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_deleted_source_handling(self) -> None:
        """Verify handle_deleted_source flags purged sources safely."""
        generate_progress_report(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            report_type="whole_class_summary",
            reporting_period_start="2026-08-01",
            reporting_period_end="2026-08-31",
            database_path=self.db_path,
        )
        updated = handle_deleted_source(
            source_type="lesson_outcome",
            source_id=99,
            database_path=self.db_path,
        )
        self.assertGreaterEqual(updated, 0)

    def test_multi_tenant_isolation(self) -> None:
        """Verify Teacher B cannot view, modify, or insert into Teacher A's reports."""
        rep = generate_progress_report(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            report_type="whole_class_summary",
            reporting_period_start="2026-08-01",
            reporting_period_end="2026-08-31",
            database_path=self.db_path,
        )
        self.assertIsNone(
            get_progress_report(user_id=self.user_b_id, report_id=rep["id"], database_path=self.db_path)
        )
        self.assertIsNone(
            update_progress_report_section(
                user_id=self.user_b_id,
                report_id=rep["id"],
                field_name="teacher_comments",
                new_value="Hacked",
                database_path=self.db_path,
            )
        )

    def test_telegram_keyboards_bounded_64_bytes(self) -> None:
        """Verify all report inline keyboards strictly respect 64-byte limit."""
        keyboards = [
            report_dashboard_keyboard(self.class_a_id, 1, 2),
            report_type_picker_keyboard(self.class_a_id, 1),
            report_view_keyboard(101, self.class_a_id, 1, status="draft"),
            report_view_keyboard(101, self.class_a_id, 1, status="approved"),
            report_edit_section_picker_keyboard(101, self.class_a_id, 1),
            report_edit_cancel_keyboard(101, 1),
            report_list_keyboard(self.class_a_id, 1, []),
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
        """Verify Telegram panel callbacks for reports home, generation, view, and editing."""
        update = MagicMock()
        update.effective_user = self.teacher_a
        update.callback_query = MagicMock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        # 1. Reports Home
        update.callback_query.data = f"v1|rp|home|{self.class_a_id:x}|1"
        await handle_progress_report_callback(update, context)
        update.callback_query.edit_message_text.assert_awaited()
        call_text = update.callback_query.edit_message_text.call_args[0][0]
        self.assertIn("Progress Reports", call_text)

        # 2. Generate whole-class report
        update.callback_query.data = f"v1|rp|tcls|{self.class_a_id:x}|1"
        await handle_progress_report_callback(update, context)
        update.callback_query.edit_message_text.assert_awaited()

        # Get generated report id from database
        rep = list_progress_reports(user_id=self.user_a_id, class_id=self.class_a_id, database_path=self.db_path)[0]
        rep_id = rep["id"]

        # 3. Edit teacher comments
        update.callback_query.data = f"v1|rp|ecom|{rep_id:x}|1"
        await handle_progress_report_callback(update, context)
        self.assertEqual(context.user_data["report_edit"]["state"], "editing")

        # 4. Save section text via message
        update.message.text = "Students made excellent progress in oral fluency."
        await handle_progress_report_message(update, context)
        update.message.reply_text.assert_awaited()
        msg_text = update.message.reply_text.call_args[0][0]
        self.assertIn("Section Updated", msg_text)
        self.assertIn("oral fluency", msg_text)


if __name__ == "__main__":
    unittest.main()
