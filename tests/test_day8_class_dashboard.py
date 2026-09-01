from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day8-token-not-used")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day8-key-not-used")

import class_service  # noqa: E402
import database  # noqa: E402
from class_dashboard_keyboards import (  # noqa: E402
    class_dashboard_keyboard,
    class_profile_keyboard,
    today_queue_keyboard,
)
from class_dashboard_service import (  # noqa: E402
    class_dashboard_snapshot,
    create_class_action_item,
    resolve_class_action_item,
    today_queue,
    update_profile_field,
)
from class_panel import class_callback  # noqa: E402
from class_setup_service import start_setup_draft  # noqa: E402
from day28_migration import SCHEMA_VERSION  # noqa: E402
from feature_flags import FEATURE_ENV_VARS  # noqa: E402


def user(user_id: int, name: str = "Dashboard") -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        username=f"day8_{user_id}",
        first_name=name,
        last_name="Teacher",
        language_code="en",
    )


def query(data: str) -> SimpleNamespace:
    return SimpleNamespace(data=data, answer=AsyncMock(), edit_message_text=AsyncMock())


def callbacks(markup: object) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def labels(markup: object) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def b36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = ""
    while value:
        value, remainder = divmod(value, 36)
        result = alphabet[remainder] + result
    return result or "0"


class Day8ClassDashboardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day8-")
        self.database_path = Path(self.temp_dir.name) / "dashboard.db"
        self.database_patch = patch.object(database, "DATABASE_PATH", self.database_path)
        self.database_patch.start()
        flags = {name: "false" for name in FEATURE_ENV_VARS.values()}
        flags[FEATURE_ENV_VARS["classes"]] = "true"
        self.flag_patch = patch.dict(os.environ, flags, clear=False)
        self.flag_patch.start()
        self.owner = user(81001, "Owner")
        self.other = user(81002, "Other")
        self.class_record = class_service.create_class(
            telegram_user=self.owner,
            display_name="B1 Evening",
            level="B1",
            age_group="adults",
            learner_count_band="6_12",
            goal="conversation practice",
        )

    def tearDown(self) -> None:
        self.flag_patch.stop()
        self.database_patch.stop()
        self.temp_dir.cleanup()

    async def _route(
        self,
        data: str,
        *,
        actor: SimpleNamespace | None = None,
        context: SimpleNamespace | None = None,
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        callback_query = query(data)
        route_context = context or SimpleNamespace(user_data={})
        await class_callback(
            SimpleNamespace(
                callback_query=callback_query,
                effective_user=actor or self.owner,
            ),
            route_context,
        )
        callback_query.answer.assert_awaited_once()
        callback_query.edit_message_text.assert_awaited_once()
        return callback_query, route_context

    def _lesson(self, title: str, status: str, scheduled: str | None = None) -> dict[str, object]:
        lesson = class_service.create_class_lesson(
            telegram_user_id=self.owner.id,
            class_id=self.class_record["id"],
            title=title,
            status=status,
            scheduled_for=scheduled,
        )
        self.assertIsNotNone(lesson)
        return lesson

    def _material(self) -> int:
        with database.database_connection(self.database_path) as connection:
            user_id = database.ensure_database_user(connection, self.owner)
            cursor = connection.execute(
                """
                INSERT INTO materials (user_id, material_type, title, content, metadata_json)
                VALUES (?, 'lesson', 'Linked resource', 'Safe content', '{}')
                """,
                (user_id,),
            )
            return int(cursor.lastrowid)

    def test_schema_v8_is_idempotent_and_owner_scoped(self) -> None:
        database.initialize_database(self.database_path)
        database.initialize_database(self.database_path)
        with database.database_connection(self.database_path) as connection:
            self.assertEqual(
                connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0],
                SCHEMA_VERSION,
            )
            columns = [row[1] for row in connection.execute("PRAGMA table_info(classes)")]
            self.assertEqual(columns.count("last_active_at"), 1)
            action_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(class_action_items)")
            }
            self.assertTrue(
                {"class_id", "user_id", "item_type", "source_key", "status", "due_at"}
                <= action_columns
            )
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_populated_v7_upgrade_backfills_last_active_without_losing_class(self) -> None:
        class_id = int(self.class_record["id"])
        with database.database_connection(self.database_path) as connection:
            for trigger in (
                "trg_next_lesson_source_owner_insert_v13",
                "trg_next_lesson_source_owner_update_v13",
                "trg_next_lesson_owner_insert_v13",
                "trg_next_lesson_owner_update_v13",
                "trg_next_lesson_plan_source_owner_insert_v13",
                "trg_next_lesson_plan_source_owner_update_v13",
                "trg_next_lesson_plan_owner_insert_v13",
                "trg_next_lesson_plan_owner_update_v13",
                "trg_next_lesson_immutable_saved_update_v13",
                "trg_next_lesson_plan_immutable_update_v13",
                "trg_next_lesson_plan_source_immutable_update_v13",
                "trg_classes_last_active_insert",
            ):
                connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            for table in (
                "next_lesson_plan_sources",
                "next_lesson_plans",
                "next_lesson_recommendation_sources",
                "next_lesson_recommendations",
            ):
                connection.execute(f"DROP TABLE IF EXISTS {table}")
            connection.execute("DROP INDEX IF EXISTS idx_classes_owner_last_active")
            connection.execute("DROP TABLE class_action_items")
            connection.execute("ALTER TABLE classes DROP COLUMN last_active_at")
            connection.execute("DELETE FROM schema_versions WHERE version >= 8")

        database.initialize_database(self.database_path)
        with database.database_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT display_name, last_active_at FROM classes WHERE id = ?",
                (class_id,),
            ).fetchone()
            self.assertEqual(row["display_name"], "B1 Evening")
            self.assertTrue(str(row["last_active_at"]).endswith("Z"))
            self.assertEqual(
                connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0],
                SCHEMA_VERSION,
            )
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_snapshot_surfaces_every_compact_dashboard_fact(self) -> None:
        self._lesson("Next speaking lesson", "planned", "2026-08-29T10:00:00Z")
        taught = self._lesson("Past lesson", "taught")
        class_service.record_lesson_outcome(
            telegram_user_id=self.owner.id,
            class_id=self.class_record["id"],
            class_lesson_id=taught["id"],
            result="partly_met",
            confidence="medium",
            support_needed="some",
            status="approved",
        )
        create_class_action_item(
            telegram_user_id=self.owner.id,
            class_id=self.class_record["id"],
            item_type="review_due",
            source_key="outcome-1",
            due_at="2026-01-01T00:00:00Z",
        )
        create_class_action_item(
            telegram_user_id=self.owner.id,
            class_id=self.class_record["id"],
            item_type="analysis_approval",
            source_key="analysis-1",
        )

        snapshot = class_dashboard_snapshot(
            telegram_user_id=self.owner.id,
            class_id=self.class_record["id"],
        )
        self.assertEqual(snapshot["next_planned_lesson"]["title"], "Next speaking lesson")
        self.assertEqual(snapshot["last_outcome"]["result"], "partly_met")
        self.assertEqual(snapshot["unresolved_difficulty"]["support_needed"], "some")
        self.assertEqual(snapshot["due_review_count"], 1)
        self.assertEqual(snapshot["pending_analysis_count"], 1)
        self.assertFalse(snapshot["no_history"])

        class_service.record_lesson_outcome(
            telegram_user_id=self.owner.id,
            class_id=self.class_record["id"],
            class_lesson_id=taught["id"],
            result="met",
            support_needed="none",
            status="approved",
        )
        resolved = class_dashboard_snapshot(
            telegram_user_id=self.owner.id,
            class_id=self.class_record["id"],
        )
        self.assertEqual(resolved["last_outcome"]["result"], "met")
        self.assertIsNone(resolved["unresolved_difficulty"])

    def test_action_items_reject_descriptive_or_sensitive_source_text(self) -> None:
        with self.assertRaises(ValueError):
            create_class_action_item(
                telegram_user_id=self.owner.id,
                class_id=self.class_record["id"],
                item_type="review_due",
                source_key="Student Jane needs grammar review",
            )
        with self.assertRaises(ValueError):
            create_class_action_item(
                telegram_user_id=self.owner.id,
                class_id=self.class_record["id"],
                item_type="review_due",
                source_key="review-safe",
                due_at="tomorrow afternoon",
            )

    def test_action_item_resolution_is_owner_scoped_and_idempotent(self) -> None:
        item = create_class_action_item(
            telegram_user_id=self.owner.id,
            class_id=self.class_record["id"],
            item_type="analysis_approval",
            source_key="analysis-resolution-1",
        )
        self.assertFalse(
            resolve_class_action_item(
                telegram_user_id=self.other.id,
                item_id=item["id"],
                resolution="completed",
            )
        )
        self.assertTrue(
            resolve_class_action_item(
                telegram_user_id=self.owner.id,
                item_id=item["id"],
                resolution="completed",
            )
        )
        self.assertTrue(
            resolve_class_action_item(
                telegram_user_id=self.owner.id,
                item_id=item["id"],
                resolution="completed",
            )
        )
        self.assertNotIn(
            "pending_analysis",
            [entry["kind"] for entry in today_queue(telegram_user_id=self.owner.id)],
        )

    def test_today_queue_contains_all_five_states_in_priority_order(self) -> None:
        start_setup_draft(telegram_user=self.owner)
        self._lesson("Planned tomorrow", "planned", "2026-08-29T10:00:00Z")
        self._lesson("Needs a check-in", "taught")
        create_class_action_item(
            telegram_user_id=self.owner.id,
            class_id=self.class_record["id"],
            item_type="analysis_approval",
            source_key="analysis-queue",
        )
        create_class_action_item(
            telegram_user_id=self.owner.id,
            class_id=self.class_record["id"],
            item_type="review_due",
            source_key="review-queue",
            due_at="2026-01-01T00:00:00Z",
        )
        create_class_action_item(
            telegram_user_id=self.owner.id,
            class_id=self.class_record["id"],
            item_type="review_due",
            source_key="future-review",
            due_at="2099-01-01T00:00:00Z",
        )

        items = today_queue(telegram_user_id=self.owner.id)
        self.assertEqual(
            [item["kind"] for item in items],
            [
                "unfinished_setup",
                "missing_outcome",
                "pending_analysis",
                "planned_lesson",
                "review_due",
            ],
        )

    async def test_dashboard_is_phone_sized_and_has_one_obvious_primary_action(self) -> None:
        class_id = int(self.class_record["id"])
        revision = int(self.class_record["revision"])
        route_query, route_context = await self._route(
            f"v1|cl|open|{b36(class_id)}|{b36(revision)}"
        )
        text = route_query.edit_message_text.await_args.args[0]
        markup = route_query.edit_message_text.await_args.kwargs["reply_markup"]

        self.assertLess(len(text), 700)
        self.assertTrue(text.startswith("🏫 Active class: B1 Evening"))
        self.assertIn("🎯 NEXT: Plan Next Lesson", text)
        self.assertIn("No history yet", text)
        self.assertEqual(labels(markup)[0], "🎯 Plan Next Lesson")
        for label in (
            "🔬 Analyze Work", "🧰 Create Materials", "✅ Record Outcome",
            "📈 Progress", "📁 Library", "👤 Profile",
        ):
            self.assertIn(label, labels(markup))
        self.assertNotIn("Last active:", text)

        details_callback = next(value for value in callbacks(markup) if "|details|" in value)
        details_query, _ = await self._route(details_callback, context=route_context)
        details_text = details_query.edit_message_text.await_args.args[0]
        self.assertIn("Last active:", details_text)

    def test_all_ten_profile_fields_update_one_at_a_time_and_reject_cross_owner(self) -> None:
        class_id = int(self.class_record["id"])
        values = (
            ("display_name", "  B2   Morning  "),
            ("level", "not_sure"),
            ("age_group", "teens"),
            ("learner_count_band", "13_20"),
            ("lesson_duration_minutes", 90),
            ("goal", "exam_preparation"),
            ("weak_areas", ["gram", "write"]),
            (
                "coursebook",
                {"coursebook_state": "provided", "coursebook": "English File", "coursebook_unit": "Unit 4"},
            ),
            ("equipment", ["board", "proj"]),
            ("teaching_preferences", ["struct"]),
        )
        current = self.class_record
        for field, value in values:
            updated = update_profile_field(
                telegram_user_id=self.owner.id,
                class_id=class_id,
                field=field,
                value=value,
                expected_revision=int(current["revision"]),
            )
            self.assertIsNotNone(updated, field)
            self.assertEqual(int(updated["revision"]), int(current["revision"]) + 1)
            current = updated
        self.assertEqual(current["display_name"], "B2 Morning")
        self.assertIsNone(current["level"])
        self.assertEqual(current["coursebook_unit"], "Unit 4")
        profile = json.loads(current["setup_profile_json"])
        self.assertEqual(profile["level_choice"], "not_sure")
        self.assertEqual(profile["weak_areas"], ["gram", "write"])
        self.assertIsNone(
            update_profile_field(
                telegram_user_id=self.other.id,
                class_id=class_id,
                field="goal",
                value="travel_english",
                expected_revision=int(current["revision"]),
            )
        )

    async def test_profile_choice_and_multi_edit_callbacks_update_only_after_save(self) -> None:
        class_id = int(self.class_record["id"])
        revision = int(self.class_record["revision"])
        open_query, route_context = await self._route(
            f"v1|cl|open|{b36(class_id)}|{b36(revision)}"
        )
        profile_callback = next(
            value
            for value in callbacks(open_query.edit_message_text.await_args.kwargs["reply_markup"])
            if "|profile|" in value
        )
        profile_query, route_context = await self._route(
            profile_callback, context=route_context
        )
        level_edit = next(
            value
            for value in callbacks(profile_query.edit_message_text.await_args.kwargs["reply_markup"])
            if "|pfedit|lv|" in value
        )
        level_query, route_context = await self._route(level_edit, context=route_context)
        level_callbacks = callbacks(
            level_query.edit_message_text.await_args.kwargs["reply_markup"]
        )
        self.assertTrue(
            any("|edset|lvns|" in value for value in level_callbacks),
            level_callbacks,
        )
        not_sure = next(value for value in level_callbacks if "|edset|lvns|" in value)
        updated_query, route_context = await self._route(not_sure, context=route_context)
        self.assertIn("Profile field updated", updated_query.edit_message_text.await_args.args[0])
        after_level = class_service.get_class(
            telegram_user_id=self.owner.id, class_id=class_id
        )
        self.assertIsNone(after_level["level"])

        preference_edit = next(
            value
            for value in callbacks(updated_query.edit_message_text.await_args.kwargs["reply_markup"])
            if "|pfedit|pf|" in value
        )
        preference_query, route_context = await self._route(
            preference_edit, context=route_context
        )
        toggle = next(
            value
            for value in callbacks(preference_query.edit_message_text.await_args.kwargs["reply_markup"])
            if "|edmulti|pfstruct|" in value
        )
        toggled_query, route_context = await self._route(toggle, context=route_context)
        before_save = class_service.get_class(
            telegram_user_id=self.owner.id, class_id=class_id
        )
        self.assertEqual(before_save["revision"], after_level["revision"])
        save = next(
            value
            for value in callbacks(toggled_query.edit_message_text.await_args.kwargs["reply_markup"])
            if "|edsave|pf|" in value
        )
        await self._route(save, context=route_context)
        after_save = class_service.get_class(
            telegram_user_id=self.owner.id, class_id=class_id
        )
        self.assertEqual(
            json.loads(after_save["setup_profile_json"])["teaching_preferences"],
            ["struct"],
        )
        self.assertEqual(int(after_save["revision"]), int(after_level["revision"]) + 1)

    async def test_archive_restore_confirmation_preserves_every_linked_record(self) -> None:
        class_id = int(self.class_record["id"])
        material_id = self._material()
        self.assertTrue(
            class_service.link_material_to_class(
                telegram_user_id=self.owner.id,
                material_id=material_id,
                class_id=class_id,
            )
        )
        lesson = self._lesson("Preserved lesson", "taught")
        class_service.record_lesson_outcome(
            telegram_user_id=self.owner.id,
            class_id=class_id,
            class_lesson_id=lesson["id"],
            result="met",
            status="approved",
        )
        create_class_action_item(
            telegram_user_id=self.owner.id,
            class_id=class_id,
            item_type="review_due",
            source_key="preserved-review",
        )
        route_context = SimpleNamespace(
            user_data={
                "active_class": {
                    "id": class_id,
                    "display_name": self.class_record["display_name"],
                    "revision": self.class_record["revision"],
                }
            }
        )
        ask = f"v1|cl|archask|{b36(class_id)}|{b36(int(self.class_record['revision']))}"
        ask_query, route_context = await self._route(ask, context=route_context)
        self.assertIn("every linked material", ask_query.edit_message_text.await_args.args[0])
        self.assertEqual(
            class_service.get_class(telegram_user_id=self.owner.id, class_id=class_id)["status"],
            "active",
        )
        yes_callback = next(
            value
            for value in callbacks(ask_query.edit_message_text.await_args.kwargs["reply_markup"])
            if "|archyes|" in value
        )
        await self._route(yes_callback, context=route_context)
        archived = class_service.get_class(telegram_user_id=self.owner.id, class_id=class_id)
        self.assertEqual(archived["status"], "archived")
        with database.database_connection(self.database_path) as connection:
            before_restore = {
                table: connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE class_id = ?", (class_id,)
                ).fetchone()[0]
                for table in ("materials", "class_lessons", "lesson_outcomes", "class_action_items")
            }
        restore_ask = f"v1|cl|restask|{b36(class_id)}|{b36(int(archived['revision']))}"
        restore_query, restore_context = await self._route(restore_ask)
        self.assertIn("returns to the active workspace", restore_query.edit_message_text.await_args.args[0])
        self.assertEqual(
            class_service.get_class(telegram_user_id=self.owner.id, class_id=class_id)["status"],
            "archived",
        )
        restore_yes = next(
            value
            for value in callbacks(restore_query.edit_message_text.await_args.kwargs["reply_markup"])
            if "|restyes|" in value
        )
        await self._route(restore_yes, context=restore_context)
        restored = class_service.get_class(
            telegram_user_id=self.owner.id, class_id=class_id
        )
        self.assertEqual(restored["status"], "active")
        with database.database_connection(self.database_path) as connection:
            after_restore = {
                table: connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE class_id = ?", (class_id,)
                ).fetchone()[0]
                for table in before_restore
            }
        self.assertEqual(before_restore, after_restore)

    def test_dashboard_keyboards_are_compact_and_have_safe_escapes(self) -> None:
        markups = (
            class_dashboard_keyboard(9_223_372_036_854_775_807, 2_176_782_335),
            class_profile_keyboard(9_223_372_036_854_775_807, 2_176_782_335, archived=False),
            today_queue_keyboard([]),
        )
        for markup in markups:
            values = callbacks(markup)
            self.assertTrue(any("|home|" in value or "|list|" in value for value in values))
            for value in values:
                self.assertLessEqual(len(value.encode("utf-8")), 64, value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
