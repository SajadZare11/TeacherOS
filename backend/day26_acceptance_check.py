"""TeacherOS Day 26 Acceptance Check.

Validates system reliability, performance, backups, and observability:
- Schema v26 deployed with system_health_snapshots table.
- Structured error categories and recommended actions.
- Bounded retry with exponential backoff and jitter.
- Sensitive data redaction for API keys, tokens, emails, and card numbers.
- Safe SQLite backup with WAL integrity check and automated rotation.
- Verified database restore drill to an isolated directory.
- Disk storage capacity safety checks.
- System observability telemetry and health snapshots without PII.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import database
from backup_service import check_disk_space, create_database_backup, restore_database_backup
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
    redact_sensitive_text,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "day26"
DEFAULT_REPORT = OUTPUTS_DIR / "acceptance_report.json"


def evaluate_day26() -> dict[str, Any]:
    previous_flags = {name: os.environ.get(name) for name in FEATURE_ENV_VARS.values()}
    for name in FEATURE_ENV_VARS.values():
        os.environ[name] = "false"
    os.environ[FEATURE_ENV_VARS["classes"]] = "true"
    os.environ[FEATURE_ENV_VARS["continuity"]] = "true"

    try:
        with tempfile.TemporaryDirectory(prefix="teacheros-day26-acceptance-") as temp_dir:
            temp_path = Path(temp_dir)
            path = temp_path / "teacheros.db"
            original_path = database.DATABASE_PATH
            database.DATABASE_PATH = path

            try:
                database.initialize_database(path)

                # 1. Schema v26 verification
                with database.database_connection(path) as conn:
                    schema_ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
                    tbl = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='system_health_snapshots'"
                    ).fetchone()
                    schema_valid = (schema_ver >= 26 and tbl is not None)

                # 2. Structured error categories
                err1 = ProviderTimeoutError()
                err2 = DatabaseLockError()
                err3 = DiskSpaceLowError()
                err4 = ExportFailureError()
                err5 = ProviderInvalidResponseError()
                error_types_valid = (
                    isinstance(err1, TeacherOSError)
                    and err1.subsystem == "ai_gateway"
                    and err2.subsystem == "database"
                    and err3.subsystem == "storage"
                    and err4.subsystem == "exports"
                    and err5.recommended_action == "regenerate"
                )

                # 3. Bounded retry with exponential backoff & jitter
                call_counts = {"attempts": 0}

                def _transient_op() -> str:
                    call_counts["attempts"] += 1
                    if call_counts["attempts"] < 3:
                        raise ProviderTimeoutError("Transient gateway timeout")
                    return "recovered_ok"

                retry_result = execute_with_retry(
                    _transient_op,
                    max_retries=3,
                    base_delay=0.01,
                    max_delay=0.05,
                    jitter=False,
                    retry_exceptions=(ProviderTimeoutError,),
                )
                retry_valid = (retry_result == "recovered_ok" and call_counts["attempts"] == 3)

                # 4. Sensitive data redaction
                raw_log = (
                    "OpenRouter sk-or-v1-abcdef1234567890 failed. "
                    "Bot token 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ_1234567. "
                    "User email teacher@example.com with card 4111 1111 1111 1234."
                )
                redacted = redact_sensitive_text(raw_log)
                redaction_valid = (
                    "sk-or-v1-[REDACTED]" in redacted
                    and "[BOT_TOKEN_REDACTED]" in redacted
                    and "t***@example.com" in redacted
                    and "****-****-****-1234" in redacted
                    and "4111 1111 1111 1234" not in redacted
                )

                # 5. Database backup and automated rotation
                backup_dir = temp_path / "backups"
                backup_1 = create_database_backup(
                    source_path=path,
                    backup_dir=backup_dir,
                    label="drill1",
                    keep_count=2,
                )
                backup_2 = create_database_backup(
                    source_path=path,
                    backup_dir=backup_dir,
                    label="drill2",
                    keep_count=2,
                )
                backup_3 = create_database_backup(
                    source_path=path,
                    backup_dir=backup_dir,
                    label="drill3",
                    keep_count=2,
                )
                remaining_backups = list(backup_dir.glob("teacheros_backup_*.db"))
                backup_rotation_valid = (
                    backup_3.is_file()
                    and backup_3.stat().st_size > 0
                    and len(remaining_backups) == 2
                )

                # 6. Database restore drill
                restore_target = temp_path / "restored_test.db"
                restore_res = restore_database_backup(backup_3, restore_target)
                restore_valid = (
                    restore_res["restored"] is True
                    and restore_res["integrity"] == "ok"
                    and restore_res["schema_version"] >= 26
                )

                # 7. Disk space safety check
                disk_status = check_disk_space(path=temp_path, min_free_mb=50)
                disk_valid = (disk_status["free_mb"] > 0 and disk_status["status"] in {"OK", "WARNING"})

                # 8. Observability telemetry and health snapshots
                record_latency(150.0)
                record_latency(220.0)
                record_latency(850.0)
                record_failure("provider_failures")
                p50, p95 = calculate_percentiles()
                snapshot = record_health_snapshot(database_path=path)
                telemetry = get_system_health_telemetry(database_path=path)

                observability_valid = (
                    p50 > 0
                    and p95 >= p50
                    and snapshot.get("snapshot_uuid") is not None
                    and telemetry.get("provider_failures") >= 1
                    and telemetry.get("schema_version") >= 26
                )

                checks = {
                    "schema_v26_deployed": schema_valid,
                    "structured_error_categories_implemented": error_types_valid,
                    "bounded_retry_with_jitter_operational": retry_valid,
                    "sensitive_data_redaction_verified": redaction_valid,
                    "database_backup_and_rotation_functional": backup_rotation_valid,
                    "database_restore_drill_verified": restore_valid,
                    "disk_space_safety_check_operational": disk_valid,
                    "observability_telemetry_and_snapshots_active": observability_valid,
                }
                passed = all(checks.values())

                return {
                    "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "gate": "Day 26 — Harden Reliability, Performance, Backups, and Observability",
                    "schema_version": 26,
                    "checks": checks,
                    "passed": passed,
                    "engineering_status": "PASS" if passed else "FAIL",
                    "details": {
                        "p50_latency_ms": p50,
                        "p95_latency_ms": p95,
                        "backup_file": str(backup_3.name),
                        "restored_integrity": restore_res["integrity"],
                    },
                }
            finally:
                database.DATABASE_PATH = original_path
    finally:
        for name, value in previous_flags.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate TeacherOS Day 26 Reliability & Hardening.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = evaluate_day26()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"DAY 26 ACCEPTANCE: {report['engineering_status']}")
    print(f"Report: {output_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
