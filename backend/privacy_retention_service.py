"""TeacherOS Privacy Hard Deletion & Retention Engine (Day 27).

Implements hard deletion and GDPR right-to-be-forgotten across user accounts,
classes, materials, and automated retention cleanup jobs.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from database import database_connection
from security_service import log_security_event

logger = logging.getLogger(__name__)


def hard_delete_class_data(
    *,
    telegram_user_id: int,
    class_id: int,
    database_path: Path | None = None,
) -> dict[str, int]:
    """Permanently delete all class data, lesson history, evidence, and progress reports."""
    deleted_counts: dict[str, int] = {}
    with database_connection(database_path) as conn:
        user = conn.execute("SELECT id FROM users WHERE telegram_user_id = ?", (telegram_user_id,)).fetchone()
        if not user:
            return {"classes": 0}
        user_id = int(user["id"])

        # Verify class ownership
        cls_row = conn.execute(
            "SELECT id, display_name FROM classes WHERE id = ? AND user_id = ?",
            (class_id, user_id),
        ).fetchone()
        if not cls_row:
            return {"classes": 0}

        # 1. Delete materials explicitly linked to class
        mat_cur = conn.execute(
            "DELETE FROM materials WHERE class_id = ? AND user_id = ?",
            (class_id, user_id),
        )
        deleted_counts["materials"] = mat_cur.rowcount

        # 2. Delete class (cascades to curriculum units, lessons, outcomes, evidence batches, reports, pins)
        cls_cur = conn.execute(
            "DELETE FROM classes WHERE id = ? AND user_id = ?",
            (class_id, user_id),
        )
        deleted_counts["classes"] = cls_cur.rowcount

    log_security_event(
        event_type="class_data_purged",
        severity="low",
        user_id=user_id,
        target_resource=f"class:{class_id}",
        details=deleted_counts,
        database_path=database_path,
    )
    return deleted_counts


def hard_delete_user_account(
    *,
    telegram_user_id: int,
    database_path: Path | None = None,
) -> dict[str, int]:
    """Permanently delete all user profile data, classes, materials, and preferences."""
    deleted_counts: dict[str, int] = {}
    with database_connection(database_path) as conn:
        user = conn.execute("SELECT id FROM users WHERE telegram_user_id = ?", (telegram_user_id,)).fetchone()
        if not user:
            return {"users": 0}
        user_id = int(user["id"])

        # Cascade delete user record
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        deleted_counts["users"] = cur.rowcount

    log_security_event(
        event_type="account_purged",
        severity="medium",
        user_id=None,
        target_resource=f"user:{telegram_user_id}",
        details=deleted_counts,
        database_path=database_path,
    )
    return deleted_counts


def run_retention_cleanup_job(
    *,
    retention_days: int = 365,
    database_path: Path | None = None,
) -> dict[str, int]:
    """Purge unverified draft evidence batches older than retention threshold."""
    if isinstance(retention_days, bool) or not isinstance(retention_days, int) or retention_days < 1:
        raise ValueError("retention_days must be a positive integer.")
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    purged: dict[str, int] = {}

    with database_connection(database_path) as conn:
        # Delete unverified draft evidence older than cutoff
        cur = conn.execute(
            """
            DELETE FROM evidence_batches
            WHERE status IN ('draft', 'purged') AND created_at < ?
            """,
            (cutoff_str,),
        )
        purged["stale_evidence_batches"] = cur.rowcount

    log_security_event(
        event_type="retention_cleanup_executed",
        severity="low",
        target_resource="system:retention_job",
        details=purged,
        database_path=database_path,
    )
    return purged
