from __future__ import annotations

import json
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
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day18-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day18-key")

import database
from analysis_followup_keyboards import (
    analysis_followup_duration_keyboard,
    analysis_followup_types_keyboard,
    analysis_followup_view_keyboard,
)
from analysis_followup_service import (
    accept_followup_action,
    create_analysis_followup_action,
    get_analysis_followup_action,
    list_analysis_followup_actions,
)
from class_service import create_class
from day18_migration import apply_schema_v18
from day22_migration import SCHEMA_VERSION
from evidence_analysis_service import (
    analyze_evidence_batch,
    approve_evidence_analysis,
    get_evidence_analysis,
)
from evidence_service import delete_evidence_batch, submit_evidence_batch
from feature_flags import FEATURE_ENV_VARS


def _teacher(identifier: int, username: str = "teacher") -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        username=f"{username}_{identifier}",
        first_name="Followup",
        last_name="Teacher",
        language_code="en",
    )


class Day18AnalysisFollowupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day18-tests-")
        self.db_path = Path(self.temp_dir.name) / "teacheros_day18.db"
        database.initialize_database(self.db_path)

        self.teacher_a = _teacher(180_001, "teacher_a")
        self.teacher_b = _teacher(180_002, "teacher_b")

        self.flags_patcher = patch.dict(
            os.environ,
            {
                FEATURE_ENV_VARS["classes"]: "true",
                FEATURE_ENV_VARS["continuity"]: "true",
                FEATURE_ENV_VARS["evidence"]: "true",
            },
            clear=False,
        )
        self.flags_patcher.start()

        self.class_a = create_class(
            telegram_user=self.teacher_a,
            display_name="B2 Upper-Intermediate Writing",
            level="B2",
            age_group="adults",
            learner_count_band="13_20",
            goal="Essay transitions and subject-verb agreement",
            database_path=self.db_path,
        )

        # Create batch and analysis
        raw_text = (
            "Student 1: Sustainable tourism promotes cultural preservation.\n"
            "Student 2: He don't like overcrowded destinations.\n"
            "Student 3: Ecotourism depend of local communities.\n"
            "Student 4: Long-term ecological benefits are undeniable.\n"
        )
        self.batch_a = submit_evidence_batch(
            telegram_user=self.teacher_a,
            class_id=self.class_a["id"],
            evidence_type="writing",
            raw_text=raw_text,
            retention_policy="30_days",
            privacy_confirmed=True,
            database_path=self.db_path,
        )
        self.analysis_a = analyze_evidence_batch(
            telegram_user=self.teacher_a,
            batch_id=self.batch_a["id"],
            database_path=self.db_path,
        )

    def tearDown(self) -> None:
        self.flags_patcher.stop()
        self.temp_dir.cleanup()

    def test_schema_v18_is_idempotent_and_creates_tables(self) -> None:
        with database.database_connection(self.db_path) as conn:
            apply_schema_v18(conn)
            max_v = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
            self.assertEqual(max_v, SCHEMA_VERSION)

            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            self.assertIn("analysis_followup_actions", tables)
            self.assertIn("material_evidence_links", tables)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_cannot_create_followup_from_unapproved_analysis(self) -> None:
        # analysis_a is in draft status
        self.assertEqual(self.analysis_a["status"], "draft")
        self.assertEqual(self.analysis_a["approved"], 0)

        with self.assertRaises(ValueError) as ctx:
            create_analysis_followup_action(
                telegram_user=self.teacher_a,
                analysis_id=self.analysis_a["id"],
                action_type="reteach_lesson",
                database_path=self.db_path,
            )
        self.assertIn("unapproved analysis", str(ctx.exception))

    def test_create_reteaching_lesson_from_approved_analysis(self) -> None:
        approved = approve_evidence_analysis(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            database_path=self.db_path,
        )
        self.assertIsNotNone(approved)

        followup = create_analysis_followup_action(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            action_type="reteach_lesson",
            duration_minutes=45,
            database_path=self.db_path,
        )
        self.assertIsNotNone(followup)
        self.assertEqual(followup["action_type"], "reteach_lesson")
        self.assertEqual(followup["duration_minutes"], 45)
        self.assertEqual(followup["status"], "generated")

        content = followup["content_markdown"]
        self.assertIn("What this addresses:", content)
        self.assertIn(self.analysis_a["analysis_uuid"], content)
        self.assertIn("Concept Checking Questions", content)
        self.assertIn("Exit Ticket", content)

    def test_create_targeted_worksheet_from_approved_analysis(self) -> None:
        approve_evidence_analysis(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            database_path=self.db_path,
        )
        ws = create_analysis_followup_action(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            action_type="targeted_worksheet",
            duration_minutes=30,
            database_path=self.db_path,
        )
        self.assertIsNotNone(ws)
        self.assertEqual(ws["action_type"], "targeted_worksheet")

        content = ws["content_markdown"]
        self.assertIn("Spot and Underline", content)
        self.assertIn("Rewrite and Correct", content)
        self.assertIn("ANSWER KEY & TEACHER NOTES", content)

    def test_create_differentiated_practice_three_tiers(self) -> None:
        approve_evidence_analysis(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            database_path=self.db_path,
        )
        dif = create_analysis_followup_action(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            action_type="differentiated_practice",
            database_path=self.db_path,
        )
        self.assertIsNotNone(dif)
        content = dif["content_markdown"]
        self.assertIn("Tier 1: Support Route", content)
        self.assertIn("Tier 2: Core Route", content)
        self.assertIn("Tier 3: Challenge Route", content)
        self.assertIn("Sentence Frames:", content)
        self.assertIn("Word Bank:", content)

    def test_create_group_activity_and_roles(self) -> None:
        approve_evidence_analysis(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            database_path=self.db_path,
        )
        grp = create_analysis_followup_action(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            action_type="group_activity",
            database_path=self.db_path,
        )
        self.assertIsNotNone(grp)
        content = grp["content_markdown"]
        self.assertIn("Fluid Group Collaboration", content)
        self.assertIn("Rule Captain", content)
        self.assertIn("Sentence Editor", content)

    def test_create_reassessment_formative_check(self) -> None:
        approve_evidence_analysis(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            database_path=self.db_path,
        )
        rea = create_analysis_followup_action(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            action_type="reassessment",
            duration_minutes=15,
            database_path=self.db_path,
        )
        self.assertIsNotNone(rea)
        content = rea["content_markdown"]
        self.assertIn("Formative Reassessment", content)
        self.assertIn("Marking Rubric", content)

    def test_create_targeted_homework_task(self) -> None:
        approve_evidence_analysis(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            database_path=self.db_path,
        )
        hw = create_analysis_followup_action(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            action_type="homework",
            database_path=self.db_path,
        )
        self.assertIsNotNone(hw)
        content = hw["content_markdown"]
        self.assertIn("Targeted Home Practice", content)
        self.assertIn("Self-Audit", content)

    def test_saves_directly_to_class_library_and_links_material(self) -> None:
        approve_evidence_analysis(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            database_path=self.db_path,
        )
        followup = create_analysis_followup_action(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            action_type="reteach_lesson",
            save_to_library=True,
            database_path=self.db_path,
        )
        mat_id = followup.get("material_id")
        self.assertIsNotNone(mat_id)

        with database.database_connection(self.db_path) as conn:
            mat = conn.execute("SELECT * FROM materials WHERE id = ?", (mat_id,)).fetchone()
            self.assertIsNotNone(mat)
            self.assertEqual(mat["class_id"], self.class_a["id"])
            self.assertIn("What this addresses:", mat["content"])

            link = conn.execute(
                "SELECT * FROM material_evidence_links WHERE material_id = ? AND analysis_id = ?",
                (mat_id, self.analysis_a["id"]),
            ).fetchone()
            self.assertIsNotNone(link)

    def test_accept_followup_action_completes_conversion_pipeline(self) -> None:
        approve_evidence_analysis(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            database_path=self.db_path,
        )
        followup = create_analysis_followup_action(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            action_type="reteach_lesson",
            database_path=self.db_path,
        )
        self.assertEqual(followup["status"], "generated")

        accepted = accept_followup_action(
            telegram_user=self.teacher_a,
            followup_id=followup["id"],
            database_path=self.db_path,
        )
        self.assertIsNotNone(accepted)
        self.assertEqual(accepted["status"], "accepted")

        with database.database_connection(self.db_path) as conn:
            events = conn.execute(
                "SELECT event_name FROM product_events WHERE event_name IN ('evidence_analysis_approved', 'followup_created', 'followup_accepted')"
            ).fetchall()
            names = [e[0] for e in events]
            self.assertIn("evidence_analysis_approved", names)
            self.assertIn("followup_created", names)
            self.assertIn("followup_accepted", names)

    def test_raw_evidence_purge_preserves_followup_and_provenance(self) -> None:
        approve_evidence_analysis(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            database_path=self.db_path,
        )
        followup = create_analysis_followup_action(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            action_type="targeted_worksheet",
            database_path=self.db_path,
        )

        # Delete underlying evidence batch
        delete_evidence_batch(
            telegram_user=self.teacher_a,
            batch_id=self.batch_a["id"],
            database_path=self.db_path,
        )

        # Follow-up action remains fully intact
        fa_record = get_analysis_followup_action(
            telegram_user=self.teacher_a,
            followup_id=followup["id"],
            database_path=self.db_path,
        )
        self.assertIsNotNone(fa_record)
        self.assertIn("Spot and Underline", fa_record["content_markdown"])

    def test_multi_tenant_isolation_guards(self) -> None:
        approve_evidence_analysis(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            database_path=self.db_path,
        )
        followup = create_analysis_followup_action(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            action_type="reteach_lesson",
            database_path=self.db_path,
        )

        # Teacher B cannot create follow-up from Teacher A's analysis
        with self.assertRaises(ValueError):
            create_analysis_followup_action(
                telegram_user=self.teacher_b,
                analysis_id=self.analysis_a["id"],
                action_type="reteach_lesson",
                database_path=self.db_path,
            )

        # Teacher B cannot view or accept Teacher A's follow-up
        self.assertIsNone(
            get_analysis_followup_action(
                telegram_user=self.teacher_b,
                followup_id=followup["id"],
                database_path=self.db_path,
            )
        )
        self.assertIsNone(
            accept_followup_action(
                telegram_user=self.teacher_b,
                followup_id=followup["id"],
                database_path=self.db_path,
            )
        )

    def test_zero_raw_evidence_in_telemetry_and_prompts(self) -> None:
        approve_evidence_analysis(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            database_path=self.db_path,
        )
        followup = create_analysis_followup_action(
            telegram_user=self.teacher_a,
            analysis_id=self.analysis_a["id"],
            action_type="group_activity",
            database_path=self.db_path,
        )
        accept_followup_action(
            telegram_user=self.teacher_a,
            followup_id=followup["id"],
            database_path=self.db_path,
        )

        with database.database_connection(self.db_path) as conn:
            events = conn.execute("SELECT properties_json FROM product_events").fetchall()
            for ev in events:
                self.assertNotIn("Sustainable tourism", str(ev["properties_json"]))
                self.assertNotIn("overcrowded destinations", str(ev["properties_json"]))

    def test_keyboards_are_compact_and_within_64_bytes(self) -> None:
        kbs = [
            analysis_followup_types_keyboard(1, 1, 1),
            analysis_followup_duration_keyboard(1, "ret", 1, 1),
            analysis_followup_view_keyboard(1, 1, 1, 1, 1, accepted=False),
            analysis_followup_view_keyboard(1, 1, 1, None, 1, accepted=True),
        ]
        for kb in kbs:
            for row in kb.inline_keyboard:
                for btn in row:
                    payload = btn.callback_data.encode("utf-8")
                    self.assertLessEqual(
                        len(payload), 64, f"Payload '{btn.callback_data}' exceeds 64 bytes"
                    )
