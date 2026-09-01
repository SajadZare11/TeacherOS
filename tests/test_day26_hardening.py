"""Tests for TeacherOS Day 26 Hardening, Reliability, Backups, and Observability."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day26-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day26-key")

import database
from backup_service import check_disk_space, create_database_backup, restore_database_backup
from day27_migration import SCHEMA_VERSION
from feature_flags import FEATURE_ENV_VARS
from observability import (
    calculate_percentiles,
    get_system_health_telemetry,
    record_failure,
    record_health_snapshot,
    record_latency,
)
from resilience import (
    DatabaseLockError,
    DiskSpaceLowError,
    ExportFailureError,
    ProviderInvalidResponseError,
    ProviderTimeoutError,
    TeacherOSError,
    execute_with_retry,
    execute_with_retry_async,
    redact_sensitive_text,
)


class Day26HardeningTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="teacheros-day26-test-")
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "teacheros.db"
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

    def tearDown(self) -> None:
        database.DATABASE_PATH = self.orig_db_path
        self.flags_patcher.stop()
        self.temp_dir.cleanup()

    def test_schema_v26_initialized(self) -> None:
        """Verify schema version 26 and system_health_snapshots table creation."""
        with database.database_connection(self.db_path) as conn:
            ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
            self.assertGreaterEqual(ver, 26)
            tbl = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='system_health_snapshots'"
            ).fetchone()
            self.assertIsNotNone(tbl)

    def test_structured_error_categories(self) -> None:
        """Verify custom structured exceptions, subsystems, and actions."""
        p_err = ProviderTimeoutError()
        self.assertIsInstance(p_err, TeacherOSError)
        self.assertEqual(p_err.subsystem, "ai_gateway")
        self.assertEqual(p_err.recommended_action, "retry_with_backoff")

        db_err = DatabaseLockError()
        self.assertEqual(db_err.subsystem, "database")

        disk_err = DiskSpaceLowError()
        self.assertEqual(disk_err.subsystem, "storage")

        exp_err = ExportFailureError()
        self.assertEqual(exp_err.subsystem, "exports")

        inv_err = ProviderInvalidResponseError()
        self.assertEqual(inv_err.recommended_action, "regenerate")

    def test_execute_with_retry_success(self) -> None:
        """Verify synchronous retry recovers from transient failures."""
        attempts = 0

        def _op() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise ProviderTimeoutError("Gateway temporary timeout")
            return "success_recovered"

        res = execute_with_retry(
            _op,
            max_retries=3,
            base_delay=0.01,
            max_delay=0.05,
            jitter=False,
            retry_exceptions=(ProviderTimeoutError,),
        )
        self.assertEqual(res, "success_recovered")
        self.assertEqual(attempts, 2)

    def test_execute_with_retry_exceeded(self) -> None:
        """Verify synchronous retry raises original exception when max attempts exceeded."""
        def _failing_op() -> None:
            raise DatabaseLockError("Lock error")

        with self.assertRaises(DatabaseLockError):
            execute_with_retry(
                _failing_op,
                max_retries=2,
                base_delay=0.01,
                max_delay=0.02,
                jitter=False,
                retry_exceptions=(DatabaseLockError,),
            )

    async def test_execute_with_retry_async(self) -> None:
        """Verify asynchronous retry recovers from transient coroutine failures."""
        attempts = 0

        async def _async_op() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise ProviderTimeoutError("Async timeout")
            return "async_recovered"

        res = await execute_with_retry_async(
            _async_op,
            max_retries=3,
            base_delay=0.01,
            max_delay=0.05,
            jitter=False,
            retry_exceptions=(ProviderTimeoutError,),
        )
        self.assertEqual(res, "async_recovered")
        self.assertEqual(attempts, 2)

    def test_sensitive_data_redaction(self) -> None:
        """Verify redaction of OpenRouter keys, bot tokens, emails, and card numbers."""
        text = (
            "API Key sk-or-v1-0987654321fedcba and Bot 987654321:XYZ_token_123456789. "
            "Teacher john.smith@school.edu processed card 5555 5555 5555 4321."
        )
        redacted = redact_sensitive_text(text)
        self.assertIn("sk-or-v1-[REDACTED]", redacted)
        self.assertIn("[BOT_TOKEN_REDACTED]", redacted)
        self.assertIn("j***@school.edu", redacted)
        self.assertIn("****-****-****-4321", redacted)
        self.assertNotIn("5555 5555 5555 4321", redacted)

    def test_database_backup_and_rotation(self) -> None:
        """Verify online SQLite backup generation, WAL integrity, and rotation."""
        backup_dir = self.temp_path / "backups_test"
        b1 = create_database_backup(source_path=self.db_path, backup_dir=backup_dir, label="t1", keep_count=2)
        b2 = create_database_backup(source_path=self.db_path, backup_dir=backup_dir, label="t2", keep_count=2)
        b3 = create_database_backup(source_path=self.db_path, backup_dir=backup_dir, label="t3", keep_count=2)

        self.assertTrue(b3.is_file())
        self.assertGreater(b3.stat().st_size, 0)
        files = list(backup_dir.glob("teacheros_backup_*.db"))
        self.assertEqual(len(files), 2)

    def test_database_restore_drill(self) -> None:
        """Verify restoring a backup into a clean target directory passes integrity checks."""
        backup_dir = self.temp_path / "backups_restore"
        backup_file = create_database_backup(source_path=self.db_path, backup_dir=backup_dir, label="drill")

        restore_target = self.temp_path / "restored_dir" / "teacheros_restored.db"
        result = restore_database_backup(backup_file, restore_target)

        self.assertTrue(result["restored"])
        self.assertEqual(result["integrity"], "ok")
        self.assertEqual(result["foreign_key_issues"], 0)
        self.assertGreaterEqual(result["schema_version"], 26)

    def test_disk_space_check(self) -> None:
        """Verify disk capacity check returns structured data."""
        res = check_disk_space(path=self.temp_path, min_free_mb=10)
        self.assertGreater(res["free_mb"], 0)
        self.assertIn(res["status"], {"OK", "WARNING"})

    def test_observability_and_snapshots(self) -> None:
        """Verify recording latencies, failure events, and capturing health snapshots."""
        record_latency(110.0)
        record_latency(350.0)
        record_failure("provider_failures")
        record_failure("db_locks")

        p50, p95 = calculate_percentiles()
        self.assertGreater(p50, 0)
        self.assertGreaterEqual(p95, p50)

        snapshot = record_health_snapshot(database_path=self.db_path)
        self.assertIn("snapshot_uuid", snapshot)
        self.assertGreaterEqual(snapshot["schema_version"], 26)

        telemetry = get_system_health_telemetry(database_path=self.db_path)
        self.assertIn("status", telemetry)
        self.assertGreaterEqual(telemetry["provider_failures"], 1)


if __name__ == "__main__":
    unittest.main()
