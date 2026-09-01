"""TeacherOS Database Backup, Rotation, and Restore Engine (Day 26).

Provides consistent SQLite backups with WAL mode support, automatic rotation
to prevent disk exhaustion, and validated restore drills with integrity checks.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DATABASE_PATH, PROJECT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = PROJECT_ROOT / "backups" / "automated"
CRITICAL_CORE_TABLES = (
    "schema_versions",
    "users",
    "classes",
    "materials",
    "payments",
    "subscriptions",
)


def create_database_backup(
    *,
    source_path: Path | None = None,
    backup_dir: Path | None = None,
    label: str = "auto",
    keep_count: int = 7,
) -> Path:
    """Create a consistent online SQLite backup and rotate older backups."""
    src = Path(source_path or DATABASE_PATH).expanduser().resolve()
    target_dir = Path(backup_dir or DEFAULT_BACKUP_DIR).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    if not src.is_file():
        raise FileNotFoundError(f"Source database not found at: {src}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    clean_label = "".join(c for c in label.lower() if c.isalnum() or c in {"-", "_"}).strip("-_") or "auto"
    destination = target_dir / f"teacheros_backup_{timestamp}_{clean_label}.db"

    source_conn = sqlite3.connect(src, timeout=15)
    target_conn = sqlite3.connect(destination)
    try:
        source_conn.execute("PRAGMA busy_timeout = 15000")
        source_conn.backup(target_conn)
        integrity = target_conn.execute("PRAGMA integrity_check").fetchone()
        if not integrity or str(integrity[0]).lower() != "ok":
            raise RuntimeError(f"Backup failed integrity verification: {integrity}")
    finally:
        target_conn.close()
        source_conn.close()

    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("Created database backup is empty or unwritten.")

    # Rotate older backups keeping the newest keep_count
    rotate_backups(backup_dir=target_dir, keep_count=keep_count)

    logger.info("Successfully created database backup: %s (%d bytes)", destination.name, destination.stat().st_size)
    return destination


def rotate_backups(
    *,
    backup_dir: Path | None = None,
    keep_count: int = 7,
) -> int:
    """Remove older backup files exceeding the retention count."""
    target_dir = Path(backup_dir or DEFAULT_BACKUP_DIR).expanduser().resolve()
    if not target_dir.is_dir():
        return 0

    backups = sorted(
        [f for f in target_dir.glob("teacheros_backup_*.db") if f.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    removed = 0
    if len(backups) > keep_count:
        to_delete = backups[keep_count:]
        for backup_file in to_delete:
            try:
                backup_file.unlink()
                removed += 1
                logger.info("Rotated old backup file: %s", backup_file.name)
            except Exception as exc:
                logger.warning("Could not delete old backup %s: %s", backup_file.name, exc)

    return removed


def restore_database_backup(
    backup_path: Path,
    target_path: Path,
) -> dict[str, Any]:
    """Restore a backup file to target location and verify structural integrity."""
    backup = Path(backup_path).expanduser().resolve()
    target = Path(target_path).expanduser().resolve()

    if not backup.is_file() or backup.stat().st_size == 0:
        raise FileNotFoundError(f"Valid backup file not found at: {backup}")

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, target)

    conn = sqlite3.connect(target)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk_issues = conn.execute("PRAGMA foreign_key_check").fetchall()
        schema_ver = int(conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0])
        counts = {}
        for tbl in CRITICAL_CORE_TABLES:
            try:
                counts[tbl] = int(conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0])
            except sqlite3.OperationalError:
                counts[tbl] = 0

        is_healthy = (integrity == "ok" and len(fk_issues) == 0 and schema_ver >= 1)
        return {
            "restored": is_healthy,
            "integrity": integrity,
            "foreign_key_issues": len(fk_issues),
            "schema_version": schema_ver,
            "table_counts": counts,
            "target_path": str(target),
        }
    finally:
        conn.close()


def check_disk_space(
    path: Path | None = None,
    min_free_mb: int = 100,
) -> dict[str, Any]:
    """Check disk storage capacity and determine if free space is below safety threshold."""
    check_path = Path(path or PROJECT_ROOT).expanduser().resolve()
    usage = shutil.disk_usage(check_path)
    free_mb = usage.free / (1024 * 1024)
    total_mb = usage.total / (1024 * 1024)
    used_mb = usage.used / (1024 * 1024)

    is_low = free_mb < min_free_mb
    return {
        "path": str(check_path),
        "free_mb": round(free_mb, 2),
        "total_mb": round(total_mb, 2),
        "used_mb": round(used_mb, 2),
        "min_free_mb": min_free_mb,
        "is_low": is_low,
        "status": "WARNING" if is_low else "OK",
    }
