from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day11-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day11-key")

import class_service  # noqa: E402
import database  # noqa: E402
from class_dashboard_panel import handle_dashboard_callback  # noqa: E402
from class_dashboard_service import class_dashboard_snapshot  # noqa: E402
from day20_migration import SCHEMA_VERSION  # noqa: E402
from feature_flags import FEATURE_ENV_VARS  # noqa: E402
from keyboards import lesson_replace_keyboard, lesson_schedule_keyboard  # noqa: E402
from lesson_history_service import (  # noqa: E402
    _scheduled_date,
    cancel_planned_lesson,
    get_owned_class_lesson,
    lesson_conversion_metrics,
    list_lesson_history,
    mark_lesson_taught,
    schedule_material_lesson,
)


def teacher(identifier: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier, username=f"day11_{identifier}", first_name="Day Eleven",
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


class Day11LessonHistoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="teacheros-day11-")
        self.path = Path(self.temp.name) / "teacheros.db"
        self.db_patch = patch.object(database, "DATABASE_PATH", self.path)
        self.db_patch.start()
        flags = {value: "false" for value in FEATURE_ENV_VARS.values()}
        flags[FEATURE_ENV_VARS["classes"]] = "true"
        flags[FEATURE_ENV_VARS["continuity"]] = "true"
        self.flag_patch = patch.dict(os.environ, flags, clear=False)
        self.flag_patch.start()
        self.owner = teacher(111_001)
        self.other = teacher(111_002)
        self.class_record = class_service.create_class(
            telegram_user=self.owner, display_name="Day 11 Class", level="B1",
            cadence="weekly", goal="Trusted continuity",
        )
        assert self.class_record is not None
        with database.database_connection(self.path) as connection:
            database.ensure_database_user(connection, self.other)
            self.owner_id = int(connection.execute(
                "SELECT user_id FROM classes WHERE id = ?", (self.class_record["id"],)
            ).fetchone()[0])
            self.objective_id = int(connection.execute(
                "INSERT INTO class_objectives (class_id, user_id, objective, priority) "
                "VALUES (?, ?, 'Use polite requests', 60)",
                (self.class_record["id"], self.owner_id),
            ).lastrowid)

    def tearDown(self) -> None:
        self.flag_patch.stop()
        self.db_patch.stop()
        self.temp.cleanup()

    def _lesson(self, title: str) -> int:
        return database.save_generated_material(
            telegram_user=self.owner, material_type="lesson", title=title,
            content="CEFR B1. Timing 45 minutes. Materials board. Instructions included.",
            level="B1", topic="Requests", class_id=int(self.class_record["id"]),
            objective_ids=[self.objective_id],
        )

    def test_schema_v11_is_additive_idempotent_and_auditable(self) -> None:
        database.initialize_database(self.path)
        database.initialize_database(self.path)
        with database.database_connection(self.path) as connection:
            version = int(connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0])
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(class_lessons)")}
            tables = {str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )}
            triggers = {str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )}
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertTrue(
            {"lifecycle_state", "lifecycle_version", "cancelled_at", "origin_key"} <= columns
        )
        self.assertIn("class_lesson_transitions", tables)
        self.assertIn("trg_lesson_material_immutable_v11", triggers)
        self.assertIn("trg_lesson_material_delete_guard_v11", triggers)
        self.assertIn("trg_lesson_lifecycle_transition_v11", triggers)

    def test_generation_creates_only_generated_fact_and_changes_no_progress(self) -> None:
        with database.database_connection(self.path) as connection:
            before = dict(connection.execute(
                "SELECT status, priority, updated_at FROM class_objectives WHERE id = ?",
                (self.objective_id,),
            ).fetchone())
            action_count = int(connection.execute("SELECT COUNT(*) FROM class_action_items").fetchone()[0])
            outcome_count = int(connection.execute("SELECT COUNT(*) FROM lesson_outcomes").fetchone()[0])
        material_id = self._lesson("Generated, not taught")
        history = list_lesson_history(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["lifecycle_state"], "generated")
        self.assertEqual(history[0]["material_id"], material_id)
        self.assertIsNone(class_service.record_lesson_outcome(
            telegram_user_id=self.owner.id,
            class_id=int(self.class_record["id"]),
            class_lesson_id=int(history[0]["id"]),
            result="met",
            database_path=self.path,
        ))
        with database.database_connection(self.path) as connection:
            after = dict(connection.execute(
                "SELECT status, priority, updated_at FROM class_objectives WHERE id = ?",
                (self.objective_id,),
            ).fetchone())
            self.assertEqual(before, after)
            self.assertEqual(int(connection.execute("SELECT COUNT(*) FROM class_action_items").fetchone()[0]), action_count)
            self.assertEqual(int(connection.execute("SELECT COUNT(*) FROM lesson_outcomes").fetchone()[0]), outcome_count)

    def test_all_four_date_choices_are_deterministic(self) -> None:
        base = date(2026, 8, 29)
        self.assertEqual(_scheduled_date("today", "weekly", today=base), "2026-08-29")
        self.assertEqual(_scheduled_date("tomorrow", "weekly", today=base), "2026-08-30")
        self.assertEqual(_scheduled_date("next_class", "weekly", today=base), "2026-09-05")
        self.assertEqual(_scheduled_date("next_class", "twice_weekly", today=base), "2026-09-01")
        self.assertIsNone(_scheduled_date("later", "weekly", today=base))
        with self.assertRaises(ValueError):
            _scheduled_date("guessed", "weekly", today=base)

    def test_duplicate_plan_callbacks_and_replace_are_idempotent(self) -> None:
        first_id = self._lesson("First plan")
        first = schedule_material_lesson(
            telegram_user_id=self.owner.id, material_id=first_id, date_choice="today"
        )
        duplicate = schedule_material_lesson(
            telegram_user_id=self.owner.id, material_id=first_id, date_choice="today"
        )
        self.assertEqual(first["status"], "planned")
        self.assertEqual(duplicate["status"], "already_planned")
        second_id = self._lesson("Replacement plan")
        conflict = schedule_material_lesson(
            telegram_user_id=self.owner.id, material_id=second_id, date_choice="tomorrow"
        )
        self.assertEqual(conflict["status"], "conflict")
        replaced = schedule_material_lesson(
            telegram_user_id=self.owner.id, material_id=second_id,
            date_choice="tomorrow", replace=True,
        )
        self.assertEqual(replaced["status"], "replaced")
        history = list_lesson_history(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        self.assertEqual([item["lifecycle_state"] for item in history], ["cancelled", "planned"])
        self.assertIsNotNone(database.get_user_material(
            telegram_user_id=self.owner.id, material_id=first_id
        ))
        self.assertFalse(class_service.unlink_material_from_class(
            telegram_user_id=self.owner.id,
            material_id=first_id,
            database_path=self.path,
        ))
        metrics = lesson_conversion_metrics(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        self.assertEqual(metrics["generated_to_planned"], 2)
        with database.database_connection(self.path) as connection:
            planned_count = int(connection.execute(
                "SELECT COUNT(*) FROM class_lessons WHERE class_id = ? "
                "AND lifecycle_state = 'planned'", (self.class_record["id"],)
            ).fetchone()[0])
        self.assertEqual(planned_count, 1)

    def test_mark_taught_and_cancel_are_idempotent_and_never_double_count(self) -> None:
        material_id = self._lesson("Taught once")
        planned = schedule_material_lesson(
            telegram_user_id=self.owner.id, material_id=material_id, date_choice="today"
        )["lesson"]
        lesson_id = int(planned["id"])
        taught, changed = mark_lesson_taught(
            telegram_user_id=self.owner.id, lesson_id=lesson_id
        )
        taught_again, changed_again = mark_lesson_taught(
            telegram_user_id=self.owner.id, lesson_id=lesson_id
        )
        self.assertTrue(changed)
        self.assertFalse(changed_again)
        self.assertEqual(taught["id"], taught_again["id"])
        self.assertEqual(taught["lifecycle_state"], "taught")
        cancelled, cancel_changed = cancel_planned_lesson(
            telegram_user_id=self.owner.id, lesson_id=lesson_id
        )
        self.assertFalse(cancel_changed)
        self.assertEqual(cancelled["lifecycle_state"], "taught")
        metrics = lesson_conversion_metrics(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        self.assertEqual(metrics, {"generated_to_planned": 1, "planned_to_taught": 1})
        with database.database_connection(self.path) as connection:
            transitions = int(connection.execute(
                "SELECT COUNT(*) FROM class_lesson_transitions WHERE class_lesson_id = ?",
                (lesson_id,),
            ).fetchone()[0])
        self.assertEqual(transitions, 3)

    def test_cancelled_plan_is_auditable_not_taught_and_keeps_resource(self) -> None:
        material_id = self._lesson("Cancelled plan")
        lesson = schedule_material_lesson(
            telegram_user_id=self.owner.id, material_id=material_id, date_choice="later"
        )["lesson"]
        cancelled, changed = cancel_planned_lesson(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"])
        )
        duplicate, changed_twice = cancel_planned_lesson(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"])
        )
        self.assertTrue(changed)
        self.assertFalse(changed_twice)
        self.assertEqual(cancelled["lifecycle_state"], "cancelled")
        self.assertEqual(duplicate["lifecycle_state"], "cancelled")
        self.assertIsNone(cancelled["taught_at"])
        self.assertFalse(database.delete_user_material(
            telegram_user_id=self.owner.id, material_id=material_id
        ))
        self.assertIsNotNone(database.get_user_material(
            telegram_user_id=self.owner.id, material_id=material_id
        ))

    def test_owner_isolation_and_immutable_material_link(self) -> None:
        first_id = self._lesson("Immutable link")
        second_id = self._lesson("Other resource")
        history = list_lesson_history(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        lesson_id = int(history[0]["id"])
        self.assertIsNone(get_owned_class_lesson(
            telegram_user_id=self.other.id, lesson_id=lesson_id
        ))
        self.assertEqual(list_lesson_history(
            telegram_user_id=self.other.id, class_id=int(self.class_record["id"])
        ), [])
        with self.assertRaises(sqlite3.IntegrityError):
            with database.database_connection(self.path) as connection:
                connection.execute(
                    "UPDATE class_lessons SET material_id = ? WHERE id = ?",
                    (second_id, lesson_id),
                )
        with self.assertRaises(sqlite3.IntegrityError):
            with database.database_connection(self.path) as connection:
                connection.execute(
                    "UPDATE class_lesson_transitions SET reason = 'rewritten' "
                    "WHERE class_lesson_id = ?", (lesson_id,),
                )
        with self.assertRaises(sqlite3.IntegrityError):
            with database.database_connection(self.path) as connection:
                connection.execute(
                    "UPDATE class_lessons SET lifecycle_state = 'taught' WHERE id = ?",
                    (lesson_id,),
                )
        self.assertIsNotNone(database.get_user_material(
            telegram_user_id=self.owner.id, material_id=first_id
        ))

    def test_dashboard_shows_only_the_next_planned_lesson(self) -> None:
        material_id = self._lesson("Dashboard next")
        empty = class_dashboard_snapshot(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        self.assertIsNone(empty["next_planned_lesson"])
        result = schedule_material_lesson(
            telegram_user_id=self.owner.id, material_id=material_id, date_choice="tomorrow"
        )
        snapshot = class_dashboard_snapshot(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        self.assertEqual(snapshot["next_planned_lesson"]["id"], result["lesson"]["id"])
        self.assertEqual(snapshot["next_planned_lesson"]["status"], "planned")
        self.assertEqual(snapshot["history_counts"]["generated"], 0)
        self.assertEqual(snapshot["history_counts"]["planned"], 1)

    async def test_restart_safe_taught_callback_and_compact_date_callbacks(self) -> None:
        material_id = self._lesson("Restart recovery")
        lesson = schedule_material_lesson(
            telegram_user_id=self.owner.id, material_id=material_id, date_choice="today"
        )["lesson"]
        schedule_callbacks = callbacks(lesson_schedule_keyboard(material_id))
        replace_callbacks = callbacks(lesson_replace_keyboard(material_id, "td"))
        self.assertTrue(all(len(value.encode("utf-8")) <= 64 for value in schedule_callbacks + replace_callbacks))
        self.assertEqual(
            {value.rsplit("|", 1)[-1] for value in schedule_callbacks if "|pd|" in value},
            {"td", "tm", "nc", "lt"},
        )
        record = class_service.get_class(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        query = SimpleNamespace(
            answer=AsyncMock(), edit_message_text=AsyncMock(),
        )
        context = SimpleNamespace(user_data={})  # simulates a bot restart
        await handle_dashboard_callback(
            SimpleNamespace(callback_query=query, effective_user=self.owner), context,
            action="taught", object_id=b36(int(lesson["id"])),
            revision_text=b36(int(record["revision"])),
        )
        query.edit_message_text.assert_awaited_once()
        self.assertIn("Marked as taught", query.edit_message_text.await_args.args[0])
        saved = get_owned_class_lesson(
            telegram_user_id=self.owner.id, lesson_id=int(lesson["id"])
        )
        self.assertEqual(saved["lifecycle_state"], "taught")

    def test_empty_history_and_cross_owner_scheduling_fail_closed(self) -> None:
        self.assertEqual(list_lesson_history(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        ), [])
        material_id = self._lesson("Private material")
        result = schedule_material_lesson(
            telegram_user_id=self.other.id, material_id=material_id, date_choice="today"
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(list_lesson_history(
            telegram_user_id=self.other.id, class_id=int(self.class_record["id"])
        ), [])


if __name__ == "__main__":
    unittest.main()
