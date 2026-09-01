"""Tests for TeacherOS Day 28 Five-Teacher Release Rehearsal and Journey Metrics."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day28-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day28-key")

import database
from day28_migration import SCHEMA_VERSION
from feature_flags import FEATURE_ENV_VARS
from rehearsal_service import (
    REHEARSAL_PERSONAS,
    TOP_3_BEHAVIOR_CHANGES,
    execute_teacher_rehearsal_mission,
    run_full_rehearsal_suite,
)


class Day28ReleaseRehearsalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day28-test-")
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "teacheros.db"
        database.initialize_database(self.db_path)

        self.flags_patcher = patch.dict(
            os.environ,
            {name: "true" for name in FEATURE_ENV_VARS.values()},
        )
        self.flags_patcher.start()

        self.orig_db_path = database.DATABASE_PATH
        database.DATABASE_PATH = self.db_path

    def tearDown(self) -> None:
        database.DATABASE_PATH = self.orig_db_path
        self.flags_patcher.stop()
        self.temp_dir.cleanup()

    def test_schema_v28_initialized(self) -> None:
        """Verify schema version 28 and rehearsal tables."""
        with database.database_connection(self.db_path) as conn:
            ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
            self.assertGreaterEqual(ver, 28)
            tbl1 = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='rehearsal_sessions'"
            ).fetchone()
            tbl2 = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='rehearsal_task_metrics'"
            ).fetchone()
            self.assertIsNotNone(tbl1)
            self.assertIsNotNone(tbl2)

    def test_rehearsal_personas_definition(self) -> None:
        """Verify 5 distinct personas spanning CEFR levels A1-C1."""
        self.assertEqual(len(REHEARSAL_PERSONAS), 5)
        levels = {p["level"] for p in REHEARSAL_PERSONAS}
        self.assertEqual(levels, {"A1", "A2", "B1", "B2", "C1"})

    def test_single_teacher_mission_execution(self) -> None:
        """Verify executing full 9-step mission for one persona."""
        persona = REHEARSAL_PERSONAS[0]
        session = execute_teacher_rehearsal_mission(persona, database_path=self.db_path)

        self.assertEqual(session["teacher"], persona["username"])
        self.assertEqual(session["tasks_completed"], 9)
        self.assertEqual(session["tasks_total"], 9)
        self.assertGreater(session["total_duration_seconds"], 0)
        self.assertGreaterEqual(session["avg_seq_score"], 6.0)
        self.assertGreaterEqual(session["trust_score"], 4.5)
        self.assertEqual(len(session["tasks"]), 9)

    def test_full_rehearsal_suite_aggregation(self) -> None:
        """Verify executing all 5 teacher missions and computing summary metrics."""
        summary = run_full_rehearsal_suite(database_path=self.db_path)

        self.assertEqual(summary["teachers_tested"], 5)
        self.assertEqual(summary["tasks_assigned"], 45)
        self.assertEqual(summary["tasks_completed"], 45)
        self.assertEqual(summary["completion_rate_percent"], 100.0)
        self.assertEqual(summary["navigation_rescues_required"], 0)
        self.assertGreaterEqual(summary["overall_avg_seq_score"], 6.0)
        self.assertGreaterEqual(summary["overall_trust_score"], 4.5)
        self.assertGreaterEqual(summary["total_est_minutes_saved"], 200)

    def test_top_3_behavior_changes_ranked(self) -> None:
        """Verify top 3 behavior-backed UX changes are ranked."""
        self.assertEqual(len(TOP_3_BEHAVIOR_CHANGES), 3)
        self.assertEqual(TOP_3_BEHAVIOR_CHANGES[0]["rank"], 1)
        self.assertEqual(TOP_3_BEHAVIOR_CHANGES[0]["severity"], "P1")
        self.assertIn("One-Tap Evidence Batch Anonymization", TOP_3_BEHAVIOR_CHANGES[0]["title"])

    def test_database_persistence_of_metrics(self) -> None:
        """Verify sessions and task metrics rows exist in the database."""
        run_full_rehearsal_suite(database_path=self.db_path)

        with database.database_connection(self.db_path) as conn:
            sess_count = conn.execute("SELECT COUNT(*) FROM rehearsal_sessions").fetchone()[0]
            task_count = conn.execute("SELECT COUNT(*) FROM rehearsal_task_metrics").fetchone()[0]

            self.assertEqual(sess_count, 5)
            self.assertEqual(task_count, 45)


if __name__ == "__main__":
    unittest.main()
