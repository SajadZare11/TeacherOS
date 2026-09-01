from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from docx import Document

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

_TEMP_DIR = tempfile.TemporaryDirectory(prefix="teacheros-day1-smoke-")
os.environ["TEACHEROS_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "teacheros-smoke.db")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-smoke-token-not-used")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-smoke-key-not-used")
os.environ.setdefault("TEACHEROS_ADMIN_ID", "9001")
os.environ["ZARINPAL_SANDBOX"] = "true"
os.environ["TEACHEROS_LOCAL_PAYMENT_SIMULATOR"] = "true"

import database  # noqa: E402
import main as bot_main  # noqa: E402
from account_panel import _account_home_text  # noqa: E402
from pdf_document import create_pdf_export  # noqa: E402
from word_document import create_word_export  # noqa: E402


def user(user_id: int, name: str = "Day One Teacher") -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        username=f"teacher{user_id}",
        first_name=name,
        last_name="Baseline",
        language_code="en",
    )


class Day1CriticalPathSmokeTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Keep this module isolated even when a later-day test imports database first.
        database.DATABASE_PATH = Path(_TEMP_DIR.name) / "teacheros-smoke.db"
        database.initialize_database()
        cls.owner = user(9001)
        cls.other = user(9002, "Other Teacher")

    def test_01_current_schema_and_all_four_generation_types(self) -> None:
        expected_types = ("lesson", "activity", "worksheet", "assessment")
        for material_type in expected_types:
            material_id = database.save_generated_material(
                telegram_user=self.owner,
                material_type=material_type,
                title=f"Day 1 {material_type.title()} Smoke",
                content=(
                    f"# {material_type.title()}\n"
                    "Objective: Teachers can verify a complete classroom-ready result.\n\n"
                    "1. Warm-up\n2. Guided practice\n3. Check understanding\n\n"
                    "ANSWER KEY\n1. Verified"
                ),
                subtype="baseline",
                level="B1",
                topic="Travel",
                metadata={"source": "day1_offline_smoke"},
            )
            saved = database.get_user_material(
                telegram_user_id=self.owner.id,
                material_id=material_id,
            )
            self.assertIsNotNone(saved)
            self.assertEqual(saved["material_type"], material_type)
            self.assertIn("ANSWER KEY", saved["content"])

        health = database.database_healthcheck()
        self.assertEqual(health["schema_version"], 27)
        self.assertEqual(
            database.count_user_materials(telegram_user_id=self.owner.id),
            4,
        )

    def test_02_library_search_ownership_and_exports(self) -> None:
        results = database.search_user_materials(
            telegram_user_id=self.owner.id,
            query="Travel B1",
            limit=10,
        )
        self.assertEqual(len(results), 4)
        material_id = int(results[0]["id"])
        material = database.get_user_material(
            telegram_user_id=self.owner.id,
            material_id=material_id,
        )
        self.assertIsNotNone(material)
        self.assertIsNone(
            database.get_user_material(
                telegram_user_id=self.other.id,
                material_id=material_id,
            )
        )

        word_stream, word_name = create_word_export(material)
        pdf_stream, pdf_name = create_pdf_export(material)
        self.assertTrue(word_name.endswith(".docx"))
        self.assertTrue(pdf_name.endswith(".pdf"))
        word_bytes = word_stream.read()
        pdf_bytes = pdf_stream.read()
        self.assertEqual(word_bytes[:2], b"PK")
        self.assertEqual(pdf_bytes[:5], b"%PDF-")
        exported_document = Document(BytesIO(word_bytes))
        exported_text = "\n".join(
            paragraph.text for paragraph in exported_document.paragraphs
        )
        self.assertIn(str(material["title"]), exported_text)
        self.assertIn("answer key", exported_text.casefold())
        self.assertGreater(len(pdf_bytes), 1_000)
        self.assertIn(b"/Type /Page", pdf_bytes)
        database.record_export_event(
            telegram_user=self.owner,
            export_format="word",
            material_id=material_id,
        )
        database.record_export_event(
            telegram_user=self.owner,
            export_format="pdf",
            material_id=material_id,
        )

    def test_03_feedback_account_payment_sandbox_and_admin(self) -> None:
        feedback_id = database.save_beta_feedback(
            telegram_user=self.owner,
            rating=5,
            area="lesson",
            message="Day 1 baseline completed successfully.",
        )
        feedback = database.get_admin_feedback_summary(limit=5)
        self.assertGreaterEqual(feedback["total"], 1)
        self.assertTrue(database.update_feedback_status(feedback_id=feedback_id, status="reviewed"))

        entitlement = database.get_user_entitlement(telegram_user_id=self.owner.id)
        account_text = _account_home_text(entitlement)
        self.assertIn("TeacherOS", account_text)

        token_hash = hashlib.sha256(b"day1-sandbox-callback").hexdigest()
        payment = database.create_payment_order(
            telegram_user=self.owner,
            purpose="TeacherOS Pro smoke test",
            amount=149000,
            currency="IRT",
            callback_token_hash=token_hash,
            is_sandbox=True,
            product_code="pro",
            subscription_days=30,
        )
        pending = database.set_payment_pending(
            payment_id=int(payment["id"]),
            authority="DAY1-SANDBOX-AUTHORITY",
            payment_url="http://127.0.0.1:8080/sandbox/day1",
            provider_code=100,
            provider_message="Offline sandbox smoke",
        )
        self.assertEqual(pending["status"], "pending")
        paid = database.mark_payment_paid(
            payment_id=int(payment["id"]),
            authority="DAY1-SANDBOX-AUTHORITY",
            ref_id="DAY1-REF",
            card_pan="000000******0000",
            card_hash="day1-card-hash",
            provider_code=100,
            provider_message="Offline sandbox verified",
        )
        self.assertEqual(paid["status"], "paid")
        self.assertEqual(paid["activated_plan"], "pro")
        self.assertIsNone(
            database.get_user_payment(
                telegram_user_id=self.other.id,
                payment_id=int(payment["id"]),
            )
        )

        admin = database.get_admin_dashboard_summary()
        self.assertGreaterEqual(admin["users"]["total"], 1)
        self.assertEqual(admin["saved_materials"], 4)

    async def test_04_api_failure_returns_recoverable_message(self) -> None:
        update = SimpleNamespace(
            message=SimpleNamespace(
                text="Create a short review task",
                reply_text=AsyncMock(),
            ),
            effective_user=self.owner,
            effective_chat=SimpleNamespace(id=12345),
        )
        context = SimpleNamespace(
            user_data={},
            bot=SimpleNamespace(send_chat_action=AsyncMock()),
        )
        access = {"allowed": True, "plan_code": "pro"}
        with (
            patch.object(bot_main, "generation_access_for_user", return_value=access),
            patch.object(bot_main, "selected_openrouter_model", return_value="offline-model"),
            patch.object(bot_main, "generate_artifact", AsyncMock(side_effect=TimeoutError("offline"))),
        ):
            await bot_main.handle_message(update, context)

        update.message.reply_text.assert_awaited_once()
        message = update.message.reply_text.await_args.args[0]
        self.assertIn("could not generate a safe response", message)
        self.assertIn("send it again to retry", message)

    def test_05_required_command_and_callback_routes_are_registered(self) -> None:
        source = (BACKEND_DIR / "main.py").read_text(encoding="utf-8")
        required_commands = (
            "start", "library", "search", "usage", "plan", "payments",
            "feedback", "admin", "admin_users", "admin_stats", "admin_revenue",
        )
        required_callbacks = (
            "lesson", "activity_", "worksheet_", "quiz_", "library_", "search_",
            "account_", "feedback_", "payment_", "export_", "pdf_", "admin_",
        )
        for command in required_commands:
            self.assertIn(f'CommandHandler("{command}"', source)
        for namespace in required_callbacks:
            self.assertIn(namespace, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
