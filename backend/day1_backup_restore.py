from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DATABASE_PATH, PROJECT_ROOT
from database import initialize_database

BACKUP_ROOT = PROJECT_ROOT / "backups" / "day1"
CRITICAL_TABLES = (
    "schema_versions",
    "users",
    "materials",
    "usage_events",
    "payments",
    "subscriptions",
    "feedback",
)


def _run_git(*arguments: str, cwd: Path = PROJECT_ROOT) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _database_snapshot(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(path)
    try:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        version_row = connection.execute(
            "SELECT MAX(version) FROM schema_versions"
        ).fetchone()
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in CRITICAL_TABLES
        }
        return {
            "integrity": integrity,
            "schema_version": int(version_row[0] or 0),
            "counts": counts,
        }
    finally:
        connection.close()


def _create_code_backup(destination: Path) -> dict[str, Any]:
    archive_path = destination / "teacheros-code.zip"
    _run_git("archive", "--format=zip", f"--output={archive_path}", "HEAD")

    restore_dir = destination / "restore-check" / "code"
    restore_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(restore_dir)

    required = (
        "backend/main.py",
        "backend/database.py",
        "backend/check_project.py",
        "requirements.txt",
    )
    missing = [relative for relative in required if not (restore_dir / relative).is_file()]
    if missing:
        raise RuntimeError("Code restore is missing critical files: " + ", ".join(missing))

    return {
        "path": str(archive_path),
        "sha256": _sha256(archive_path),
        "bytes": archive_path.stat().st_size,
        "commit": _run_git("rev-parse", "HEAD"),
        "restored_to": str(restore_dir),
        "required_files_verified": list(required),
    }


def _create_database_backup(destination: Path) -> dict[str, Any]:
    source_path = initialize_database()
    backup_path = destination / "teacheros-database.db"

    source = sqlite3.connect(source_path, timeout=15)
    target = sqlite3.connect(backup_path)
    try:
        source.execute("PRAGMA busy_timeout = 15000")
        source.backup(target)
    finally:
        target.close()
        source.close()

    restore_path = destination / "restore-check" / "database" / "teacheros.db"
    restore_path.parent.mkdir(parents=True, exist_ok=True)
    restored_source = sqlite3.connect(backup_path)
    restored_target = sqlite3.connect(restore_path)
    try:
        restored_source.backup(restored_target)
    finally:
        restored_target.close()
        restored_source.close()

    source_snapshot = _database_snapshot(source_path)
    restored_snapshot = _database_snapshot(restore_path)
    if source_snapshot != restored_snapshot:
        raise RuntimeError("Restored database snapshot does not match the live database snapshot.")
    if restored_snapshot["integrity"] != "ok":
        raise RuntimeError("Restored database failed PRAGMA integrity_check.")

    return {
        "source": str(DATABASE_PATH),
        "path": str(backup_path),
        "sha256": _sha256(backup_path),
        "bytes": backup_path.stat().st_size,
        "restored_to": str(restore_path),
        "snapshot": restored_snapshot,
    }


def create_and_verify_backups(*, label: str = "day1") -> Path:
    status = _run_git("status", "--porcelain")
    if status:
        raise RuntimeError(
            "Refusing to create the Day 1 code checkpoint from a dirty worktree. "
            "Commit or stash intended changes first."
        )

    safe_label = "".join(
        character for character in label.lower() if character.isalnum() or character in {"-", "_"}
    ).strip("-_") or "day1"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = BACKUP_ROOT / f"{timestamp}_{safe_label}"
    destination.mkdir(parents=True, exist_ok=False)

    try:
        report = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "branch": _run_git("branch", "--show-current"),
            "code": _create_code_backup(destination),
            "database": _create_database_backup(destination),
            "result": "pass",
        }
        report_path = destination / "restore-report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report_path
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create and restore-test secret-safe TeacherOS Day 1 backups."
    )
    parser.add_argument("--label", default="day1", help="Short backup label")
    args = parser.parse_args()
    report_path = create_and_verify_backups(label=args.label)
    print("TeacherOS Day 1 backup and restore verification passed")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
