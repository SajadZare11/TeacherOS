from __future__ import annotations

import json
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
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day19-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day19-key")

import database
from class_service import create_class
from day19_migration import apply_schema_v19
from day25_migration import SCHEMA_VERSION
from differentiation_keyboards import (
    _ADAP_CODES,
    _base36,
    adaptation_view_keyboard,
    adaptations_menu_keyboard,
    differentiation_view_keyboard,
)
from differentiation_panel import (
    handle_adaptation_callback,
    handle_differentiation_callback,
)
from differentiation_service import (
    VALID_ADAPTATION_TYPES,
    generate_one_tap_adaptation,
    generate_tiered_differentiation,
    get_material_adaptation,
    get_tiered_differentiation,
    list_material_adaptations,
)
from feature_flags import FEATURE_ENV_VARS


class Day19DifferentiationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day19-test-")
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
            id=190_001,
            username="teacher_a_19",
            first_name="Alice",
            last_name="Teacher",
            language_code="en",
        )
        self.teacher_b = SimpleNamespace(
            id=190_002,
            username="teacher_b_19",
            first_name="Bob",
            last_name="Teacher",
            language_code="en",
        )

        with database.database_connection(self.db_path) as conn:
            conn.execute(
                "INSERT INTO users (telegram_user_id, username, first_name) VALUES (?, ?, ?)",
                (self.teacher_a.id, self.teacher_a.username, self.teacher_a.first_name),
            )
            conn.execute(
                "INSERT INTO users (telegram_user_id, username, first_name) VALUES (?, ?, ?)",
                (self.teacher_b.id, self.teacher_b.username, self.teacher_b.first_name),
            )

        self.class_a = create_class(
            telegram_user=self.teacher_a,
            display_name="B2 Upper-Intermediate",
            level="B2",
            age_group="adults",
            learner_count_band="13_20",
            goal="Discourse markers and debate synthesis",
            database_path=self.db_path,
        )

        # Create sample lesson material for Teacher A
        with database.database_connection(self.db_path) as conn:
            u_id = conn.execute("SELECT id FROM users WHERE telegram_user_id = ?", (self.teacher_a.id,)).fetchone()[0]
            cursor = conn.execute(
                """
                INSERT INTO materials (
                    user_id, class_id, material_type, subtype, title, topic,
                    level, content, metadata_json, created_at
                ) VALUES (?, ?, 'lesson', 'speaking', 'Debate Cohesion and Connectors', 'Discourse Connectors',
                          'B2', '# Lesson Plan\\nObjective: Express complex contrast using connectors.', '{}', '2026-08-31 12:00:00')
                """,
                (u_id, self.class_a["id"]),
            )
            self.mat_a_id = cursor.lastrowid

    def tearDown(self) -> None:
        database.DATABASE_PATH = self.orig_db_path
        self.flags_patcher.stop()
        self.temp_dir.cleanup()

    def test_schema_v19_is_idempotent_and_creates_tables(self) -> None:
        with database.database_connection(self.db_path) as conn:
            apply_schema_v19(conn)
            max_v = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
            self.assertEqual(max_v, SCHEMA_VERSION)

            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            self.assertIn("material_differentiations", tables)
            self.assertIn("material_adaptations", tables)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_generate_tiered_differentiation_creates_support_core_challenge(self) -> None:
        diff = generate_tiered_differentiation(
            telegram_user=self.teacher_a,
            source_material_id=self.mat_a_id,
            database_path=self.db_path,
        )
        self.assertIsNotNone(diff)
        self.assertEqual(diff["source_material_id"], self.mat_a_id)

        # 1. Shared Objective Invariant
        obj = diff["objective"]
        self.assertIn("Discourse Connectors", obj)

        # 2. Support route has scaffolding (model sentences, word bank, smaller steps)
        sup = diff["support_route_markdown"]
        self.assertIn("Support Route", sup)
        self.assertIn("Word Bank", sup)
        self.assertIn("Sentence Frame", sup)

        # 3. Core route has standard performance
        cor = diff["core_route_markdown"]
        self.assertIn("Core Route", cor)

        # 4. Challenge route has transfer & depth (NOT busywork)
        cha = diff["challenge_route_markdown"]
        self.assertIn("Challenge Route", cha)
        self.assertIn("Not Busywork", cha)
        self.assertIn("critique", cha)

        # 5. Classroom delivery guidance
        gui = diff["delivery_guidance_markdown"]
        self.assertIn("Discreet Distribution", gui)
        self.assertIn("Monitoring Protocol", gui)
        self.assertIn("Whole-Class Reconnection", gui)

    def test_all_nine_one_tap_adaptations_generate_correctly(self) -> None:
        for atype, label in VALID_ADAPTATION_TYPES.items():
            adap = generate_one_tap_adaptation(
                telegram_user=self.teacher_a,
                source_material_id=self.mat_a_id,
                adaptation_type=atype,
                database_path=self.db_path,
            )
            self.assertIsNotNone(adap)
            self.assertEqual(adap["adaptation_type"], atype)
            self.assertIn(label, adap["title"])
            self.assertTrue(len(adap["changes_summary"]) > 10)
            self.assertTrue(len(adap["adapted_content_markdown"]) > 20)

    def test_golden_cases_large_class_and_low_resource_are_runnable(self) -> None:
        # Large class golden case
        lar = generate_one_tap_adaptation(
            telegram_user=self.teacher_a,
            source_material_id=self.mat_a_id,
            adaptation_type="large_class",
            database_path=self.db_path,
        )
        self.assertIn("Large Class Management Protocol", lar["adapted_content_markdown"])
        self.assertIn("Pyramid Pairing", lar["adapted_content_markdown"])
        self.assertIn("Silent Signaling", lar["adapted_content_markdown"])

        # Zero tech / low resource golden case
        not_tech = generate_one_tap_adaptation(
            telegram_user=self.teacher_a,
            source_material_id=self.mat_a_id,
            adaptation_type="no_tech_low_resource",
            database_path=self.db_path,
        )
        self.assertIn("Zero-Tech / Low-Resource Version", not_tech["adapted_content_markdown"])
        self.assertIn("chalkboard", not_tech["adapted_content_markdown"])
        self.assertIn("paper", not_tech["adapted_content_markdown"])

    def test_multi_tenant_isolation_guards(self) -> None:
        # Teacher B cannot differentiate Teacher A's material
        with self.assertRaises(ValueError):
            generate_tiered_differentiation(
                telegram_user=self.teacher_b,
                source_material_id=self.mat_a_id,
                database_path=self.db_path,
            )

        # Teacher B cannot adapt Teacher A's material
        with self.assertRaises(ValueError):
            generate_one_tap_adaptation(
                telegram_user=self.teacher_b,
                source_material_id=self.mat_a_id,
                adaptation_type="shorter",
                database_path=self.db_path,
            )

        diff = generate_tiered_differentiation(
            telegram_user=self.teacher_a,
            source_material_id=self.mat_a_id,
            database_path=self.db_path,
        )
        adap = generate_one_tap_adaptation(
            telegram_user=self.teacher_a,
            source_material_id=self.mat_a_id,
            adaptation_type="shorter",
            database_path=self.db_path,
        )

        # Teacher B cannot read Teacher A's records
        self.assertIsNone(
            get_tiered_differentiation(
                telegram_user=self.teacher_b,
                differentiation_id=diff["id"],
                database_path=self.db_path,
            )
        )
        self.assertIsNone(
            get_material_adaptation(
                telegram_user=self.teacher_b,
                adaptation_id=adap["id"],
                database_path=self.db_path,
            )
        )

    def test_database_triggers_prevent_cross_user_insertion(self) -> None:
        with database.database_connection(self.db_path) as conn:
            u_b_id = conn.execute("SELECT id FROM users WHERE telegram_user_id = ?", (self.teacher_b.id,)).fetchone()[0]

            with self.assertRaises(Exception):
                conn.execute(
                    """
                    INSERT INTO material_differentiations (
                        diff_uuid, user_id, source_material_id, objective,
                        support_route_markdown, core_route_markdown,
                        challenge_route_markdown, delivery_guidance_markdown,
                        prompt_contract, prompt_version
                    ) VALUES ('diff-test-01', ?, ?, 'Obj', 'Sup', 'Cor', 'Cha', 'Gui', 'c', 'v')
                    """,
                    (u_b_id, self.mat_a_id),
                )

            with self.assertRaises(Exception):
                conn.execute(
                    """
                    INSERT INTO material_adaptations (
                        adaptation_uuid, user_id, source_material_id,
                        adaptation_type, title, changes_summary,
                        adapted_content_markdown, prompt_contract, prompt_version
                    ) VALUES ('adap-test-01', ?, ?, 'shorter', 'T', 'S', 'C', 'c', 'v')
                    """,
                    (u_b_id, self.mat_a_id),
                )

    def test_zero_raw_student_text_in_telemetry(self) -> None:
        diff = generate_tiered_differentiation(
            telegram_user=self.teacher_a,
            source_material_id=self.mat_a_id,
            database_path=self.db_path,
        )
        adap = generate_one_tap_adaptation(
            telegram_user=self.teacher_a,
            source_material_id=self.mat_a_id,
            adaptation_type="fast_finisher",
            database_path=self.db_path,
        )

        with database.database_connection(self.db_path) as conn:
            events = conn.execute("SELECT properties_json FROM product_events").fetchall()
            for ev in events:
                props = json.loads(ev["properties_json"])
                self.assertNotIn("Lesson Plan", str(props))
                self.assertNotIn("Discourse Connectors", str(props))

    def test_keyboards_are_compact_and_within_64_bytes(self) -> None:
        kbs = [
            differentiation_view_keyboard(1, self.mat_a_id, "sup"),
            differentiation_view_keyboard(1, self.mat_a_id, "cor"),
            differentiation_view_keyboard(1, self.mat_a_id, "cha"),
            differentiation_view_keyboard(1, self.mat_a_id, "gui"),
            adaptations_menu_keyboard(self.mat_a_id),
            adaptation_view_keyboard(1, self.mat_a_id),
        ]
        for kb in kbs:
            for row in kb.inline_keyboard:
                for btn in row:
                    payload_len = len(btn.callback_data.encode("utf-8"))
                    self.assertLessEqual(
                        payload_len,
                        64,
                        f"Callback payload '{btn.callback_data}' exceeds 64 bytes ({payload_len} bytes)",
                    )

    def test_list_material_adaptations_returns_all_for_source(self) -> None:
        generate_one_tap_adaptation(
            telegram_user=self.teacher_a,
            source_material_id=self.mat_a_id,
            adaptation_type="shorter",
            database_path=self.db_path,
        )
        generate_one_tap_adaptation(
            telegram_user=self.teacher_a,
            source_material_id=self.mat_a_id,
            adaptation_type="longer_plus15",
            database_path=self.db_path,
        )
        adaps = list_material_adaptations(
            telegram_user=self.teacher_a,
            source_material_id=self.mat_a_id,
            database_path=self.db_path,
        )
        self.assertEqual(len(adaps), 2)
        self.assertEqual(adaps[0]["source_material_id"], self.mat_a_id)

    async def test_ui_differentiation_panel_renders_all_tabs(self) -> None:
        diff = generate_tiered_differentiation(
            telegram_user=self.teacher_a,
            source_material_id=self.mat_a_id,
            database_path=self.db_path,
        )
        # Test tab switching
        for tab in ("sup", "cor", "cha", "gui"):
            query = MagicMock()
            query.data = f"v1|df|tab|{_base36(diff['id'])}|{tab}"
            query.answer = AsyncMock()
            query.edit_message_text = AsyncMock()
            update = MagicMock()
            update.callback_query = query
            update.effective_user = self.teacher_a
            context = MagicMock()

            await handle_differentiation_callback(update, context)
            query.edit_message_text.assert_called_once()
            args, kwargs = query.edit_message_text.call_args
            text = args[0]
            self.assertIn("3-Tier Differentiation", text)

    async def test_ui_adaptation_panel_renders_menu_and_generation(self) -> None:
        # Test adaptation menu
        query = MagicMock()
        query.data = f"v1|ad|menu|{_base36(self.mat_a_id)}"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update = MagicMock()
        update.callback_query = query
        update.effective_user = self.teacher_a
        context = MagicMock()

        await handle_adaptation_callback(update, context)
        query.edit_message_text.assert_called_once()
        args, kwargs = query.edit_message_text.call_args
        self.assertIn("One-Tap Classroom Adaptations", args[0])

        # Test adaptation generation
        query_gen = MagicMock()
        query_gen.data = f"v1|ad|gen|{_base36(self.mat_a_id)}|sho"
        query_gen.answer = AsyncMock()
        query_gen.edit_message_text = AsyncMock()
        update_gen = MagicMock()
        update_gen.callback_query = query_gen
        update_gen.effective_user = self.teacher_a

        await handle_adaptation_callback(update_gen, context)
        query_gen.edit_message_text.assert_called_once()
        args_g, kwargs_g = query_gen.edit_message_text.call_args
        self.assertIn("Shorter Version", args_g[0])

    def test_invalid_adaptation_type_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            generate_one_tap_adaptation(
                telegram_user=self.teacher_a,
                source_material_id=self.mat_a_id,
                adaptation_type="invalid_type",
                database_path=self.db_path,
            )

    def test_unregistered_user_cannot_differentiate_or_adapt(self) -> None:
        ghost = SimpleNamespace(id=999_999, username="ghost")
        with self.assertRaises(ValueError):
            generate_tiered_differentiation(
                telegram_user=ghost,
                source_material_id=self.mat_a_id,
                database_path=self.db_path,
            )
        with self.assertRaises(ValueError):
            generate_one_tap_adaptation(
                telegram_user=ghost,
                source_material_id=self.mat_a_id,
                adaptation_type="shorter",
                database_path=self.db_path,
            )

    def test_material_cascade_deletion_cleans_differentiations_and_adaptations(self) -> None:
        diff = generate_tiered_differentiation(
            telegram_user=self.teacher_a,
            source_material_id=self.mat_a_id,
            database_path=self.db_path,
        )
        adap = generate_one_tap_adaptation(
            telegram_user=self.teacher_a,
            source_material_id=self.mat_a_id,
            adaptation_type="shorter",
            database_path=self.db_path,
        )

        with database.database_connection(self.db_path) as conn:
            conn.execute("DELETE FROM materials WHERE id = ?", (self.mat_a_id,))

        self.assertIsNone(
            get_tiered_differentiation(
                telegram_user=self.teacher_a,
                differentiation_id=diff["id"],
                database_path=self.db_path,
            )
        )
        self.assertIsNone(
            get_material_adaptation(
                telegram_user=self.teacher_a,
                adaptation_id=adap["id"],
                database_path=self.db_path,
            )
        )


if __name__ == "__main__":
    unittest.main()
