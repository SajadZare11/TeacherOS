from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day6-token-not-used")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day6-key-not-used")

import class_service  # noqa: E402
import database  # noqa: E402
from class_panel import class_callback, home_callback  # noqa: E402
from feature_flags import FEATURE_ENV_VARS  # noqa: E402
from keyboards import (  # noqa: E402
    analyze_picker_keyboard,
    class_detail_keyboard,
    class_intro_keyboard,
    class_linked_back_keyboard,
    class_list_keyboard,
    class_recovery_keyboard,
    quick_create_keyboard,
    start_menu_keyboard,
)
from home_ui import teacheros_home_text  # noqa: E402


CALLBACK_CONTRACT = re.compile(
    r"^v1\|[a-z]{2,4}\|[a-z0-9]{1,8}\|[0-9a-z]{1,13}\|[0-9a-z]{1,6}$"
)


def user(user_id: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        username=f"day6_teacher_{user_id}",
        first_name=name,
        last_name="Teacher",
        language_code="en",
    )


def callbacks(markup: object) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def query(data: str) -> SimpleNamespace:
    return SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )


def context() -> SimpleNamespace:
    return SimpleNamespace(user_data={})


class Day6NavigationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day6-navigation-")
        self.database_path = Path(self.temp_dir.name) / "navigation.db"
        self.database_patch = patch.object(database, "DATABASE_PATH", self.database_path)
        self.database_patch.start()
        flag_values = {env_name: "false" for env_name in FEATURE_ENV_VARS.values()}
        flag_values[FEATURE_ENV_VARS["classes"]] = "true"
        self.flag_patch = patch.dict(os.environ, flag_values, clear=False)
        self.flag_patch.start()
        self.owner = user(61001, "Owner")
        self.other = user(61002, "Other")
        self.active = class_service.create_class(
            telegram_user=self.owner,
            display_name="B1 Evening Group",
            level="B1",
            goal="Build speaking confidence",
        )
        self.archived = class_service.create_class(
            telegram_user=self.owner,
            display_name="Archived Saturday Group",
            level="A2",
        )
        class_service.archive_class(
            telegram_user_id=self.owner.id,
            class_id=self.archived["id"],
        )
        self.archived = class_service.get_class(
            telegram_user_id=self.owner.id,
            class_id=self.archived["id"],
        )

    def tearDown(self) -> None:
        self.flag_patch.stop()
        self.database_patch.stop()
        self.temp_dir.cleanup()

    async def _class_route(
        self,
        data: str,
        *,
        actor: SimpleNamespace | None = None,
        state: SimpleNamespace | None = None,
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        callback_query = query(data)
        route_context = state or context()
        update = SimpleNamespace(
            callback_query=callback_query,
            effective_user=actor or self.owner,
        )
        await class_callback(update, route_context)
        callback_query.answer.assert_awaited_once()
        callback_query.edit_message_text.assert_awaited_once()
        return callback_query, route_context

    def test_flagged_home_and_quick_create_preserve_every_legacy_callback(self) -> None:
        home_callbacks = callbacks(start_menu_keyboard())
        self.assertEqual(
            home_callbacks,
            [
                "v1|cl|list|0|0",
                "home_quick",
                "home_analyze",
                "search_start",
                "account_home",
            ],
        )
        quick_callbacks = callbacks(quick_create_keyboard())
        self.assertEqual(
            quick_callbacks[:4],
            ["lesson", "activity_start", "worksheet_start", "quiz_start"],
        )
        self.assertIn("recurring teaching", teacheros_home_text("Plan: Free"))
        self.assertIn("one-off work", teacheros_home_text("Plan: Free"))

        source = (BACKEND_DIR / "main.py").read_text(encoding="utf-8")
        required_routes = (
            'pattern=r"^lesson(?:$|_)"',
            'pattern=r"^activity_"',
            'pattern=r"^worksheet_"',
            'pattern=r"^quiz_"',
            'pattern=r"^search_"',
            'pattern=r"^account_"',
            'pattern=r"^home_"',
            'pattern=r"^v1\\|(?:cl|rc)\\|"',
        )
        for route in required_routes:
            self.assertIn(route, source)

    def test_every_legacy_main_menu_return_uses_flag_aware_home_copy(self) -> None:
        return_modules = (
            "account_panel.py",
            "activity_generator.py",
            "admin_panel.py",
            "lesson_planner.py",
            "library_search.py",
            "payment_panel.py",
            "quiz_generator.py",
            "teacher_library.py",
            "usage_tracking.py",
            "worksheet_generator.py",
        )
        stale_copy = "Choose what you'd like to create today."
        for filename in return_modules:
            source = (BACKEND_DIR / filename).read_text(encoding="utf-8")
            self.assertIn("teacheros_home_text()", source, filename)
            self.assertNotIn(stale_copy, source, filename)

    async def test_quick_create_and_analyze_home_buttons_have_complete_routes(self) -> None:
        quick_query = query("home_quick")
        quick_context = context()
        await home_callback(
            SimpleNamespace(callback_query=quick_query, effective_user=self.owner),
            quick_context,
        )
        quick_query.answer.assert_awaited_once()
        quick_text = quick_query.edit_message_text.await_args.args[0]
        quick_markup = quick_query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertIn("one-off", quick_text)
        self.assertEqual(
            callbacks(quick_markup)[:4],
            ["lesson", "activity_start", "worksheet_start", "quiz_start"],
        )

        analyze_query = query("home_analyze")
        await home_callback(
            SimpleNamespace(callback_query=analyze_query, effective_user=self.owner),
            context(),
        )
        analyze_query.answer.assert_awaited_once()
        analyze_text = analyze_query.edit_message_text.await_args.args[0]
        analyze_markup = analyze_query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertIn("Choose an active class first", analyze_text)
        self.assertTrue(any("|analyze|" in value for value in callbacks(analyze_markup)))
        self.assertNotIn("Archived Saturday Group", analyze_text)

    async def test_active_archived_empty_and_intro_routes_are_helpful(self) -> None:
        active_query, _ = await self._class_route("v1|cl|list|0|0")
        active_text = active_query.edit_message_text.await_args.args[0]
        active_markup = active_query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertIn("My Classes", active_text)
        self.assertIn("recurring", active_text)
        self.assertTrue(any("|open|" in value for value in callbacks(active_markup)))

        archived_query, _ = await self._class_route("v1|cl|archive|0|0")
        archived_text = archived_query.edit_message_text.await_args.args[0]
        archived_markup = archived_query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertIn("Archived Classes", archived_text)
        self.assertTrue(any("|open|" in value for value in callbacks(archived_markup)))

        intro_query, _ = await self._class_route("v1|cl|new|0|0")
        intro_text = intro_query.edit_message_text.await_args.args[0]
        self.assertIn("recurring", intro_text)
        self.assertIn("one-off", intro_text)
        self.assertIn("never student names", intro_text)

        class_service.archive_class(
            telegram_user_id=self.owner.id,
            class_id=self.active["id"],
        )
        empty_query, _ = await self._class_route("v1|cl|list|0|0")
        empty_text = empty_query.edit_message_text.await_args.args[0]
        self.assertIn("no active classes", empty_text)
        self.assertIn("Quick Create", empty_text)

    async def test_class_linked_screens_always_name_the_verified_class(self) -> None:
        open_callback = next(
            value
            for value in callbacks(class_list_keyboard([self.active], archived=False))
            if "|open|" in value
        )
        open_query, route_context = await self._class_route(open_callback)
        open_text = open_query.edit_message_text.await_args.args[0]
        open_markup = open_query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertIn("Active class: B1 Evening Group", open_text)
        self.assertEqual(
            route_context.user_data["active_class"]["display_name"],
            "B1 Evening Group",
        )

        analyze_callback = next(
            value for value in callbacks(open_markup) if "|analyze|" in value
        )
        analyze_query, analyze_context = await self._class_route(analyze_callback)
        analyze_text = analyze_query.edit_message_text.await_args.args[0]
        self.assertIn("Active class: B1 Evening Group", analyze_text)
        self.assertEqual(
            analyze_context.user_data["active_class"]["display_name"],
            "B1 Evening Group",
        )

        archived_callback = next(
            value
            for value in callbacks(class_list_keyboard([self.archived], archived=True))
            if "|open|" in value
        )
        archived_query, _ = await self._class_route(archived_callback)
        archived_text = archived_query.edit_message_text.await_args.args[0]
        archived_markup = archived_query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertIn("Archived class: Archived Saturday Group", archived_text)
        self.assertFalse(any("|analyze|" in value for value in callbacks(archived_markup)))

    async def test_stale_malformed_and_cross_owner_callbacks_share_safe_recovery(self) -> None:
        valid = next(
            value
            for value in callbacks(class_list_keyboard([self.active], archived=False))
            if "|open|" in value
        )
        parts = valid.split("|")
        parts[-1] = "zz"
        stale = "|".join(parts)

        stale_query, stale_context = await self._class_route(stale)
        stale_text = stale_query.edit_message_text.await_args.args[0]
        self.assertIn("changed, expired, or is no longer available", stale_text)
        self.assertNotIn("B1 Evening Group", stale_text)
        self.assertEqual(stale_context.user_data, {})

        malformed_query, _ = await self._class_route("v1|cl|open|not-valid")
        self.assertEqual(
            malformed_query.edit_message_text.await_args.args[0],
            stale_text,
        )

        cross_owner_query, _ = await self._class_route(valid, actor=self.other)
        self.assertEqual(
            cross_owner_query.edit_message_text.await_args.args[0],
            stale_text,
        )
        self.assertNotIn(
            "B1 Evening Group",
            cross_owner_query.edit_message_text.await_args.args[0],
        )

    def test_every_day6_callback_is_compact_contracted_and_has_an_escape(self) -> None:
        records = [self.active]
        markups = (
            quick_create_keyboard(),
            class_list_keyboard(records, archived=False),
            class_list_keyboard([self.archived], archived=True),
            class_intro_keyboard(),
            class_detail_keyboard(int(self.active["id"]), int(self.active["revision"])),
            analyze_picker_keyboard(records),
            class_linked_back_keyboard(int(self.active["id"]), int(self.active["revision"])),
            class_recovery_keyboard(),
        )
        for markup in markups:
            values = callbacks(markup)
            self.assertTrue(values)
            self.assertTrue(
                any(
                    value in {"v1|cl|home|0|0", "v1|rc|home|0|0"}
                    or "|list|" in value
                    or "|open|" in value
                    for value in values
                ),
                values,
            )
            for value in values:
                self.assertLessEqual(len(value.encode("utf-8")), 64, value)
                if value.startswith("v1|"):
                    self.assertIsNotNone(CALLBACK_CONTRACT.fullmatch(value), value)

    async def test_flag_off_restores_legacy_home_and_recovers_new_callbacks(self) -> None:
        with patch.dict(
            os.environ,
            {FEATURE_ENV_VARS["classes"]: "false"},
            clear=False,
        ):
            self.assertEqual(
                callbacks(start_menu_keyboard()),
                [
                    "lesson",
                    "activity_start",
                    "worksheet_start",
                    "quiz_start",
                    "search_start",
                    "account_home",
                ],
            )
            route_query, _ = await self._class_route("v1|cl|list|0|0")
            route_text = route_query.edit_message_text.await_args.args[0]
            route_markup = route_query.edit_message_text.await_args.kwargs["reply_markup"]
            self.assertIn("not enabled", route_text)
            self.assertEqual(callbacks(route_markup)[0], "lesson")


if __name__ == "__main__":
    unittest.main(verbosity=2)
