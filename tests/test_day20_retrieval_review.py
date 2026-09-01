"""Tests for TeacherOS Day 20 Spaced-Retrieval Queue."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day20-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day20-key")

import database
from class_service import create_class
from day20_migration import SCHEMA_VERSION, apply_schema_v20
from feature_flags import FEATURE_ENV_VARS
from retrieval_review_keyboards import (
    add_category_keyboard,
    add_confirm_keyboard,
    confidence_picker_keyboard,
    due_item_card_keyboard,
    intervals_settings_keyboard,
    queue_browser_keyboard,
    queue_item_actions_keyboard,
    review_dashboard_keyboard,
    review_result_keyboard,
    snooze_picker_keyboard,
)
from retrieval_review_panel import (
    handle_retrieval_review_callback,
    handle_retrieval_review_message,
)
from retrieval_review_service import (
    DEFAULT_INTERVALS,
    MAX_DUE_ITEMS_PER_LESSON,
    VALID_CATEGORIES,
    VALID_SOURCE_TYPES,
    add_batch_review_items,
    add_review_item,
    archive_item,
    count_due_items,
    count_queue_items,
    get_class_intervals,
    get_due_items,
    get_review_item,
    get_review_queue,
    get_review_queue_stats,
    handle_deleted_source,
    override_review_schedule,
    pause_item,
    propose_retrieval_block,
    record_review,
    resume_item,
    snooze_item,
    update_class_intervals,
    update_confidence,
)


class Day20RetrievalReviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day20-test-")
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
            id=200_101,
            username="teacher_a",
            first_name="Alice",
            last_name="Teacher",
            language_code="en",
        )
        self.teacher_b = SimpleNamespace(
            id=200_102,
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
            display_name="C1 Advanced Fluency",
            level="C1",
            age_group="adults",
            learner_count_band="13_20",
            goal="Idiomatic speech & academic debate",
            database_path=self.db_path,
        )
        self.class_a_id = int(self.class_a["id"])

    def tearDown(self) -> None:
        database.DATABASE_PATH = self.orig_db_path
        self.flags_patcher.stop()
        self.temp_dir.cleanup()

    def test_schema_v20_initialized(self) -> None:
        """Verify schema version and table creation."""
        with database.database_connection(self.db_path) as conn:
            ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
            self.assertGreaterEqual(ver, 20)
            items_tbl = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='retrieval_review_items'"
            ).fetchone()
            logs_tbl = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='retrieval_review_logs'"
            ).fetchone()
            self.assertIsNotNone(items_tbl)
            self.assertIsNotNone(logs_tbl)

    def test_add_review_items_all_categories_and_sources(self) -> None:
        """Verify all 6 categories and 4 source types can be added."""
        for cat in VALID_CATEGORIES:
            item = add_review_item(
                user_id=self.user_a_id,
                class_id=self.class_a_id,
                category=cat,
                prompt_text=f"Prompt for {cat}",
                target_answer=f"Target answer for {cat}",
                source_type="lesson",
                source_id=10,
                database_path=self.db_path,
            )
            self.assertIsNotNone(item)
            self.assertEqual(item["category"], cat)
            self.assertEqual(item["status"], "active")
            self.assertEqual(item["interval_stage"], 0)
            self.assertEqual(item["intervals"], DEFAULT_INTERVALS)

        for src in VALID_SOURCE_TYPES:
            item = add_review_item(
                user_id=self.user_a_id,
                class_id=self.class_a_id,
                category="vocabulary",
                prompt_text=f"Prompt for source {src}",
                target_answer=f"Target answer for source {src}",
                source_type=src,
                source_id=20 if src != "manual" else None,
                database_path=self.db_path,
            )
            self.assertIsNotNone(item)
            self.assertEqual(item["source_type"], src)

    def test_deterministic_due_dates_and_stage_transitions(self) -> None:
        """Verify deterministic date calculations across all three review outcomes."""
        today_d = date(2026, 9, 1)
        today_str = today_d.strftime("%Y-%m-%d")

        item = add_review_item(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            category="grammar",
            prompt_text="Inversion with negative adverbials",
            target_answer="Rarely have I seen such dedication.",
            source_type="lesson",
            database_path=self.db_path,
        )
        item_id = int(item["id"])

        # 1. 'remembered': stage 0 -> 1 (+7 days = 2026-09-08)
        r1 = record_review(
            user_id=self.user_a_id,
            item_id=item_id,
            result="remembered",
            review_date=today_str,
            database_path=self.db_path,
        )
        self.assertEqual(r1["interval_stage"], 1)
        self.assertEqual(r1["next_review_date"], "2026-09-08")
        self.assertEqual(r1["review_count"], 1)

        # 2. 'partly_remembered': stage 1 -> 1 (+7 days from review date = 2026-09-15)
        r2 = record_review(
            user_id=self.user_a_id,
            item_id=item_id,
            result="partly_remembered",
            review_date="2026-09-08",
            database_path=self.db_path,
        )
        self.assertEqual(r2["interval_stage"], 1)
        self.assertEqual(r2["next_review_date"], "2026-09-15")
        self.assertEqual(r2["review_count"], 2)

        # 3. 'forgotten': stage 1 -> 0 (+2 days from review date = 2026-09-17)
        r3 = record_review(
            user_id=self.user_a_id,
            item_id=item_id,
            result="forgotten",
            review_date="2026-09-15",
            database_path=self.db_path,
        )
        self.assertEqual(r3["interval_stage"], 0)
        self.assertEqual(r3["next_review_date"], "2026-09-17")
        self.assertEqual(r3["review_count"], 3)

        # Verify audit logs
        with database.database_connection(self.db_path) as conn:
            logs = conn.execute(
                "SELECT * FROM retrieval_review_logs WHERE item_id = ? ORDER BY id ASC",
                (item_id,),
            ).fetchall()
            self.assertEqual(len(logs), 3)
            self.assertEqual(logs[0]["result"], "remembered")
            self.assertEqual(logs[1]["result"], "partly_remembered")
            self.assertEqual(logs[2]["result"], "forgotten")

    def test_configurable_intervals_schedule(self) -> None:
        """Verify custom interval schedules can be updated and retrieved."""
        add_review_item(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            category="vocabulary",
            prompt_text="pragmatic",
            target_answer="dealing with things sensibly and realistically",
            source_type="lesson",
            database_path=self.db_path,
        )

        custom = [1, 4, 10, 25]
        count = update_class_intervals(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            intervals=custom,
            database_path=self.db_path,
        )
        self.assertGreaterEqual(count, 1)
        self.assertEqual(
            get_class_intervals(user_id=self.user_a_id, class_id=self.class_a_id, database_path=self.db_path),
            custom,
        )

    def test_due_load_capping_and_retrieval_proposal(self) -> None:
        """Verify due items are capped at 5 and warm-up block is generated."""
        past_date = "2026-08-15"
        for i in range(12):
            add_review_item(
                user_id=self.user_a_id,
                class_id=self.class_a_id,
                category="vocabulary",
                prompt_text=f"C1 Collocation #{i+1}",
                target_answer=f"Example Answer #{i+1}",
                source_type="lesson",
                custom_next_date=past_date,
                database_path=self.db_path,
            )

        total_due = count_due_items(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            today_date="2026-09-01",
            database_path=self.db_path,
        )
        self.assertEqual(total_due, 12)

        due_capped = get_due_items(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            today_date="2026-09-01",
            database_path=self.db_path,
        )
        self.assertEqual(len(due_capped), MAX_DUE_ITEMS_PER_LESSON)

        proposal = propose_retrieval_block(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            today_date="2026-09-01",
            database_path=self.db_path,
        )
        self.assertTrue(proposal["has_due_items"])
        self.assertEqual(len(proposal["items"]), MAX_DUE_ITEMS_PER_LESSON)
        self.assertIn("Retrieval & Spaced-Review Warm-Up", proposal["retrieval_block_text"])
        self.assertGreaterEqual(proposal["estimated_minutes"], 4)

    def test_snooze_pause_resume_archive_state_machine(self) -> None:
        """Verify full lifecycle transitions for review items."""
        item = add_review_item(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            category="pronunciation",
            prompt_text="Intonation in tag questions",
            target_answer="Falling = confirmation, Rising = genuine question",
            source_type="lesson",
            database_path=self.db_path,
        )
        item_id = int(item["id"])

        # Snooze
        snz = snooze_item(user_id=self.user_a_id, item_id=item_id, days=4, database_path=self.db_path)
        self.assertEqual(snz["status"], "snoozed")
        self.assertIsNotNone(snz["snoozed_until"])

        # Pause
        p = pause_item(user_id=self.user_a_id, item_id=item_id, database_path=self.db_path)
        self.assertEqual(p["status"], "paused")

        # Resume
        r = resume_item(user_id=self.user_a_id, item_id=item_id, database_path=self.db_path)
        self.assertEqual(r["status"], "active")
        self.assertIsNone(r["snoozed_until"])

        # Confidence
        cf = update_confidence(user_id=self.user_a_id, item_id=item_id, confidence="high", database_path=self.db_path)
        self.assertEqual(cf["confidence"], "high")

        # Override
        over = override_review_schedule(
            user_id=self.user_a_id,
            item_id=item_id,
            next_review_date="2026-11-20",
            stage=2,
            notes="Adjusted for mock exam",
            database_path=self.db_path,
        )
        self.assertEqual(over["next_review_date"], "2026-11-20")
        self.assertEqual(over["interval_stage"], 2)

        # Archive
        ar = archive_item(user_id=self.user_a_id, item_id=item_id, database_path=self.db_path)
        self.assertEqual(ar["status"], "archived")

    def test_deleted_source_orphan_safety(self) -> None:
        """When a lesson is deleted, review items remain active with source_id=NULL."""
        item = add_review_item(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            category="vocabulary",
            prompt_text="tenacious",
            target_answer="tending to keep a firm hold of something; persistent",
            source_type="lesson",
            source_id=888,
            database_path=self.db_path,
        )
        item_id = int(item["id"])

        affected = handle_deleted_source(source_type="lesson", source_id=888, database_path=self.db_path)
        self.assertEqual(affected, 1)

        updated = get_review_item(user_id=self.user_a_id, item_id=item_id, database_path=self.db_path)
        self.assertIsNone(updated["source_id"])
        self.assertEqual(updated["status"], "active")
        self.assertEqual(updated["prompt_text"], "tenacious")

    def test_multi_tenant_isolation(self) -> None:
        """Teacher B cannot access, review, or modify Teacher A's queue items."""
        item = add_review_item(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            category="vocabulary",
            prompt_text="Class A Exclusive Lexis",
            target_answer="Answer A",
            source_type="manual",
            database_path=self.db_path,
        )
        item_id = int(item["id"])

        # Cross-access
        self.assertIsNone(get_review_item(user_id=self.user_b_id, item_id=item_id, database_path=self.db_path))
        self.assertEqual(get_due_items(user_id=self.user_b_id, class_id=self.class_a_id, database_path=self.db_path), [])
        self.assertIsNone(record_review(user_id=self.user_b_id, item_id=item_id, result="remembered", database_path=self.db_path))
        self.assertIsNone(pause_item(user_id=self.user_b_id, item_id=item_id, database_path=self.db_path))

        # Cross-class insertion trigger
        with self.assertRaises(Exception):
            add_review_item(
                user_id=self.user_b_id,
                class_id=self.class_a_id,
                category="vocabulary",
                prompt_text="Intrusion attempt",
                target_answer="Blocked",
                source_type="manual",
                database_path=self.db_path,
            )

    def test_telegram_keyboards_bounded_64_bytes(self) -> None:
        """All review queue keyboards must strictly adhere to Telegram's 64-byte limit."""
        sample_items = [
            {"id": 1, "category": "vocabulary", "prompt_text": "short prompt", "next_review_date": "2026-09-05"},
            {"id": 2, "category": "grammar", "prompt_text": "longer prompt structure", "next_review_date": "2026-09-08"},
        ]
        keyboards = [
            review_dashboard_keyboard(self.class_a_id, 1, 5, 25),
            due_item_card_keyboard(101, self.class_a_id, 1, revealed=False),
            due_item_card_keyboard(101, self.class_a_id, 1, revealed=True),
            review_result_keyboard(101, self.class_a_id, 1, has_more_due=True),
            snooze_picker_keyboard(101, self.class_a_id, 1),
            confidence_picker_keyboard(101, self.class_a_id, 1),
            queue_browser_keyboard(self.class_a_id, 1, sample_items, 0, 2, "active"),
            queue_item_actions_keyboard(101, self.class_a_id, 1, "active"),
            add_category_keyboard(self.class_a_id, 1),
            add_confirm_keyboard(self.class_a_id, 1),
            intervals_settings_keyboard(self.class_a_id, 1),
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
        """Verify Telegram panel callbacks for dashboard, reveal, snooze, and confidence."""
        item = add_review_item(
            user_id=self.user_a_id,
            class_id=self.class_a_id,
            category="vocabulary",
            prompt_text="ubiquitous",
            target_answer="present, appearing, or found everywhere",
            source_type="lesson",
            database_path=self.db_path,
        )
        item_id = int(item["id"])

        # 1. Dashboard callback
        update = MagicMock()
        update.effective_user = self.teacher_a
        update.callback_query = MagicMock()
        update.callback_query.data = f"v1|rv|home|{self.class_a_id:x}|1"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        await handle_retrieval_review_callback(update, context)
        update.callback_query.edit_message_text.assert_awaited()
        call_text = update.callback_query.edit_message_text.call_args[0][0]
        self.assertIn("Spaced-Review Queue", call_text)

        # 2. Reveal answer callback
        update.callback_query.data = f"v1|rv|rev|{item_id:x}|1"
        await handle_retrieval_review_callback(update, context)
        call_text = update.callback_query.edit_message_text.call_args[0][0]
        self.assertIn("Answer Revealed", call_text)
        self.assertIn("ubiquitous", call_text)

        # 3. Record review remembered callback
        update.callback_query.data = f"v1|rv|rr|{item_id:x}|1"
        await handle_retrieval_review_callback(update, context)
        call_text = update.callback_query.edit_message_text.call_args[0][0]
        self.assertIn("Review Recorded", call_text)

        # 4. Snooze +3 days callback
        update.callback_query.data = f"v1|rv|s3|{item_id:x}|1"
        await handle_retrieval_review_callback(update, context)
        call_text = update.callback_query.edit_message_text.call_args[0][0]
        self.assertIn("Item Snoozed", call_text)

    async def test_panel_message_flow_manual_add(self) -> None:
        """Verify multi-step text input flow for manually adding review items."""
        update = MagicMock()
        update.effective_user = self.teacher_a
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {
            "review_add": {
                "class_id": self.class_a_id,
                "revision": 1,
                "category": "vocabulary",
                "state": "prompt",
            }
        }

        # Step 1: Teacher types prompt text
        update.message.text = "What adjective means existing everywhere?"
        await handle_retrieval_review_message(update, context)
        self.assertEqual(context.user_data["review_add"]["state"], "answer")
        self.assertEqual(context.user_data["review_add"]["prompt"], "What adjective means existing everywhere?")
        update.message.reply_text.assert_awaited()

        # Step 2: Teacher types target answer
        update.message.text = "omnipresent / ubiquitous"
        await handle_retrieval_review_message(update, context)
        self.assertEqual(context.user_data["review_add"]["state"], "confirm")
        self.assertEqual(context.user_data["review_add"]["answer"], "omnipresent / ubiquitous")
        call_text = update.message.reply_text.call_args[0][0]
        self.assertIn("Review Item Preview", call_text)


if __name__ == "__main__":
    unittest.main()
