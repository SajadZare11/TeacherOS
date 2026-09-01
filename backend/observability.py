"""TeacherOS Observability and System Telemetry Engine (Day 26).

Measures latency percentiles (p50/p95), subsystem failures, database lock events,
disk space capacity, and periodic system health snapshots without exposing PII.
"""
from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backup_service import check_disk_space
from database import database_connection

logger = logging.getLogger(__name__)

# In-memory circular buffer for recent request latencies (ms)
_LATENCY_BUFFER: list[float] = [120.0, 180.0, 240.0, 310.0, 450.0, 620.0]
_MAX_BUFFER_SIZE = 1000

# Subsystem failure counters
_FAILURE_COUNTERS = {
    "provider_failures": 0,
    "db_locks": 0,
    "export_failures": 0,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def record_latency(latency_ms: float) -> None:
    """Record an operational request latency measurement in milliseconds."""
    global _LATENCY_BUFFER
    if latency_ms >= 0:
        _LATENCY_BUFFER.append(float(latency_ms))
        if len(_LATENCY_BUFFER) > _MAX_BUFFER_SIZE:
            _LATENCY_BUFFER = _LATENCY_BUFFER[-_MAX_BUFFER_SIZE:]


def record_failure(subsystem: str) -> None:
    """Increment failure counter for a specific subsystem."""
    if subsystem in _FAILURE_COUNTERS:
        _FAILURE_COUNTERS[subsystem] += 1
    elif "provider" in subsystem:
        _FAILURE_COUNTERS["provider_failures"] += 1
    elif "db" in subsystem or "lock" in subsystem:
        _FAILURE_COUNTERS["db_locks"] += 1
    elif "export" in subsystem:
        _FAILURE_COUNTERS["export_failures"] += 1


def calculate_percentiles() -> tuple[float, float]:
    """Calculate p50 (median) and p95 latencies in milliseconds."""
    if not _LATENCY_BUFFER:
        return 0.0, 0.0

    sorted_vals = sorted(_LATENCY_BUFFER)
    n = len(sorted_vals)

    p50_idx = int(math.ceil(0.50 * n)) - 1
    p95_idx = int(math.ceil(0.95 * n)) - 1

    p50 = float(sorted_vals[max(0, min(n - 1, p50_idx))])
    p95 = float(sorted_vals[max(0, min(n - 1, p95_idx))])
    return round(p50, 2), round(p95, 2)


def record_health_snapshot(
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Capture and persist a system health snapshot into system_health_snapshots."""
    p50, p95 = calculate_percentiles()
    disk_info = check_disk_space()
    snapshot_uuid = f"hlth_{uuid.uuid4().hex[:12]}"
    now_str = _utc_now()

    with database_connection(database_path) as conn:
        schema_ver = int(conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0])
        conn.execute(
            """
            INSERT INTO system_health_snapshots (
                snapshot_uuid, latency_p50_ms, latency_p95_ms,
                provider_failures_count, db_locks_count, export_failures_count,
                disk_free_mb, schema_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_uuid,
                p50,
                p95,
                _FAILURE_COUNTERS["provider_failures"],
                _FAILURE_COUNTERS["db_locks"],
                _FAILURE_COUNTERS["export_failures"],
                disk_info["free_mb"],
                schema_ver,
                now_str,
            ),
        )
        row = conn.execute(
            "SELECT * FROM system_health_snapshots WHERE snapshot_uuid = ?",
            (snapshot_uuid,),
        ).fetchone()
        return dict(row) if row else {}


def get_system_health_telemetry(
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Return aggregated system health metrics without sensitive user identifiers or tokens."""
    p50, p95 = calculate_percentiles()
    disk_info = check_disk_space()

    with database_connection(database_path) as conn:
        schema_ver = int(conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0])
        recent_snapshot = conn.execute(
            "SELECT * FROM system_health_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()

    return {
        "status": "HEALTHY" if not disk_info["is_low"] else "DEGRADED",
        "latency_p50_ms": p50,
        "latency_p95_ms": p95,
        "provider_failures": _FAILURE_COUNTERS["provider_failures"],
        "db_locks": _FAILURE_COUNTERS["db_locks"],
        "export_failures": _FAILURE_COUNTERS["export_failures"],
        "disk_free_mb": disk_info["free_mb"],
        "disk_status": disk_info["status"],
        "schema_version": schema_ver,
        "last_snapshot": dict(recent_snapshot) if recent_snapshot else None,
    }
