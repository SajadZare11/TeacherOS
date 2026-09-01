"""Tests for TeacherOS Day 24 Telegram Speed, Clarity, Accessibility, and Localization."""
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
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day24-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day24-key")

import database
from class_service import create_class
from day26_migration import SCHEMA_VERSION
from feature_flags import FEATURE_ENV_VARS
from string_catalog import STRINGS_EN, STRINGS_FA, tr
from ui_keyboards import (
    language_switcher_keyboard,
    material_pin_toggle_keyboard,
    onboarding_walkthrough_keyboard,
    pinned_materials_keyboard,
)
from ui_panel import handle_ui_callback
from ui_service import (
    complete_onboarding,
    get_or_create_ui_preferences,
    get_recent_class_materials,
    is_material_pinned,
    list_pinned_materials,
    pin_material_to_class,
    search_class_materials,
    set_user_language,
    unpin_material_from_class,
)


class Day24TelegramPolishTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day24-test-")
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
            id=240_101,
            username="teacher_a",
            first_name="Alice",
            last_name="Teacher",
            language_code="en",
        )
        self.teacher_b = SimpleNamespace(
            id=240_102,
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
            display_name="B2 Professional Business English",
            level="B2",
            age_group="adults",
            learner_count_band="6_12",
            goal="Negotiations and presentations",
            database_path=self.db_path,
        )
        self.class_a_id = int(self.class_a["id"])

    def tearDown(self) -> None:
        database.DATABASE_PATH = self.orig_db_path
        self.flags_patcher.stop()
        self.temp_dir.cleanup()

    def test_schema_v24_initialized(self) -> None:
        """Verify schema version 24 and table creation."""
        with database.database_connection(self.db_path) as conn:
            ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
            self.assertGreaterEqual(ver, 24)
            t1 = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='user_ui_preferences'"
            ).fetchone()
            t2 = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='user_pinned_materials'"
            ).fetchone()
            self.assertIsNotNone(t1)
            self.assertIsNotNone(t2)

    def test_string_catalog_and_localization(self) -> None:
        """Verify string catalog retrieval, template formatting, and fallback."""
        self.assertEqual(tr("nav_save", "en"), "💾 Save")
        self.assertEqual(tr("nav_save", "fa"), "💾 ذخیره")
        # Template formatting
        hdr = tr("header_active_class", "en", class_name="IELTS Prep", level="B2")
        self.assertIn("IELTS Prep", hdr)
        self.assertIn("B2", hdr)
        # Safe fallback
        self.assertIn("[non_existent_key]", tr("non_existent_key", "fa"))

    def test_language_preference_persisted(self) -> None:
        """Verify UI preferences creation and language switching."""
        prefs = get_or_create_ui_preferences(self.user_a_id, database_path=self.db_path)
        self.assertEqual(prefs["language_code"], "en")

        updated = set_user_language(self.user_a_id, "fa", database_path=self.db_path)
        self.assertEqual(updated["language_code"], "fa")

        reloaded = get_or_create_ui_preferences(self.user_a_id, database_path=self.db_path)
        self.assertEqual(reloaded["language_code"], "fa")

    def test_onboarding_walkthrough_and_completion(self) -> None:
        """Verify first-run walkthrough state tracking."""
        prefs_before = get_or_create_ui_preferences(self.user_a_id, database_path=self.db_path)
        self.assertEqual(prefs_before["onboarding_completed"], 0)

        complete_onboarding(self.user_a_id, database_path=self.db_path)
        prefs_after = get_or_create_ui_preferences(self.user_a_id, database_path=self.db_path)
        self.assertEqual(prefs_after["onboarding_completed"], 1)

    def test_pin_and_unpin_materials(self) -> None:
        """Verify pinning materials to class favorites and unpinning."""
        with database.database_connection(self.db_path) as conn:
            mat_cur = conn.execute(
                """
                INSERT INTO materials (user_id, material_type, title, level, content, class_id)
                VALUES (?, 'lesson', 'Business Email Etiquette', 'B2', 'Email content...', ?)
                """,
                (self.user_a_id, self.class_a_id),
            )
            mat_id = mat_cur.lastrowid

        self.assertFalse(is_material_pinned(user_id=self.user_a_id, class_id=self.class_a_id, material_id=mat_id, database_path=self.db_path))

        pinned = pin_material_to_class(user_id=self.user_a_id, class_id=self.class_a_id, material_id=mat_id, database_path=self.db_path)
        self.assertTrue(pinned)
        self.assertTrue(is_material_pinned(user_id=self.user_a_id, class_id=self.class_a_id, material_id=mat_id, database_path=self.db_path))

        favorites = list_pinned_materials(user_id=self.user_a_id, class_id=self.class_a_id, database_path=self.db_path)
        self.assertEqual(len(favorites), 1)
        self.assertEqual(favorites[0]["title"], "Business Email Etiquette")

        unpinned = unpin_material_from_class(user_id=self.user_a_id, class_id=self.class_a_id, material_id=mat_id, database_path=self.db_path)
        self.assertTrue(unpinned)
        self.assertFalse(is_material_pinned(user_id=self.user_a_id, class_id=self.class_a_id, material_id=mat_id, database_path=self.db_path))

    def test_class_aware_search_and_recent(self) -> None:
        """Verify class-scoped material search and recent list."""
        with database.database_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO materials (user_id, material_type, title, level, content, class_id)
                VALUES (?, 'lesson', 'Job Interview Practice', 'B2', 'Common interview questions...', ?)
                """,
                (self.user_a_id, self.class_a_id),
            )

        results = search_class_materials(user_id=self.user_a_id, class_id=self.class_a_id, query_text="interview", database_path=self.db_path)
        self.assertEqual(len(results), 1)
        self.assertIn("Interview", results[0]["title"])

        recent = get_recent_class_materials(user_id=self.user_a_id, class_id=self.class_a_id, database_path=self.db_path)
        self.assertGreaterEqual(len(recent), 1)

    def test_accessibility_screen_reader_labels(self) -> None:
        """Verify screen-reader friendly status badges without relying solely on emoji."""
        self.assertEqual(tr("badge_approved", "en"), "[Status: Approved]")
        self.assertEqual(tr("badge_draft", "en"), "[Status: Draft]")
        self.assertEqual(tr("badge_needs_review", "en"), "[Status: Needs Review]")

    def test_multi_tenant_isolation(self) -> None:
        """Verify Teacher B cannot access or modify Teacher A's pinned materials or class search."""
        with database.database_connection(self.db_path) as conn:
            mat_cur = conn.execute(
                """
                INSERT INTO materials (user_id, material_type, title, level, content, class_id)
                VALUES (?, 'lesson', 'Private Material', 'B2', 'Secret content', ?)
                """,
                (self.user_a_id, self.class_a_id),
            )
            mat_id = mat_cur.lastrowid

        cross_pin = pin_material_to_class(
            user_id=self.user_b_id,
            class_id=self.class_a_id,
            material_id=mat_id,
            database_path=self.db_path,
        )
        self.assertFalse(cross_pin)

        cross_search = search_class_materials(
            user_id=self.user_b_id,
            class_id=self.class_a_id,
            query_text="Private",
            database_path=self.db_path,
        )
        self.assertEqual(len(cross_search), 0)

    def test_telegram_keyboards_bounded_64_bytes(self) -> None:
        """Verify all inline keyboards in ui_keyboards respect 64-byte payload limits."""
        keyboards = [
            language_switcher_keyboard(1, "en"),
            language_switcher_keyboard(1, "fa"),
            onboarding_walkthrough_keyboard(1, 1, "en"),
            onboarding_walkthrough_keyboard(2, 1, "en"),
            onboarding_walkthrough_keyboard(3, 1, "en"),
            pinned_materials_keyboard(self.class_a_id, 1, [], "en"),
            material_pin_toggle_keyboard(self.class_a_id, 10, 1, is_pinned=True, lang="en"),
            material_pin_toggle_keyboard(self.class_a_id, 10, 1, is_pinned=False, lang="en"),
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

    async def test_ui_panel_callbacks(self) -> None:
        """Verify Telegram panel callbacks for language switching and walkthrough."""
        update = MagicMock()
        update.effective_user = self.teacher_a
        update.callback_query = MagicMock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        # 1. Open Language Switcher
        update.callback_query.data = "v1|ui|lang|0|1"
        await handle_ui_callback(update, context)
        update.callback_query.edit_message_text.assert_awaited()

        # 2. Switch language to FA
        update.callback_query.data = "v1|ui|slfa|0|1"
        await handle_ui_callback(update, context)
        prefs = get_or_create_ui_preferences(self.user_a_id, database_path=self.db_path)
        self.assertEqual(prefs["language_code"], "fa")

        # 3. Walkthrough Step 1 to Step 2
        update.callback_query.data = "v1|ui|onb2|0|1"
        await handle_ui_callback(update, context)
        update.callback_query.edit_message_text.assert_awaited()

        # 4. Finish Walkthrough
        update.callback_query.data = "v1|ui|onbdon|0|1"
        await handle_ui_callback(update, context)
        prefs_done = get_or_create_ui_preferences(self.user_a_id, database_path=self.db_path)
        self.assertEqual(prefs_done["onboarding_completed"], 1)


if __name__ == "__main__":
    unittest.main()
