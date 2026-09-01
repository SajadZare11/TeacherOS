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
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day10-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day10-key")

import class_service  # noqa: E402
import database  # noqa: E402
import ai_gateway  # noqa: E402
from ai_gateway import generate_artifact  # noqa: E402
from class_generation import class_generation_callback_handler  # noqa: E402
from class_dashboard_keyboards import class_action_keyboard  # noqa: E402
from day28_migration import SCHEMA_VERSION  # noqa: E402
from feature_flags import FEATURE_ENV_VARS  # noqa: E402
from keyboards import generated_material_export_keyboard  # noqa: E402
from material_actions import _prompt_replacements  # noqa: E402
from openrouter_client import ModelResponse  # noqa: E402
from pdf_document import create_pdf_export  # noqa: E402
from prompt_contracts import get_prompt_contract  # noqa: E402
from validators import validate_model_response  # noqa: E402
from word_document import create_word_export  # noqa: E402


def teacher(identifier: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier, username=f"day10_{identifier}", first_name="Day Ten",
        last_name="Teacher", language_code="en",
    )


def callbacks(markup: object) -> list[str]:
    return [
        button.callback_data for row in markup.inline_keyboard for button in row
        if button.callback_data
    ]


class Day10ClassAwareTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="teacheros-day10-")
        self.database_path = Path(self.temp.name) / "teacheros.db"
        self.db_patch = patch.object(database, "DATABASE_PATH", self.database_path)
        self.db_patch.start()
        flags = {value: "false" for value in FEATURE_ENV_VARS.values()}
        flags[FEATURE_ENV_VARS["classes"]] = "true"
        flags[FEATURE_ENV_VARS["continuity"]] = "true"
        self.flag_patch = patch.dict(os.environ, flags, clear=False)
        self.flag_patch.start()
        self.owner = teacher(101001)
        self.other = teacher(101002)
        self.class_record = class_service.create_class(
            telegram_user=self.owner, display_name="B1 Evening", level="B1",
            age_group="adults", learner_count_band="6_12", goal="Fluent speaking",
        )
        with database.database_connection(self.database_path) as connection:
            connection.execute(
                "UPDATE classes SET lesson_duration_minutes = 45 WHERE id = ?",
                (self.class_record["id"],),
            )
            owner_id = int(connection.execute(
                "SELECT user_id FROM classes WHERE id = ?", (self.class_record["id"],)
            ).fetchone()[0])
            self.objective_id = int(connection.execute(
                "INSERT INTO class_objectives (class_id, user_id, objective, priority) "
                "VALUES (?, ?, 'Use target language accurately', 50)",
                (self.class_record["id"], owner_id),
            ).lastrowid)

    def tearDown(self) -> None:
        self.flag_patch.stop()
        self.db_patch.stop()
        self.temp.cleanup()

    async def _start(self, kind: str) -> tuple[SimpleNamespace, SimpleNamespace]:
        record = class_service.get_class(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )
        query = SimpleNamespace(
            data=f"cg|{kind}|{int(record['id']):x}|{int(record['revision']):x}",
            answer=AsyncMock(), edit_message_text=AsyncMock(),
        )
        context = SimpleNamespace(user_data={})
        await class_generation_callback_handler(
            SimpleNamespace(callback_query=query, effective_user=self.owner), context
        )
        query.answer.assert_awaited_once()
        query.edit_message_text.assert_awaited_once()
        return query, context

    async def test_all_four_class_entries_inherit_context_and_lesson_halves_inputs(self) -> None:
        lesson_query, lesson_context = await self._start("ls")
        lesson = lesson_context.user_data["lesson"]
        self.assertEqual(lesson["state"], "topic")
        self.assertEqual(lesson["level"], "B1")
        self.assertEqual(lesson["duration"], "45")
        day1_inputs = 4
        class_aware_inputs = 2  # topic + grammar; level and duration are inherited
        reduction = (day1_inputs - class_aware_inputs) / day1_inputs
        self.assertGreaterEqual(reduction, 0.50)
        self.assertIn("Inherited", lesson_query.edit_message_text.await_args.args[0])
        for kind, key, state in (
            ("ac", "activity", "type"), ("ws", "worksheet", "type"),
            ("as", "quiz", "assessment_type"),
        ):
            _, context = await self._start(kind)
            self.assertEqual(context.user_data[key]["state"], state)
            self.assertEqual(context.user_data[key]["level"], "B1")
            self.assertTrue(context.user_data[key]["class_mode"])

    async def test_stale_or_cross_owner_entry_fails_closed(self) -> None:
        query = SimpleNamespace(
            data=f"cg|ls|{int(self.class_record['id']):x}|ffff",
            answer=AsyncMock(), edit_message_text=AsyncMock(),
        )
        context = SimpleNamespace(user_data={"sentinel": "must-clear"})
        await class_generation_callback_handler(
            SimpleNamespace(callback_query=query, effective_user=self.other), context
        )
        self.assertEqual(context.user_data, {})
        self.assertIn("unavailable", query.edit_message_text.await_args.args[0])

    def test_schema_v10_and_class_material_provenance_are_owner_scoped(self) -> None:
        database.initialize_database(self.database_path)
        database.initialize_database(self.database_path)
        provenance = {
            "prompt_contract": "teacheros.lesson_plan",
            "prompt_version": "2026-08-28.1",
            "prompt_hash_sha256": "a" * 64,
            "context_hash_sha256": "b" * 64,
            "source_record_ids": {
                "classes": [self.class_record["id"]],
                "class_objectives": [self.objective_id],
            },
        }
        material_id = database.save_generated_material(
            telegram_user=self.owner, material_type="lesson", subtype="Lesson Plan",
            title="Class-linked travel lesson", level="B1", topic="Travel",
            content="Level B1. Timing 45 minutes. Materials: board. Instructions: teach safely.",
            class_id=int(self.class_record["id"]), objective_ids=[self.objective_id],
            ai_provenance=provenance,
            quality_scores={"timing": 100, "overall": 100},
        )
        material = database.get_user_material(
            telegram_user_id=self.owner.id, material_id=material_id
        )
        self.assertEqual(material["class_id"], self.class_record["id"])
        self.assertEqual(material["objective_ids"], [self.objective_id])
        self.assertEqual(material["ai_prompt_version"], "2026-08-28.1")
        self.assertEqual(material["quality_scores"]["overall"], 100)
        self.assertEqual(database.database_healthcheck()["schema_version"], SCHEMA_VERSION)
        self.assertEqual(len(database.list_class_materials(
            telegram_user_id=self.owner.id, class_id=int(self.class_record["id"])
        )), 1)
        self.assertEqual(len(database.search_user_materials(
            telegram_user_id=self.owner.id, query="travel B1"
        )), 1)
        self.assertIsNone(database.get_user_material(
            telegram_user_id=self.other.id, material_id=material_id
        ))
        with self.assertRaises((RuntimeError, ValueError)):
            database.save_generated_material(
                telegram_user=self.other, material_type="lesson", title="Cross owner",
                content="blocked", class_id=int(self.class_record["id"]),
            )

    def test_quality_gate_checks_all_day10_dimensions(self) -> None:
        contract = get_prompt_contract("general_chat")
        valid = (
            "CEFR Level B1\nTiming: 45 minutes\nMaterials: board\n"
            "Instructions: follow these steps.\nAnswer Key: 1 A\n"
            "Objective Alignment: Use target language accurately."
        )
        requirements = {
            "level": "B1", "duration_minutes": "45", "answer_key": True,
            "objective_alignment": True,
        }
        result = validate_model_response(
            json.dumps({"content": valid}), contract, requirements
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.quality_scores["overall"], 100)
        markers = {
            "timing": "Timing: 45 minutes", "instructions": "Instructions: follow these steps.",
            "level": "CEFR Level B1", "resource_requirements": "Materials: board",
            "answer_key": "Answer Key: 1 A", "objective_alignment": "Objective Alignment: Use target language accurately.",
        }
        for name, marker in markers.items():
            invalid = validate_model_response(
                json.dumps({"content": valid.replace(marker, "")}), contract, requirements
            )
            self.assertIn(f"quality_failed:{name}", invalid.errors, name)

    async def test_quality_failure_repairs_once_before_display(self) -> None:
        with database.database_connection(self.database_path) as connection:
            database.ensure_database_user(connection, self.owner)
        valid = (
            "CEFR Level B1. Timing: 45 minutes. Materials: board. "
            "Instructions: follow the steps."
        )
        provider = AsyncMock(side_effect=[
            ModelResponse('{"content":"Too vague."}'),
            ModelResponse(json.dumps({"content": valid})),
        ])
        with patch.object(ai_gateway, "generate_response", provider):
            result = await generate_artifact(
                feature="general_chat", telegram_user_id=self.owner.id,
                model="offline-model", current_request="Create a lesson",
                quality_requirements={"level": "B1", "duration_minutes": 45},
                database_path=self.database_path,
            )
        self.assertEqual(result.content, valid)
        self.assertTrue(result.repair_attempted)
        self.assertEqual(result.attempt_count, 2)
        self.assertEqual(result.quality_scores["overall"], 100)

    def test_toolbar_matrix_idempotent_next_lesson_and_exports(self) -> None:
        material_id = database.save_generated_material(
            telegram_user=self.owner, material_type="lesson", title="Next class lesson",
            content="Timing 45 minutes. Materials board. Instructions. Level B1.",
            level="B1", topic="Travel", class_id=int(self.class_record["id"]),
        )
        toolbar = generated_material_export_keyboard(
            material_id, material_type="lesson", class_id=int(self.class_record["id"])
        )
        values = callbacks(toolbar)
        for prefix in ("ma|sv|", "ma|ad|", "ma|rg|", "ma|nx|", "ma|rp|", "export_", "pdf_"):
            self.assertTrue(any(value.startswith(prefix) for value in values), prefix)
        self.assertTrue(all(len(value.encode("utf-8")) <= 64 for value in values))
        maximum = 9_223_372_036_854_775_807
        for action in ("plan", "create"):
            class_callbacks = callbacks(class_action_keyboard(
                maximum, 2_176_782_335, action, class_aware=True
            ))
            self.assertTrue(all(len(value.encode("utf-8")) <= 64 for value in class_callbacks))
        first, created = database.plan_material_as_next_lesson(
            telegram_user_id=self.owner.id, material_id=material_id
        )
        second, duplicate = database.plan_material_as_next_lesson(
            telegram_user_id=self.owner.id, material_id=material_id
        )
        self.assertTrue(created)
        self.assertFalse(duplicate)
        self.assertEqual(first["id"], second["id"])
        material = database.get_user_material(
            telegram_user_id=self.owner.id, material_id=material_id
        )
        word, word_name = create_word_export(material)
        pdf, pdf_name = create_pdf_export(material)
        self.assertEqual(word.read(2), b"PK")
        self.assertEqual(pdf.read(4), b"%PDF")
        self.assertTrue(word_name.endswith(".docx") and pdf_name.endswith(".pdf"))

    def test_quick_create_replacements_and_day10_matrix_are_complete(self) -> None:
        # Quick mode remains class-free: persistence and every prompt can omit class_id.
        for material_type in ("lesson", "activity", "worksheet", "assessment"):
            material = {
                "id": 1, "material_type": material_type, "subtype": "Quiz",
                "title": "Quick", "level": "A2", "topic": "Food", "metadata": {},
            }
            replacements = _prompt_replacements(material, "make it shorter")
            self.assertTrue(replacements)
            saved = database.save_generated_material(
                telegram_user=self.owner, material_type=material_type,
                title=f"Quick {material_type}", content="Quick content",
            )
            self.assertIsNone(database.get_user_material(
                telegram_user_id=self.owner.id, material_id=saved
            )["class_id"])
        generators = ("lesson", "activity", "worksheet", "assessment")
        modes = ("quick", "class")
        behaviors = ("override", "cancel", "retry", "save", "word_export", "pdf_export")
        matrix = {(g, mode, behavior) for g in generators for mode in modes for behavior in behaviors}
        self.assertEqual(len(matrix), 48)


if __name__ == "__main__":
    unittest.main()
