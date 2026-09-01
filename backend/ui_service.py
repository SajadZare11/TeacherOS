"""TeacherOS UI Service (Day 24).

Manages user UI preferences, language localization, active class memory,
onboarding walkthrough state, and class-aware material pinning / search.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from database import database_connection

logger = logging.getLogger(__name__)

VALID_LANGUAGES = frozenset({"en", "fa"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---------------------------------------------------------------------------
# 1. UI Preferences & Language
# ---------------------------------------------------------------------------

def get_or_create_ui_preferences(
    user_id: int,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Retrieve or initialize UI preferences for a teacher."""
    now_str = _utc_now()
    with database_connection(database_path) as conn:
        row = conn.execute(
            "SELECT * FROM user_ui_preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if row is None:
            conn.execute(
                """
                INSERT OR IGNORE INTO user_ui_preferences (
                    user_id, language_code, compact_mode, onboarding_completed, created_at, updated_at
                ) VALUES (?, 'en', 0, 0, ?, ?)
                """,
                (user_id, now_str, now_str),
            )
            row = conn.execute(
                "SELECT * FROM user_ui_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        return dict(row) if row else {}


def set_user_language(
    user_id: int,
    language_code: str,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Set teacher's display language preference ('en' or 'fa')."""
    if language_code not in VALID_LANGUAGES:
        raise ValueError(f"Unsupported language code: {language_code}")

    now_str = _utc_now()
    with database_connection(database_path) as conn:
        conn.execute(
            """
            INSERT INTO user_ui_preferences (user_id, language_code, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                language_code = excluded.language_code,
                updated_at = excluded.updated_at
            """,
            (user_id, language_code, now_str),
        )
        row = conn.execute(
            "SELECT * FROM user_ui_preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else {}


def set_active_class(
    user_id: int,
    class_id: int,
    database_path: Path | None = None,
) -> bool:
    """Store the last actively opened class for rapid return."""
    now_str = _utc_now()
    with database_connection(database_path) as conn:
        owned = conn.execute(
            "SELECT 1 FROM classes WHERE id = ? AND user_id = ? AND status = 'active'",
            (class_id, user_id),
        ).fetchone()
        if owned is None:
            return False
        conn.execute(
            """
            INSERT INTO user_ui_preferences (user_id, last_active_class_id, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                last_active_class_id = excluded.last_active_class_id,
                updated_at = excluded.updated_at
            """,
            (user_id, class_id, now_str),
        )
        return True


def complete_onboarding(
    user_id: int,
    database_path: Path | None = None,
) -> None:
    """Mark first-run onboarding walkthrough as completed."""
    now_str = _utc_now()
    with database_connection(database_path) as conn:
        conn.execute(
            """
            INSERT INTO user_ui_preferences (user_id, onboarding_completed, updated_at)
            VALUES (?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                onboarding_completed = 1,
                updated_at = excluded.updated_at
            """,
            (user_id, now_str),
        )


# ---------------------------------------------------------------------------
# 2. Pinned / Favorite Materials per Class
# ---------------------------------------------------------------------------

def pin_material_to_class(
    *,
    user_id: int,
    class_id: int,
    material_id: int,
    database_path: Path | None = None,
) -> bool:
    """Pin a material to class favorites for 1-tap reuse."""
    now_str = _utc_now()
    with database_connection(database_path) as conn:
        # Verify ownership
        cls_row = conn.execute(
            "SELECT id FROM classes WHERE id = ? AND user_id = ?", (class_id, user_id)
        ).fetchone()
        mat_row = conn.execute(
            "SELECT id FROM materials WHERE id = ? AND user_id = ? AND (class_id IS NULL OR class_id = ?)",
            (material_id, user_id, class_id),
        ).fetchone()
        if not cls_row or not mat_row:
            return False

        conn.execute(
            """
            INSERT OR IGNORE INTO user_pinned_materials (
                user_id, class_id, material_id, pinned_at
            ) VALUES (?, ?, ?, ?)
            """,
            (user_id, class_id, material_id, now_str),
        )
        return True


def unpin_material_from_class(
    *,
    user_id: int,
    class_id: int,
    material_id: int,
    database_path: Path | None = None,
) -> bool:
    """Remove a material from class favorites."""
    with database_connection(database_path) as conn:
        cursor = conn.execute(
            """
            DELETE FROM user_pinned_materials
            WHERE user_id = ? AND class_id = ? AND material_id = ?
            """,
            (user_id, class_id, material_id),
        )
        return cursor.rowcount > 0


def is_material_pinned(
    *,
    user_id: int,
    class_id: int,
    material_id: int,
    database_path: Path | None = None,
) -> bool:
    """Check if a material is pinned in this class."""
    with database_connection(database_path) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM user_pinned_materials
            WHERE user_id = ? AND class_id = ? AND material_id = ?
            """,
            (user_id, class_id, material_id),
        ).fetchone()
        return row is not None


def list_pinned_materials(
    *,
    user_id: int,
    class_id: int,
    limit: int = 10,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List pinned materials for an active class."""
    with database_connection(database_path) as conn:
        rows = conn.execute(
            """
            SELECT m.*, p.pinned_at
            FROM user_pinned_materials AS p
            JOIN materials AS m ON m.id = p.material_id
            WHERE p.user_id = ? AND p.class_id = ?
            ORDER BY p.pinned_at DESC
            LIMIT ?
            """,
            (user_id, class_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 3. Class-Aware Material Search & Recent Items
# ---------------------------------------------------------------------------

def search_class_materials(
    *,
    user_id: int,
    class_id: int,
    query_text: str,
    limit: int = 10,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Search materials within an active class matching title, topic, or content."""
    clean_q = f"%{query_text.strip().lower()}%"
    with database_connection(database_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM materials
            WHERE user_id = ? AND class_id = ?
            AND (
                lower(title) LIKE ? OR
                lower(coalesce(topic, '')) LIKE ? OR
                lower(coalesce(content, '')) LIKE ?
            )
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, class_id, clean_q, clean_q, clean_q, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_recent_class_materials(
    *,
    user_id: int,
    class_id: int,
    limit: int = 5,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Get the most recent materials created for an active class."""
    with database_connection(database_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM materials
            WHERE user_id = ? AND class_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, class_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
