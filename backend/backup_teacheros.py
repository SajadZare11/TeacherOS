from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

from config import DATABASE_PATH, PROJECT_ROOT
from database import initialize_database

BACKUP_DIR = PROJECT_ROOT / "backups"


def create_backup(*, label: str = "manual") -> Path:
    """Create a consistent SQLite backup, including databases using WAL mode."""
    source_path = initialize_database()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    safe_label = "".join(character for character in label.lower() if character.isalnum() or character in {"-", "_"})
    safe_label = safe_label.strip("-_") or "manual"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = BACKUP_DIR / f"teacheros_{timestamp}_{safe_label}.db"

    source = sqlite3.connect(source_path, timeout=15)
    target = sqlite3.connect(destination)
    try:
        source.execute("PRAGMA busy_timeout = 15000")
        source.backup(target)
        target.execute("PRAGMA integrity_check")
    finally:
        target.close()
        source.close()

    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("TeacherOS created an empty database backup.")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a safe TeacherOS SQLite backup.")
    parser.add_argument("--label", default="prelaunch", help="Short label added to the backup filename")
    args = parser.parse_args()

    backup_path = create_backup(label=args.label)
    print("✅ TeacherOS database backup created")
    print(f"Source: {DATABASE_PATH}")
    print(f"Backup: {backup_path}")
    print(f"Size: {backup_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
