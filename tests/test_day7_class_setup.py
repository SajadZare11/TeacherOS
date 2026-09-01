from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day7-token-not-used")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day7-key-not-used")

import class_service  # noqa: E402
import database  # noqa: E402
from class_panel import class_callback  # noqa: E402
from class_setup_panel import get_class_setup_text  # noqa: E402
from class_setup_service import (  # noqa: E402
    ClassLimitReachedError,
    complete_setup,
    discard_setup_draft,
    get_setup_draft,
    save_setup_draft,
    start_setup_draft,
)
from day25_migration import SCHEMA_VERSION  # noqa: E402
from feature_flags import FEATURE_ENV_VARS  # noqa: E402
from keyboards import class_list_keyboard  # noqa: E402
from subscription_service import class_creation_access_for_user  # noqa: E402


def user(user_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        username=f"day7_{user_id}",
        first_name="Setup",
        last_name="Teacher",
        language_code="en",
    )


def query(data: str) -> SimpleNamespace:
    return SimpleNamespace(data=data, answer=AsyncMock(), edit_message_text=AsyncMock())


def callback_values(markup: object) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


COMPLETE_PAYLOAD = {
    "display_name": "B1 Evening",
    "level_choice": "not_sure",
    "age_group_choice": "adults",
    "learner_count_band_choice": "6_12",
    "duration_choice": 60,
    "goal_choice": "conversation",
    "weak_areas": ["spk", "pron"],
    "coursebook_state": "skipped",
    "coursebook": None,
    "coursebook_unit": None,
    "equipment": ["board", "audio"],
    "teaching_preferences": ["comm"],
}


class Day7SetupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day7-")
        self.database_path = Path(self.temp_dir.name) / "setup.db"
        self.database_patch = patch.object(database, "DATABASE_PATH", self.database_path)
        self.database_patch.start()
        flags = {env_name: "false" for env_name in FEATURE_ENV_VARS.values()}
        flags[FEATURE_ENV_VARS["classes"]] = "true"
        self.flag_patch = patch.dict(os.environ, flags, clear=False)
        self.flag_patch.start()
        self.teacher = user(71001)

    def tearDown(self) -> None:
        self.flag_patch.stop()
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def _complete_draft(self, teacher: SimpleNamespace | None = None) -> dict[str, object]:
        actor = teacher or self.teacher
        draft = start_setup_draft(telegram_user=actor)
        updated = save_setup_draft(
            telegram_user_id=actor.id,
            expected_revision=draft["revision"],
            step="review",
            payload=dict(COMPLETE_PAYLOAD),
        )
        self.assertIsNotNone(updated)
        return updated

    async def _route(self, data: str, context: SimpleNamespace | None = None, actor: SimpleNamespace | None = None):
        callback_query = query(data)
        route_context = context or SimpleNamespace(user_data={})
        await class_callback(
            SimpleNamespace(callback_query=callback_query, effective_user=actor or self.teacher),
            route_context,
        )
        callback_query.answer.assert_awaited_once()
        callback_query.edit_message_text.assert_awaited_once()
        return callback_query, route_context

    def test_current_schema_is_idempotent_and_has_durable_setup_fields(self) -> None:
        database.initialize_database(self.database_path)
        database.initialize_database(self.database_path)
        with database.database_connection(self.database_path) as connection:
            self.assertEqual(
                connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0],
                SCHEMA_VERSION,
            )
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("class_setup_drafts", tables)
            columns = [row[1] for row in connection.execute("PRAGMA table_info(classes)")]
            for column in (
                "lesson_duration_minutes", "weak_areas_json", "coursebook",
                "coursebook_unit", "equipment_json", "teaching_preferences_json",
                "setup_profile_json", "setup_idempotency_key", "setup_draft_id",
            ):
                self.assertEqual(columns.count(column), 1)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_completion_is_idempotent_and_unknown_remains_explicit(self) -> None:
        draft = self._complete_draft()
        first, created = complete_setup(
            telegram_user_id=self.teacher.id,
            draft_id=draft["id"],
        )
        second, created_again = complete_setup(
            telegram_user_id=self.teacher.id,
            draft_id=draft["id"],
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["id"], second["id"])
        self.assertIsNone(first["level"])
        profile = json.loads(first["setup_profile_json"])
        self.assertEqual(profile["level_choice"], "not_sure")
        self.assertEqual(profile["coursebook_state"], "skipped")
        self.assertIsNone(get_setup_draft(telegram_user_id=self.teacher.id))
        with database.database_connection(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM classes").fetchone()[0], 1)
            names = [row[0] for row in connection.execute("SELECT event_name FROM product_events ORDER BY id")]
            self.assertEqual(names, ["class_setup_started", "class_setup_completed"])

    async def test_duplicate_save_callbacks_return_the_same_class(self) -> None:
        self._complete_draft()
        review_query, _ = await self._route("v1|cl|resume|0|0")
        review_markup = review_query.edit_message_text.await_args.kwargs["reply_markup"]
        save_callback = next(
            value for value in callback_values(review_markup) if "|save|" in value
        )

        first_query, _ = await self._route(save_callback)
        second_query, _ = await self._route(save_callback)

        self.assertIn("Class created", first_query.edit_message_text.await_args.args[0])
        self.assertIn("Class already created", second_query.edit_message_text.await_args.args[0])
        with database.database_connection(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM classes").fetchone()[0], 1)
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM product_events WHERE event_name='class_setup_completed'"
                ).fetchone()[0],
                1,
            )

    def test_interrupted_draft_resumes_and_discard_records_only_field_name(self) -> None:
        draft = start_setup_draft(telegram_user=self.teacher)
        payload = dict(draft["payload"])
        payload["display_name"] = "Resume Me"
        saved = save_setup_draft(
            telegram_user_id=self.teacher.id,
            expected_revision=draft["revision"],
            step="level",
            payload=payload,
        )
        resumed = get_setup_draft(telegram_user_id=self.teacher.id)
        self.assertEqual(resumed["step"], "level")
        self.assertEqual(resumed["payload"]["display_name"], "Resume Me")
        self.assertTrue(discard_setup_draft(telegram_user_id=self.teacher.id))
        self.assertIsNone(get_setup_draft(telegram_user_id=self.teacher.id))
        with database.database_connection(self.database_path) as connection:
            event = connection.execute(
                "SELECT properties_json FROM product_events WHERE event_name='class_setup_abandoned'"
            ).fetchone()
            properties = json.loads(event[0])
            self.assertEqual(properties["abandoned_at_field"], "level")
            self.assertIsInstance(properties["setup_seconds"], int)

    def test_central_entitlement_limit_preserves_blocked_draft(self) -> None:
        first_draft = self._complete_draft()
        complete_setup(telegram_user_id=self.teacher.id, draft_id=first_draft["id"])
        second_draft = self._complete_draft()
        with patch.dict(
            os.environ,
            {FEATURE_ENV_VARS["entitlements"]: "true"},
            clear=False,
        ):
            access = class_creation_access_for_user(self.teacher.id)
            self.assertFalse(access["allowed"])
            self.assertEqual(access["class_limit"], 1)
            with self.assertRaises(ClassLimitReachedError):
                complete_setup(
                    telegram_user_id=self.teacher.id,
                    draft_id=second_draft["id"],
                )
        self.assertIsNotNone(get_setup_draft(telegram_user_id=self.teacher.id))

    async def test_setup_entry_offers_template_only_after_first_class(self) -> None:
        first_query, _ = await self._route("v1|cl|new|0|0")
        first_markup = first_query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertNotIn("v1|cl|template|0|0", callback_values(first_markup))
        draft = self._complete_draft()
        complete_setup(telegram_user_id=self.teacher.id, draft_id=draft["id"])
        next_query, _ = await self._route("v1|cl|new|0|0")
        next_markup = next_query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertIn("v1|cl|template|0|0", callback_values(next_markup))

    async def test_name_input_is_one_short_non_sensitive_phrase(self) -> None:
        _, route_context = await self._route("v1|cl|begin|0|0")
        bad_message = SimpleNamespace(text="student@example.com", reply_text=AsyncMock())
        await get_class_setup_text(
            SimpleNamespace(message=bad_message, effective_user=self.teacher),
            route_context,
        )
        bad_text = bad_message.reply_text.await_args.args[0]
        self.assertIn("non-sensitive phrase", bad_text)
        self.assertEqual(get_setup_draft(telegram_user_id=self.teacher.id)["step"], "name")

        good_message = SimpleNamespace(text="  B1   Evening  ", reply_text=AsyncMock())
        await get_class_setup_text(
            SimpleNamespace(message=good_message, effective_user=self.teacher),
            route_context,
        )
        self.assertEqual(get_setup_draft(telegram_user_id=self.teacher.id)["step"], "level")
        self.assertEqual(
            get_setup_draft(telegram_user_id=self.teacher.id)["payload"]["display_name"],
            "B1 Evening",
        )

    async def test_every_setup_screen_has_back_draft_cancel_and_compact_callbacks(self) -> None:
        draft = start_setup_draft(telegram_user=self.teacher)
        payload = dict(COMPLETE_PAYLOAD)
        for step in (
            "name", "level", "age", "size", "duration", "goal", "weak",
            "book", "equipment", "preference", "review",
        ):
            current = get_setup_draft(telegram_user_id=self.teacher.id)
            updated = save_setup_draft(
                telegram_user_id=self.teacher.id,
                expected_revision=current["revision"],
                step=step,
                payload=payload,
            )
            route_query, _ = await self._route("v1|cl|resume|0|0")
            markup = route_query.edit_message_text.await_args.kwargs["reply_markup"]
            values = callback_values(markup)
            self.assertTrue(any("|back|" in value for value in values), step)
            self.assertTrue(any("|draft|" in value for value in values), step)
            self.assertTrue(any("|cancel|" in value for value in values), step)
            for value in values:
                self.assertLessEqual(len(value.encode("utf-8")), 64, value)

    async def test_final_summary_uses_readable_labels_and_edits_every_field(self) -> None:
        self._complete_draft()
        route_query, _ = await self._route("v1|cl|resume|0|0")
        text = route_query.edit_message_text.await_args.args[0]
        markup = route_query.edit_message_text.await_args.kwargs["reply_markup"]

        self.assertIn("Duration: 60 minutes", text)
        self.assertIn("Weak areas: Speaking, Pronunciation", text)
        self.assertIn("Equipment: Board, Speakers/audio", text)
        self.assertIn("Preference: Communicative", text)
        self.assertNotIn("Weak areas: spk", text)
        self.assertEqual(
            sum("|edit|" in value for value in callback_values(markup)),
            10,
        )

    def test_draft_appears_in_my_classes_navigation(self) -> None:
        start_setup_draft(telegram_user=self.teacher)
        markup = class_list_keyboard([], archived=False, has_draft=True)
        self.assertIn("v1|cl|resume|0|0", callback_values(markup))


if __name__ == "__main__":
    unittest.main(verbosity=2)
