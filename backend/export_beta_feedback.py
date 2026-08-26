from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from config import DATABASE_PATH, PROJECT_ROOT
from database import initialize_database


EXPORT_PATH = PROJECT_ROOT / "exports" / "beta_feedback.csv"


def export_beta_feedback(output_path: Path = EXPORT_PATH) -> tuple[Path, int]:
    """Export every beta report to a spreadsheet-friendly UTF-8 CSV file."""
    initialize_database()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT
                f.id AS feedback_id,
                f.created_at,
                f.rating,
                f.area,
                f.status,
                f.message,
                u.telegram_user_id,
                u.username,
                u.first_name,
                u.last_name
            FROM feedback AS f
            JOIN users AS u ON u.id = f.user_id
            ORDER BY f.created_at DESC, f.id DESC
            """
        ).fetchall()
    finally:
        connection.close()

    columns = [
        "feedback_id",
        "created_at",
        "rating",
        "area",
        "status",
        "message",
        "telegram_user_id",
        "username",
        "first_name",
        "last_name",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows({column: row[column] for column in columns} for row in rows)

    return output_path, len(rows)


def main() -> None:
    path, count = export_beta_feedback()
    print(f"✅ Exported {count} beta feedback report(s)")
    print(path)


if __name__ == "__main__":
    main()
