"""Tests for TeacherOS Day 25 Centralized Entitlements and Commercial Value Packaging."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day25-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day25-key")

import database
from class_service import create_class
from day25_migration import SCHEMA_VERSION
from entitlement_service import (
    TIER_LIMITS,
    can_complete_teaching_loop,
    check_feature_access,
    get_contextual_upgrade_prompt,
    record_entitlement_event,
)
from feature_flags import FEATURE_ENV_VARS
from subscription_service import class_creation_access_for_user


class Day25EntitlementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day25-test-")
        self.db_path = Path(self.temp_dir.name) / "teacheros.db"
        database.initialize_database(self.db_path)

        self.flags_patcher = patch.dict(
            os.environ,
            {
                FEATURE_ENV_VARS["classes"]: "true",
                FEATURE_ENV_VARS["continuity"]: "true",
                FEATURE_ENV_VARS["entitlements"]: "true",
            },
        )
        self.flags_patcher.start()

        self.orig_db_path = database.DATABASE_PATH
        database.DATABASE_PATH = self.db_path

        self.teacher_a = SimpleNamespace(
            id=250_101,
            username="teacher_a",
            first_name="Alice",
            last_name="Teacher",
            language_code="en",
        )
        self.teacher_b = SimpleNamespace(
            id=250_102,
            username="teacher_b",
            first_name="Bob",
            last_name="Teacher",
            language_code="en",
        )

        with database.database_connection(self.db_path) as conn:
            self.user_a_id = database.ensure_database_user(conn, self.teacher_a)
            self.user_b_id = database.ensure_database_user(conn, self.teacher_b)

    def tearDown(self) -> None:
        database.DATABASE_PATH = self.orig_db_path
        self.flags_patcher.stop()
        self.temp_dir.cleanup()

    def test_schema_v25_initialized(self) -> None:
        """Verify schema version 25 and entitlement_events table creation."""
        with database.database_connection(self.db_path) as conn:
            ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
            self.assertGreaterEqual(ver, 25)
            tbl = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='entitlement_events'"
            ).fetchone()
            self.assertIsNotNone(tbl)

    def test_centralized_tier_limits(self) -> None:
        """Verify plan limit definitions for Free, Pro, and Premium tiers."""
        self.assertEqual(TIER_LIMITS["free"]["active_classes"], 1)
        self.assertEqual(TIER_LIMITS["pro"]["active_classes"], 10)
        self.assertIsNone(TIER_LIMITS["premium"]["active_classes"])

        self.assertEqual(TIER_LIMITS["free"]["daily_generations"], 10)
        self.assertEqual(TIER_LIMITS["pro"]["daily_generations"], 50)
        self.assertIsNone(TIER_LIMITS["premium"]["daily_generations"])

        self.assertFalse(TIER_LIMITS["free"]["progress_reports_export"])
        self.assertTrue(TIER_LIMITS["pro"]["progress_reports_export"])
        self.assertTrue(TIER_LIMITS["premium"]["progress_reports_export"])

    def test_check_feature_access_free_tier(self) -> None:
        """Verify feature access evaluation for free tier users."""
        access_cls = check_feature_access(self.teacher_a.id, "active_classes", database_path=self.db_path)
        self.assertTrue(access_cls["allowed"])
        self.assertEqual(access_cls["limit"], 1)

        # Create one class to reach limit
        create_class(
            telegram_user=self.teacher_a,
            display_name="Class 1",
            level="B1",
            age_group="adults",
            learner_count_band="6_12",
            goal="Speaking fluency",
            database_path=self.db_path,
        )

        access_cls_blocked = check_feature_access(self.teacher_a.id, "active_classes", database_path=self.db_path)
        self.assertFalse(access_cls_blocked["allowed"])
        self.assertIsNotNone(access_cls_blocked["upgrade_prompt"])

        access_exp = check_feature_access(self.teacher_a.id, "progress_reports_export", database_path=self.db_path)
        self.assertFalse(access_exp["allowed"])

    def test_contextual_upgrade_prompts(self) -> None:
        """Verify upgrade prompts are outcome-oriented and never mention technical 'tokens'."""
        prompt_en = get_contextual_upgrade_prompt("active_classes", "en")
        self.assertIn("manage up to 10 classes", prompt_en)
        self.assertNotIn("token", prompt_en.lower())

        prompt_fa = get_contextual_upgrade_prompt("active_classes", "fa")
        self.assertIn("۱۰ کلاس", prompt_fa)
        self.assertNotIn("توکن", prompt_fa)

    def test_record_entitlement_events(self) -> None:
        """Verify recording valid funnel events and validating event types."""
        evt = record_entitlement_event(
            user_id=self.user_a_id,
            event_type="viewed",
            plan_code="pro",
            feature_key="active_classes",
            metadata={"source": "class_setup"},
            database_path=self.db_path,
        )
        self.assertEqual(evt["event_type"], "viewed")
        self.assertEqual(evt["plan_code"], "pro")

        with self.assertRaises(ValueError):
            record_entitlement_event(
                user_id=self.user_a_id,
                event_type="invalid_event_xyz",
                plan_code="pro",
                database_path=self.db_path,
            )

    def test_idempotent_subscription_activation(self) -> None:
        """Verify duplicate payment verifications do not create duplicate active subscriptions."""
        order = database.create_payment_order(
            telegram_user=self.teacher_a,
            purpose="Pro Subscription",
            amount=149_000,
            currency="IRT",
            callback_token_hash="b" * 64,
            is_sandbox=True,
            product_code="pro",
            subscription_days=30,
        )
        payment_id = int(order["id"])
        database.set_payment_pending(
            payment_id=payment_id,
            authority="AUTH_54321",
            payment_url="https://sandbox.zarinpal.com/pg/StartPay/AUTH_54321",
        )

        p1 = database.mark_payment_paid(
            payment_id=payment_id,
            authority="AUTH_54321",
            ref_id="REF_9999",
            card_pan=None,
            card_hash=None,
            provider_code=100,
            provider_message="Success",
        )
        p2 = database.mark_payment_paid(
            payment_id=payment_id,
            authority="AUTH_54321",
            ref_id="REF_9999",
            card_pan=None,
            card_hash=None,
            provider_code=100,
            provider_message="Success",
        )

        self.assertEqual(p1["status"], "paid")
        self.assertEqual(p2["status"], "paid")

        with database.database_connection(self.db_path) as conn:
            subs = conn.execute(
                "SELECT * FROM subscriptions WHERE source_payment_id = ?", (payment_id,)
            ).fetchall()
            self.assertEqual(len(subs), 1)

    def test_free_teaching_loop_guarantee(self) -> None:
        """Verify Free-tier users have sufficient limits to complete 1 full teaching loop."""
        guaranteed = can_complete_teaching_loop(self.teacher_b.id, database_path=self.db_path)
        self.assertTrue(guaranteed)

    def test_class_creation_access_integration(self) -> None:
        """Verify subscription_service delegates seamlessly to entitlement_service."""
        access = class_creation_access_for_user(self.teacher_a.id)
        self.assertTrue(access["allowed"])
        self.assertEqual(access["plan_code"], "free")
        self.assertEqual(access["class_limit"], 1)


if __name__ == "__main__":
    unittest.main()
