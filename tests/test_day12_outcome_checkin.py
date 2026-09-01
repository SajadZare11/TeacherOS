from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day12-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day12-key")

import class_service  # noqa: E402
import database  # noqa: E402
from class_dashboard_keyboards import (  # noqa: E402
    outcome_completion_keyboard,
    outcome_difficulty_keyboard,
    outcome_reminder_keyboard,
    outcome_result_keyboard,
)
from class_dashboard_panel import (  # noqa: E402
    get_class_dashboard_text,
    handle_dashboard_callback,
)
from class_dashboard_service import class_dashboard_snapshot, today_queue  # noqa: E402
from day24_migration import SCHEMA_VERSION  # noqa: E402
from feature_flags import FEATURE_ENV_VARS  # noqa: E402
from lesson_history_service import mark_lesson_taught, schedule_material_lesson  # noqa: E402
from main import post_init, post_shutdown, send_due_outcome_reminders_once  # noqa: E402
from outcome_checkin_service import (  # noqa: E402
    claim_due_outcome_reminders,
    get_lesson_outcome,
    list_outcome_lessons,
    outcome_recording_metrics,
    reminder_due_utc,
    schedule_outcome_reminder,
    save_outcome_facts,
    update_outcome_note,
)


def teacher(identifier: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier, username=f"day12_{identifier}", first_name="Day Twelve",
        last_name="Teacher", language_code="en",
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
        for row in markup.inline_keyboard for button in row if button.callback_data
    ]


class Day12OutcomeCheckinTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="teacheros-day12-")
        self.path = Path(self.temp.name) / "teacheros.db"
        self.db_patch = patch.object(database, "DATABASE_PATH", self.path)
        self.db_patch.start()
        flags = {value: "false" for value in FEATURE_ENV_VARS.values()}
        flags[FEATURE_ENV_VARS["classes"]] = "true"
        flags[FEATURE_ENV_VARS["continuity"]] = "true"
        self.flag_patch = patch.dict(os.environ, flags, clear=False)
        self.flag_patch.start()
        self.owner = teacher(112_001)
        self.other = teacher(112_002)
        self.class_record = class_service.create_class(
            telegram_user=self.owner, display_name="Day 12 Class", level="B1",
            cadence="weekly", goal="Truth without workload",
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
            telegram_user=self.owner, material_type="lesson", title=title,
            content="CEFR B1. Timing 45 minutes. Materials board. Instructions included.",
            level="B1", topic="Outcome truth", class_id=int(self.class_record["id"]),
        )
        scheduled = schedule_material_lesson(
            telegram_user_id=self.owner.id, material_id=material_id, date_choice="today"
        )
        if scheduled["status"] == "conflict":
            scheduled = schedule_material_lesson(
                telegram_user_id=self.owner.id, material_id=material_id,
                date_choice="today", replace=True,
            )
        lesson = scheduled["lesson"]
        if taught:
            lesson, changed = mark_lesson_taught(
                telegram_user_id=self.owner.id, lesson_id=int(lesson["id"])
            )
            self.assertTrue(changed)
        return lesson

    def test_schema_v12_is_additive_repeatable_and_separates_ai_suggestions(self) -> None:
        database.initialize_database(self.path)
        database.initialize_database(self.path)
        with database.database_connection(self.path) as connection:
            version = int(connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0])
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(lesson_outcomes)")}
            tables = {str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )}
            triggers = {str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )}
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertTrue({
            "difficulty_categories_json", "completion_status", "facts_version",
            "capture_source", "saved_at", "note_updated_at",
        } <= columns)
        self.assertTrue({
            "lesson_outcome_fact_revisions", "lesson_outcome_reminders",
            "lesson_outcome_ai_suggestions",
        } <= tables)
        self.assertIn("trg_outcome_active_unique_insert_v12", triggers)
        self.assertIn("trg_outcome_revision_immutable_update_v12", triggers)
        self.assertEqual(foreign_keys, [])

    def test_normal_path_saves_three_facts_without_note_and_is_idempotent(self) -> None:
        lesson = self._lesson("Three taps")
        outcome, changed = save_outcome_facts(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
            result="achieved", difficulty_categories=["none"],
            completion_status="completed",
        )
        duplicate, duplicate_changed = save_outcome_facts(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
            result="achieved", difficulty_categories=["none"],
            completion_status="completed",
        )
        self.assertTrue(changed)
        self.assertFalse(duplicate_changed)
        self.assertEqual(outcome["id"], duplicate["id"])
        self.assertEqual(outcome["status"], "approved")
        self.assertEqual(outcome["difficulty_categories"], ["none"])
        self.assertIsNone(outcome["notes"])
        self.assertEqual(outcome_recording_metrics(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        ), {"taught": 1, "outcomes_recorded": 1, "recording_rate_percent": 100})
        with database.database_connection(self.path) as connection:
            self.assertEqual(int(connection.execute("SELECT COUNT(*) FROM lesson_outcomes").fetchone()[0]), 1)
            self.assertEqual(int(connection.execute("SELECT COUNT(*) FROM lesson_outcome_fact_revisions").fetchone()[0]), 1)

    def test_multi_select_correction_updates_one_record_and_keeps_revisions(self) -> None:
        lesson = self._lesson("Correction path")
        original, _ = save_outcome_facts(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
            result="partly_achieved", difficulty_categories=["language", "pace"],
            completion_status="partly_completed",
        )
        corrected, changed = save_outcome_facts(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
            result="needs_reteaching", difficulty_categories=["instructions", "participation"],
            completion_status="not_completed",
        )
        self.assertTrue(changed)
        self.assertEqual(original["id"], corrected["id"])
        self.assertEqual(corrected["facts_version"], 2)
        self.assertEqual(corrected["difficulty_categories"], ["instructions", "participation"])
        with database.database_connection(self.path) as connection:
            self.assertEqual(int(connection.execute("SELECT COUNT(*) FROM lesson_outcomes").fetchone()[0]), 1)
            self.assertEqual(int(connection.execute("SELECT COUNT(*) FROM lesson_outcome_fact_revisions").fetchone()[0]), 2)
            self.assertEqual(int(connection.execute("SELECT COUNT(*) FROM lesson_outcome_ai_suggestions").fetchone()[0]), 0)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE lesson_outcome_fact_revisions SET reason = 'rewritten' WHERE lesson_outcome_id = ?",
                    (corrected["id"],),
                )

    def test_ai_suggestion_storage_is_separate_and_owner_scoped(self) -> None:
        lesson = self._lesson("Separate suggestion")
        outcome, _ = save_outcome_facts(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
            result="partly_achieved", difficulty_categories=["pace"],
            completion_status="partly_completed",
        )
        with database.database_connection(self.path) as connection:
            connection.execute(
                """
                INSERT INTO lesson_outcome_ai_suggestions (
                    lesson_outcome_id, class_lesson_id, class_id, user_id,
                    suggestion_json, source_record_ids_json
                ) VALUES (?, ?, ?, ?, '{"next_step":"review"}', '[1]')
                """,
                (
                    outcome["id"], outcome["class_lesson_id"],
                    outcome["class_id"], outcome["user_id"],
                ),
            )
            suggestion_count = int(connection.execute(
                "SELECT COUNT(*) FROM lesson_outcome_ai_suggestions"
            ).fetchone()[0])
            fact_columns = {str(row[1]) for row in connection.execute(
                "PRAGMA table_info(lesson_outcomes)"
            )}
        reread = get_lesson_outcome(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"])
        )
        self.assertEqual(suggestion_count, 1)
        self.assertNotIn("suggestion_json", fact_columns)
        self.assertEqual(reread["result"], "partly_met")

    def test_optional_note_add_edit_clear_and_privacy_validation(self) -> None:
        lesson = self._lesson("Optional note")
        save_outcome_facts(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
            result="achieved", difficulty_categories=["none"], completion_status="completed",
        )
        added, added_changed = update_outcome_note(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
            note="Needed one extra example.",
        )
        edited, edited_changed = update_outcome_note(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
            note="Needed two extra examples.",
        )
        cleared, cleared_changed = update_outcome_note(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]), note=None
        )
        self.assertTrue(added_changed and edited_changed and cleared_changed)
        self.assertEqual((added["facts_version"], edited["facts_version"], cleared["facts_version"]), (2, 3, 4))
        self.assertIsNone(cleared["notes"])
        with self.assertRaises(ValueError):
            update_outcome_note(
                telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
                note="Contact learner@example.com",
            )
        with self.assertRaises(ValueError):
            update_outcome_note(
                telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
                note="x" * 1001,
            )
        with database.database_connection(self.path) as connection:
            revision_columns = {str(row[1]) for row in connection.execute(
                "PRAGMA table_info(lesson_outcome_fact_revisions)"
            )}
        self.assertNotIn("notes", revision_columns)

    def test_non_taught_and_cross_owner_outcomes_fail_closed(self) -> None:
        planned = self._lesson("Still planned", taught=False)
        outcome, changed = save_outcome_facts(
            telegram_user_id=self.owner.id, lesson_id=int(planned["id"]),
            result="achieved", difficulty_categories=["none"], completion_status="completed",
        )
        self.assertIsNone(outcome)
        self.assertFalse(changed)
        taught = self._lesson("Private taught lesson")
        cross, cross_changed = save_outcome_facts(
            telegram_user_id=self.other.id, lesson_id=int(taught["id"]),
            result="achieved", difficulty_categories=["none"], completion_status="completed",
        )
        self.assertIsNone(cross)
        self.assertFalse(cross_changed)
        self.assertIsNone(get_lesson_outcome(
            telegram_user_id=self.other.id, lesson_id=int(taught["id"])
        ))
        self.assertEqual(list_outcome_lessons(
            telegram_user_id=self.other.id, class_id=int(self.class_record["id"])
        ), [])

    def test_teacher_selected_local_times_are_deterministic(self) -> None:
        now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(reminder_due_utc("one_hour", now_utc=now), now + timedelta(hours=1))
        self.assertEqual(reminder_due_utc("local_18", now_utc=now), datetime(2026, 8, 31, 14, 30, tzinfo=timezone.utc))
        self.assertEqual(reminder_due_utc("local_20", now_utc=now), datetime(2026, 8, 31, 16, 30, tzinfo=timezone.utc))
        self.assertEqual(reminder_due_utc("tomorrow_09", now_utc=now), datetime(2026, 9, 1, 5, 30, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            reminder_due_utc("whenever", now_utc=now)

    def test_reminder_is_one_shot_duplicate_safe_and_completed_by_outcome(self) -> None:
        lesson = self._lesson("One-shot reminder")
        now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
        first = schedule_outcome_reminder(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
            choice="one_hour", now_utc=now,
        )
        duplicate = schedule_outcome_reminder(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
            choice="one_hour", now_utc=now,
        )
        self.assertEqual((first["status"], duplicate["status"]), ("scheduled", "already_scheduled"))
        self.assertEqual(claim_due_outcome_reminders(
            now_utc=now + timedelta(minutes=30), database_path=self.path
        ), [])
        due = claim_due_outcome_reminders(
            now_utc=now + timedelta(hours=2), database_path=self.path
        )
        self.assertEqual(len(due), 1)
        self.assertEqual(claim_due_outcome_reminders(
            now_utc=now + timedelta(hours=3), database_path=self.path
        ), [])
        save_outcome_facts(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
            result="achieved", difficulty_categories=["none"], completion_status="completed",
        )
        with database.database_connection(self.path) as connection:
            status = str(connection.execute(
                "SELECT status FROM lesson_outcome_reminders WHERE class_lesson_id = ?",
                (lesson["id"],),
            ).fetchone()[0])
        self.assertEqual(status, "completed")

    def test_reminder_prompt_cap_requires_explicit_snooze(self) -> None:
        lesson = self._lesson("Reminder cap")
        current = datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc)
        for expected_count in (1, 2, 3):
            result = schedule_outcome_reminder(
                telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
                choice="one_hour", now_utc=current,
            )
            self.assertEqual(result["status"], "scheduled")
            due = claim_due_outcome_reminders(
                now_utc=current + timedelta(hours=2), database_path=self.path
            )
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0]["prompt_count"], expected_count)
            current += timedelta(hours=3)
        limited = schedule_outcome_reminder(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
            choice="one_hour", now_utc=current,
        )
        self.assertEqual(limited["status"], "limit")

    def test_today_queue_honors_future_snooze_then_surfaces_due_lesson(self) -> None:
        lesson = self._lesson("Today reminder")
        initial = today_queue(telegram_user_id=self.owner.id, database_path=self.path)
        self.assertTrue(any(item["kind"] == "missing_outcome" for item in initial))
        schedule_outcome_reminder(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]), choice="one_hour"
        )
        snoozed = today_queue(telegram_user_id=self.owner.id, database_path=self.path)
        self.assertFalse(any(item["kind"] == "missing_outcome" for item in snoozed))
        with database.database_connection(self.path) as connection:
            connection.execute(
                "UPDATE lesson_outcome_reminders SET next_prompt_at_utc = '2000-01-01T00:00:00.000Z' "
                "WHERE class_lesson_id = ?", (lesson["id"],),
            )
        due = today_queue(telegram_user_id=self.owner.id, database_path=self.path)
        self.assertTrue(any(item["kind"] == "missing_outcome" for item in due))

    async def test_restart_safe_normal_ui_path_is_exactly_three_fact_taps(self) -> None:
        lesson = self._lesson("Three tap UI")
        revision = int(self.class_record["revision"])
        query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
        context = SimpleNamespace(user_data={})
        update = SimpleNamespace(callback_query=query, effective_user=self.owner)

        await handle_dashboard_callback(
            update, context, action="ostart", object_id=b36(int(lesson["id"])),
            revision_text=b36(revision),
        )
        self.assertIn("Tap 1 of 3", query.edit_message_text.await_args.args[0])
        await handle_dashboard_callback(
            update, context, action="ores", object_id="a" + b36(int(lesson["id"])),
            revision_text=b36(revision),
        )
        self.assertIn("Tap 2 of 3", query.edit_message_text.await_args.args[0])
        await handle_dashboard_callback(
            update, context, action="odone", object_id="a00" + b36(int(lesson["id"])),
            revision_text=b36(revision),
        )
        self.assertIn("Tap 3 of 3", query.edit_message_text.await_args.args[0])
        await handle_dashboard_callback(
            update, context, action="ocomp", object_id="ca00" + b36(int(lesson["id"])),
            revision_text=b36(revision),
        )
        self.assertIn("Outcome saved", query.edit_message_text.await_args.args[0])
        self.assertIsNotNone(get_lesson_outcome(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"])
        ))

    async def test_mark_taught_prompts_immediately_and_note_text_is_optional(self) -> None:
        planned = self._lesson("Immediate prompt", taught=False)
        revision = int(self.class_record["revision"])
        query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
        context = SimpleNamespace(user_data={})
        await handle_dashboard_callback(
            SimpleNamespace(callback_query=query, effective_user=self.owner), context,
            action="taught", object_id=b36(int(planned["id"])), revision_text=b36(revision),
        )
        self.assertIn("Marked as taught", query.edit_message_text.await_args.args[0])
        self.assertIn("Tap 1 of 3", query.edit_message_text.await_args.args[0])
        save_outcome_facts(
            telegram_user_id=self.owner.id, lesson_id=int(planned["id"]),
            result="achieved", difficulty_categories=["none"], completion_status="completed",
        )
        context.user_data["outcome_note"] = {
            "state": "text", "lesson_id": int(planned["id"]),
            "class_id": int(self.class_record["id"]), "revision": revision,
        }
        message = SimpleNamespace(text="Optional pacing note", reply_text=AsyncMock())
        await get_class_dashboard_text(
            SimpleNamespace(message=message, effective_user=self.owner), context
        )
        self.assertIn("Optional note saved", message.reply_text.await_args.args[0])
        self.assertNotIn("outcome_note", context.user_data)

    async def test_due_dispatch_delivers_once_with_record_and_snooze_actions(self) -> None:
        lesson = self._lesson("Dispatch reminder")
        now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
        schedule_outcome_reminder(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
            choice="one_hour", now_utc=now,
        )
        with database.database_connection(self.path) as connection:
            connection.execute(
                "UPDATE lesson_outcome_reminders SET next_prompt_at_utc = '2000-01-01T00:00:00.000Z'"
            )
        application = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
        delivered = await send_due_outcome_reminders_once(application)
        delivered_again = await send_due_outcome_reminders_once(application)
        self.assertEqual((delivered, delivered_again), (1, 0))
        application.bot.send_message.assert_awaited_once()
        markup = application.bot.send_message.await_args.kwargs["reply_markup"]
        values = callbacks(markup)
        self.assertTrue(any("|ores|" in value for value in values))
        self.assertTrue(any("|oremind|" in value for value in values))

    async def test_reminder_background_task_has_clean_startup_and_shutdown(self) -> None:
        application = SimpleNamespace(
            bot=SimpleNamespace(
                set_my_commands=AsyncMock(),
                set_my_short_description=AsyncMock(),
                set_my_description=AsyncMock(),
                send_message=AsyncMock(),
            ),
            bot_data={},
        )
        await post_init(application)
        await asyncio.sleep(0)
        task = application.bot_data.get("outcome_reminder_task")
        self.assertIsInstance(task, asyncio.Task)
        self.assertFalse(task.done())
        await post_shutdown(application)
        self.assertNotIn("outcome_reminder_task", application.bot_data)
        self.assertTrue(task.done())

    def test_callback_payloads_are_compact_for_every_day12_screen(self) -> None:
        lesson_id = 36**8 - 1
        revision = 36**5 - 1
        markups = [
            outcome_result_keyboard(lesson_id, revision),
            outcome_difficulty_keyboard(lesson_id, "a", 63, revision),
            outcome_completion_keyboard(lesson_id, "p", 63, revision),
            outcome_reminder_keyboard(lesson_id, revision),
        ]
        values = [value for markup in markups for value in callbacks(markup)]
        self.assertTrue(values)
        self.assertTrue(all(len(value.encode("utf-8")) <= 64 for value in values))
        self.assertTrue(all(len(value.split("|")[3]) <= 13 for value in values))

    def test_dashboard_updates_immediately_and_exposes_correction(self) -> None:
        lesson = self._lesson("Dashboard truth")
        save_outcome_facts(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"]),
            result="partly_achieved", difficulty_categories=["pace"],
            completion_status="partly_completed",
        )
        snapshot = class_dashboard_snapshot(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"]),
            database_path=self.path,
        )
        candidates = list_outcome_lessons(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"]),
            database_path=self.path,
        )
        self.assertEqual(snapshot["last_outcome"]["completion_status"], "partly_completed")
        self.assertEqual(snapshot["last_outcome"]["difficulty_categories"], ["pace"])
        self.assertEqual(snapshot["outcome_recording_rate_percent"], 100)
        self.assertEqual(candidates[0]["outcome_id"], snapshot["last_outcome"]["id"])


if __name__ == "__main__":
    unittest.main()
