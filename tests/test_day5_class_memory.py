from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day5-token-not-used")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day5-key-not-used")

import class_service  # noqa: E402
import database  # noqa: E402
from day26_migration import SCHEMA_VERSION  # noqa: E402
from day5_migration_check import run_checks  # noqa: E402
from feature_flags import (  # noqa: E402
    FEATURE_ENV_VARS,
    feature_enabled,
    feature_flag_snapshot,
    quick_create_is_default,
)
from keyboards import start_menu_keyboard  # noqa: E402


def user(user_id: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        username=f"day5_teacher_{user_id}",
        first_name=name,
        last_name="Teacher",
        language_code="en",
    )


def disabled_flags() -> dict[str, str]:
    return {env_name: "false" for env_name in FEATURE_ENV_VARS.values()}


class Day5MigrationAndFlagTests(unittest.TestCase):
    def test_empty_legacy_and_populated_migrations_are_idempotent(self) -> None:
        report = run_checks()
        self.assertTrue(report["passed"])
        self.assertEqual(report["scenario_count"], 3)
        self.assertEqual(
            [scenario["label"] for scenario in report["scenarios"]],
            ["empty", "legacy-v5", "populated-v5"],
        )
        for scenario in report["scenarios"]:
            self.assertEqual(scenario["schema_version"], SCHEMA_VERSION)
            self.assertTrue(scenario["legacy_data_preserved"])
            self.assertEqual(scenario["foreign_key_error_count"], 0)
            self.assertFalse(any(scenario["duplicate_columns"].values()))
            self.assertFalse(any(scenario["missing_legacy_columns"].values()))

    def test_flags_fail_closed_and_quick_create_stays_default(self) -> None:
        with patch.dict(os.environ, disabled_flags(), clear=False):
            snapshot = feature_flag_snapshot()
            self.assertTrue(all(not value["effective"] for value in snapshot.values()))
            self.assertTrue(quick_create_is_default())
            keyboard = start_menu_keyboard()
            callbacks = {
                button.callback_data
                for row in keyboard.inline_keyboard
                for button in row
            }
            self.assertEqual(
                callbacks,
                {
                    "lesson",
                    "activity_start",
                    "worksheet_start",
                    "quiz_start",
                    "search_start",
                    "account_home",
                },
            )
            with self.assertRaises(class_service.ClassFeatureDisabledError):
                class_service.list_classes(telegram_user_id=1)

    def test_each_flag_can_be_disabled_independently_and_dependencies_fail_closed(self) -> None:
        all_enabled = {env_name: "true" for env_name in FEATURE_ENV_VARS.values()}
        with patch.dict(os.environ, all_enabled, clear=False):
            self.assertTrue(all(feature_enabled(name) for name in FEATURE_ENV_VARS))
            for name, env_name in FEATURE_ENV_VARS.items():
                with self.subTest(feature=name), patch.dict(
                    os.environ, {env_name: "false"}, clear=False
                ):
                    self.assertFalse(feature_enabled(name))
            with patch.dict(
                os.environ,
                {FEATURE_ENV_VARS["classes"]: "false"},
                clear=False,
            ):
                self.assertFalse(feature_enabled("continuity"))
                self.assertFalse(feature_enabled("evidence"))
                self.assertFalse(feature_enabled("differentiation"))
                self.assertFalse(feature_enabled("reports"))
                self.assertTrue(feature_enabled("entitlements"))
        with self.assertRaises(ValueError):
            feature_enabled("typo")


class Day5OwnershipServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day5-service-")
        self.database_path = Path(self.temp_dir.name) / "service.db"
        self.owner = user(52001, "Owner")
        self.other = user(52002, "Other")
        self.flags = patch.dict(
            os.environ,
            {**disabled_flags(), FEATURE_ENV_VARS["classes"]: "true"},
            clear=False,
        )
        self.flags.start()

    def tearDown(self) -> None:
        self.flags.stop()
        self.temp_dir.cleanup()

    def _material(self, telegram_user: SimpleNamespace, title: str) -> int:
        with database.database_connection(self.database_path) as connection:
            user_id = database.ensure_database_user(connection, telegram_user)
            cursor = connection.execute(
                """
                INSERT INTO materials (
                    user_id, material_type, title, content, metadata_json
                ) VALUES (?, 'lesson', ?, 'Class-safe content', '{}')
                """,
                (user_id, title),
            )
            return int(cursor.lastrowid)

    def test_schema_contract_has_utc_status_constraints_and_owner_indexes(self) -> None:
        database.initialize_database(self.database_path)
        database.initialize_database(self.database_path)
        with database.database_connection(self.database_path) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertTrue(
                {
                    "classes",
                    "class_objectives",
                    "class_lessons",
                    "lesson_outcomes",
                    "product_events",
                }.issubset(tables)
            )
            material_columns = [
                row[1] for row in connection.execute("PRAGMA table_info(materials)")
            ]
            self.assertEqual(material_columns.count("class_id"), 1)
            indexes = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                )
            }
            self.assertIn("idx_classes_user_status_updated", indexes)
            self.assertIn("idx_materials_user_class_created", indexes)
            self.assertEqual(
                connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0],
                SCHEMA_VERSION,
            )
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

        created = class_service.create_class(
            telegram_user=self.owner,
            display_name="B1 Evening",
            level="B1",
            age_group="adults",
            learner_count_band="6_12",
            cadence="twice_weekly",
            database_path=self.database_path,
        )
        self.assertTrue(created["created_at"].endswith("Z"))
        self.assertEqual(created["status"], "active")
        with database.database_connection(self.database_path) as connection:
            owner_id = database.ensure_database_user(connection, self.owner)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO classes (user_id, display_name, status) VALUES (?, 'Bad', 'deleted')",
                    (owner_id,),
                )

    def test_cross_user_read_modify_archive_link_and_inference_are_blocked(self) -> None:
        owner_class = class_service.create_class(
            telegram_user=self.owner,
            display_name="Owner class",
            database_path=self.database_path,
        )
        other_class = class_service.create_class(
            telegram_user=self.other,
            display_name="Other class",
            database_path=self.database_path,
        )
        owner_material = self._material(self.owner, "Owner material")
        other_material = self._material(self.other, "Other material")

        self.assertIsNone(
            class_service.get_class(
                telegram_user_id=self.other.id,
                class_id=owner_class["id"],
                database_path=self.database_path,
            )
        )
        self.assertIsNone(
            class_service.update_class(
                telegram_user_id=self.other.id,
                class_id=owner_class["id"],
                changes={"display_name": "Stolen"},
                database_path=self.database_path,
            )
        )
        self.assertFalse(
            class_service.archive_class(
                telegram_user_id=self.other.id,
                class_id=owner_class["id"],
                database_path=self.database_path,
            )
        )
        self.assertFalse(
            class_service.link_material_to_class(
                telegram_user_id=self.other.id,
                material_id=other_material,
                class_id=owner_class["id"],
                database_path=self.database_path,
            )
        )
        self.assertFalse(
            class_service.link_material_to_class(
                telegram_user_id=self.other.id,
                material_id=owner_material,
                class_id=other_class["id"],
                database_path=self.database_path,
            )
        )
        self.assertEqual(
            class_service.list_classes(
                telegram_user_id=self.other.id,
                include_archived=True,
                database_path=self.database_path,
            ),
            [other_class],
        )
        missing_id = int(owner_class["id"]) + 1_000_000
        unauthorized = class_service.get_class(
            telegram_user_id=self.other.id,
            class_id=owner_class["id"],
            database_path=self.database_path,
        )
        missing = class_service.get_class(
            telegram_user_id=self.other.id,
            class_id=missing_id,
            database_path=self.database_path,
        )
        self.assertEqual(unauthorized, missing)

        self.assertTrue(
            class_service.link_material_to_class(
                telegram_user_id=self.owner.id,
                material_id=owner_material,
                class_id=owner_class["id"],
                database_path=self.database_path,
            )
        )
        with database.database_connection(self.database_path) as connection:
            other_user_id = connection.execute(
                "SELECT id FROM users WHERE telegram_user_id = ?", (self.other.id,)
            ).fetchone()[0]
            with self.assertRaisesRegex(sqlite3.IntegrityError, "ownership mismatch"):
                connection.execute(
                    "UPDATE materials SET user_id = ? WHERE id = ?",
                    (other_user_id, owner_material),
                )

    def test_all_new_records_work_through_owner_scoped_service(self) -> None:
        class_record = class_service.create_class(
            telegram_user=self.owner,
            display_name="Continuity class",
            level="A2",
            goal="Build speaking confidence",
            database_path=self.database_path,
        )
        material_id = self._material(self.owner, "Speaking lesson")
        self.assertTrue(
            class_service.link_material_to_class(
                telegram_user_id=self.owner.id,
                material_id=material_id,
                class_id=class_record["id"],
                database_path=self.database_path,
            )
        )
        objective = class_service.add_class_objective(
            telegram_user_id=self.owner.id,
            class_id=class_record["id"],
            objective="Use past tense in a short story",
            priority=80,
            database_path=self.database_path,
        )
        self.assertIsNotNone(objective)
        lesson = class_service.create_class_lesson(
            telegram_user_id=self.owner.id,
            class_id=class_record["id"],
            material_id=material_id,
            title="Storytelling practice",
            status="taught",
            scheduled_for="2026-08-28T15:00:00Z",
            database_path=self.database_path,
        )
        self.assertIsNotNone(lesson)
        outcome = class_service.record_lesson_outcome(
            telegram_user_id=self.owner.id,
            class_id=class_record["id"],
            class_lesson_id=lesson["id"],
            result="partly_met",
            confidence="medium",
            support_needed="some",
            notes="Revisit irregular verbs.",
            database_path=self.database_path,
        )
        self.assertIsNotNone(outcome)
        event_key = "day5-event-owner-0001"
        event_id = class_service.record_product_event(
            telegram_user=self.owner,
            event_uuid=event_key,
            event_name="class_lesson_outcome_saved",
            class_id=class_record["id"],
            class_lesson_id=lesson["id"],
            material_id=material_id,
            properties={"result": "partly_met"},
            database_path=self.database_path,
        )
        duplicate_event_id = class_service.record_product_event(
            telegram_user=self.owner,
            event_uuid=event_key,
            event_name="class_lesson_outcome_saved",
            class_id=class_record["id"],
            database_path=self.database_path,
        )
        self.assertEqual(event_id, duplicate_event_id)

        updated = class_service.update_class(
            telegram_user_id=self.owner.id,
            class_id=class_record["id"],
            changes={"goal": "Use the past tense independently"},
            expected_revision=1,
            database_path=self.database_path,
        )
        self.assertEqual(updated["revision"], 2)
        self.assertIsNone(
            class_service.update_class(
                telegram_user_id=self.owner.id,
                class_id=class_record["id"],
                changes={"goal": "Stale update"},
                expected_revision=1,
                database_path=self.database_path,
            )
        )
        with database.database_connection(self.database_path) as connection:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "classes",
                    "class_objectives",
                    "class_lessons",
                    "lesson_outcomes",
                    "product_events",
                )
            }
            self.assertEqual(counts, {table: 1 for table in counts})
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
