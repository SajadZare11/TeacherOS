"""TeacherOS Retrieval & Spaced-Review Service (Day 20).

Provides a transparent, deterministic spaced-retrieval queue for previously
taught language items (vocabulary, grammar, pronunciation, functional language,
common errors, exam strategies) without black-box mastery scores.

Status remains a planning aid under direct teacher control.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from database import database_connection
from feature_flags import feature_enabled

logger = logging.getLogger(__name__)

DEFAULT_INTERVALS = [2, 7, 21, 45]
MAX_DUE_ITEMS_PER_LESSON = 5

VALID_CATEGORIES = frozenset({
    "vocabulary",
    "grammar",
    "pronunciation",
    "functional_language",
    "common_error",
    "exam_strategy",
})

CATEGORY_LABELS: dict[str, str] = {
    "vocabulary": "Vocabulary",
    "grammar": "Grammar",
    "pronunciation": "Pronunciation",
    "functional_language": "Functional Language",
    "common_error": "Common Error",
    "exam_strategy": "Exam Strategy",
}

CATEGORY_ICONS: dict[str, str] = {
    "vocabulary": "🔤",
    "grammar": "🧩",
    "pronunciation": "🗣",
    "functional_language": "💬",
    "common_error": "⚠️",
    "exam_strategy": "🎯",
}

VALID_SOURCE_TYPES = frozenset({"lesson", "evidence_analysis", "writing_feedback", "manual"})
VALID_RESULTS = frozenset({"remembered", "partly_remembered", "forgotten"})
VALID_CONFIDENCE = frozenset({"low", "medium", "high"})
VALID_STATUSES = frozenset({"active", "due", "snoozed", "paused", "mastered", "archived"})


def _utc_now() -> str:
    """Return ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _today_utc() -> str:
    """Return current UTC date in YYYY-MM-DD format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _parse_date(date_str: str | None) -> date | None:
    """Safely parse a YYYY-MM-DD date string."""
    if not date_str:
        return None
    try:
        clean = str(date_str).strip()[:10]
        return date.fromisoformat(clean)
    except (ValueError, TypeError):
        return None


def _format_date(d: date) -> str:
    """Format date to YYYY-MM-DD."""
    return d.strftime("%Y-%m-%d")


def _compute_next_review_date(
    intervals: Sequence[int],
    stage: int,
    from_date: date | None = None,
) -> str:
    """Compute next review date deterministically from interval stage.
    
    If stage exceeds interval list length, use the final interval.
    """
    base = from_date or datetime.now(timezone.utc).date()
    if not intervals:
        intervals = DEFAULT_INTERVALS
    idx = max(0, min(stage, len(intervals) - 1))
    days = intervals[idx]
    return _format_date(base + timedelta(days=days))


def _resolve_intervals(intervals_json: str | None) -> list[int]:
    """Parse intervals from JSON with fallback to defaults."""
    if not intervals_json:
        return list(DEFAULT_INTERVALS)
    try:
        parsed = json.loads(str(intervals_json))
        if isinstance(parsed, list) and len(parsed) >= 2 and all(isinstance(x, int) and x > 0 for x in parsed):
            return [int(x) for x in parsed]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return list(DEFAULT_INTERVALS)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert an sqlite3.Row to a clean dictionary with parsed intervals."""
    if row is None:
        return None
    d = dict(row)
    d["intervals"] = _resolve_intervals(d.get("interval_days_json"))
    return d


# ---------------------------------------------------------------------------
# Core Item Creation & Ingestion
# ---------------------------------------------------------------------------

def add_review_item(
    *,
    user_id: int,
    class_id: int,
    category: str,
    prompt_text: str,
    target_answer: str,
    source_type: str,
    source_id: int | None = None,
    notes: str | None = None,
    intervals: Sequence[int] | None = None,
    confidence: str = "medium",
    custom_next_date: str | None = None,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Add a new item to the spaced-review queue with owner validation.
    
    Deduplicates based on (user_id, class_id, category, prompt_text).
    Returns the created item or existing item if duplicate.
    """
    category = str(category).strip().lower()
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category: {category}. Must be one of {sorted(VALID_CATEGORIES)}")
    
    prompt_text = str(prompt_text).strip()
    if not prompt_text:
        raise ValueError("Prompt text cannot be empty.")
    
    target_answer = str(target_answer).strip()
    if not target_answer:
        raise ValueError("Target answer cannot be empty.")
    
    source_type = str(source_type).strip().lower()
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(f"Invalid source_type: {source_type}. Must be one of {sorted(VALID_SOURCE_TYPES)}")
    
    confidence = str(confidence).strip().lower()
    if confidence not in VALID_CONFIDENCE:
        confidence = "medium"
        
    resolved_intervals = list(intervals) if intervals else list(DEFAULT_INTERVALS)
    intervals_json = json.dumps(resolved_intervals)
    
    # Generate deterministic deduplication UUID
    dedup_key = f"{user_id}:{class_id}:{category}:{prompt_text.lower()}"
    item_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, dedup_key))
    
    today_d = datetime.now(timezone.utc).date()
    if custom_next_date and _parse_date(custom_next_date):
        next_date = str(custom_next_date).strip()[:10]
    else:
        next_date = _compute_next_review_date(resolved_intervals, 0, today_d)
        
    now_str = _utc_now()

    with database_connection(database_path) as conn:
        # Check class ownership first
        owner_check = conn.execute(
            "SELECT 1 FROM classes WHERE id = ? AND user_id = ?",
            (class_id, user_id),
        ).fetchone()
        if not owner_check:
            raise ValueError(f"Class {class_id} does not belong to user {user_id}")
            
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO retrieval_review_items (
                item_uuid, user_id, class_id, category, prompt_text,
                target_answer, notes, source_type, source_id,
                interval_stage, interval_days_json, confidence,
                status, introduced_at, next_review_date,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                item_uuid, user_id, class_id, category, prompt_text,
                target_answer, notes, source_type, source_id,
                intervals_json, confidence, now_str, next_date,
                now_str, now_str,
            ),
        )
        
        row = conn.execute(
            "SELECT * FROM retrieval_review_items WHERE item_uuid = ?",
            (item_uuid,),
        ).fetchone()
        return _row_to_dict(row)


def add_batch_review_items(
    *,
    user_id: int,
    class_id: int,
    items: Sequence[dict[str, Any]],
    source_type: str,
    source_id: int | None = None,
    intervals: Sequence[int] | None = None,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Batch insert review items from a lesson or evidence analysis."""
    created: list[dict[str, Any]] = []
    for item in items:
        try:
            res = add_review_item(
                user_id=user_id,
                class_id=class_id,
                category=item.get("category", "vocabulary"),
                prompt_text=item.get("prompt_text") or item.get("prompt", ""),
                target_answer=item.get("target_answer") or item.get("answer", ""),
                source_type=source_type,
                source_id=source_id,
                notes=item.get("notes"),
                intervals=intervals,
                confidence=item.get("confidence", "medium"),
                database_path=database_path,
            )
            if res:
                created.append(res)
        except Exception as exc:
            logger.warning("Could not add review item %s: %s", item, exc)
    return created


# ---------------------------------------------------------------------------
# Retrieval / Spaced Review Queries & Due Load
# ---------------------------------------------------------------------------

def get_due_items(
    *,
    user_id: int,
    class_id: int,
    today_date: str | None = None,
    limit: int = MAX_DUE_ITEMS_PER_LESSON,
    category: str | None = None,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Retrieve due review items capped to avoid hijacking lesson time.
    
    Items are due if status in ('active', 'due') and next_review_date <= today.
    Snoozed items whose snoozed_until <= today are automatically activated.
    """
    ref_date = str(today_date).strip()[:10] if today_date else _today_utc()
    cap = max(1, min(limit, 50))
    
    with database_connection(database_path) as conn:
        # First, unsnooze any expired snoozes for this class
        conn.execute(
            """
            UPDATE retrieval_review_items
            SET status = 'active', snoozed_until = NULL, updated_at = ?
            WHERE user_id = ? AND class_id = ? AND status = 'snoozed'
              AND snoozed_until IS NOT NULL AND snoozed_until <= ?
            """,
            (_utc_now(), user_id, class_id, ref_date),
        )
        
        query = """
            SELECT * FROM retrieval_review_items
            WHERE user_id = ? AND class_id = ?
              AND status IN ('active', 'due')
              AND next_review_date <= ?
        """
        params: list[Any] = [user_id, class_id, ref_date]
        
        if category and str(category).strip().lower() in VALID_CATEGORIES:
            query += " AND category = ?"
            params.append(str(category).strip().lower())
            
        query += " ORDER BY next_review_date ASC, interval_stage ASC, id ASC LIMIT ?"
        params.append(cap)
        
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows if r is not None]


def count_due_items(
    *,
    user_id: int,
    class_id: int,
    today_date: str | None = None,
    database_path: Path | None = None,
) -> int:
    """Count total due items for a class."""
    ref_date = str(today_date).strip()[:10] if today_date else _today_utc()
    with database_connection(database_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM retrieval_review_items
            WHERE user_id = ? AND class_id = ?
              AND (
                  (status IN ('active', 'due') AND next_review_date <= ?)
                  OR (status = 'snoozed' AND snoozed_until <= ?)
              )
            """,
            (user_id, class_id, ref_date, ref_date),
        ).fetchone()
        return int(row[0]) if row else 0


def get_review_queue(
    *,
    user_id: int,
    class_id: int,
    status_filter: str | None = None,
    category_filter: str | None = None,
    limit: int = 20,
    offset: int = 0,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Get full paginated review queue for a class."""
    with database_connection(database_path) as conn:
        query = "SELECT * FROM retrieval_review_items WHERE user_id = ? AND class_id = ?"
        params: list[Any] = [user_id, class_id]
        
        if status_filter and str(status_filter).strip().lower() in VALID_STATUSES:
            query += " AND status = ?"
            params.append(str(status_filter).strip().lower())
        elif status_filter != "all":
            # Default: omit archived unless explicitly requested
            query += " AND status != 'archived'"
            
        if category_filter and str(category_filter).strip().lower() in VALID_CATEGORIES:
            query += " AND category = ?"
            params.append(str(category_filter).strip().lower())
            
        query += " ORDER BY next_review_date ASC, id ASC LIMIT ? OFFSET ?"
        params.extend([max(1, limit), max(0, offset)])
        
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows if r is not None]


def count_queue_items(
    *,
    user_id: int,
    class_id: int,
    status_filter: str | None = None,
    category_filter: str | None = None,
    database_path: Path | None = None,
) -> int:
    """Count total items matching the filter."""
    with database_connection(database_path) as conn:
        query = "SELECT COUNT(*) FROM retrieval_review_items WHERE user_id = ? AND class_id = ?"
        params: list[Any] = [user_id, class_id]
        
        if status_filter and str(status_filter).strip().lower() in VALID_STATUSES:
            query += " AND status = ?"
            params.append(str(status_filter).strip().lower())
        elif status_filter != "all":
            query += " AND status != 'archived'"
            
        if category_filter and str(category_filter).strip().lower() in VALID_CATEGORIES:
            query += " AND category = ?"
            params.append(str(category_filter).strip().lower())
            
        row = conn.execute(query, params).fetchone()
        return int(row[0]) if row else 0


def get_review_item(
    *,
    user_id: int,
    item_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Retrieve a single item with ownership guard."""
    with database_connection(database_path) as conn:
        row = conn.execute(
            "SELECT * FROM retrieval_review_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        ).fetchone()
        return _row_to_dict(row)


# ---------------------------------------------------------------------------
# State Transitions & Review Logging
# ---------------------------------------------------------------------------

def record_review(
    *,
    user_id: int,
    item_id: int,
    result: str,
    review_date: str | None = None,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Record a review result and deterministically advance or reset interval.
    
    Result transitions:
    - 'remembered': stage advances (stage + 1), next interval applied.
    - 'partly_remembered': stage stays same, current interval re-applied.
    - 'forgotten': stage steps back (max(0, stage - 1)), interval re-applied.
    
    Idempotent: if already reviewed today, does not double-advance.
    """
    result = str(result).strip().lower()
    if result not in VALID_RESULTS:
        raise ValueError(f"Invalid review result: {result}. Must be one of {sorted(VALID_RESULTS)}")
        
    today_str = str(review_date).strip()[:10] if review_date else _today_utc()
    today_d = _parse_date(today_str) or datetime.now(timezone.utc).date()
    now_str = _utc_now()

    with database_connection(database_path) as conn:
        item = conn.execute(
            "SELECT * FROM retrieval_review_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        ).fetchone()
        if not item:
            return None
            
        stage_before = int(item["interval_stage"])
        intervals = _resolve_intervals(item["interval_days_json"])
        
        # Calculate new stage based on outcome
        if result == "remembered":
            stage_after = min(stage_before + 1, len(intervals) - 1)
        elif result == "partly_remembered":
            stage_after = stage_before
        else:  # forgotten
            stage_after = max(0, stage_before - 1)
            
        next_date = _compute_next_review_date(intervals, stage_after, today_d)
        
        # Update item
        conn.execute(
            """
            UPDATE retrieval_review_items
            SET interval_stage = ?,
                last_reviewed_at = ?,
                next_review_date = ?,
                review_count = review_count + 1,
                status = 'active',
                snoozed_until = NULL,
                updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (stage_after, now_str, next_date, now_str, item_id, user_id),
        )
        
        # Record immutable review log
        conn.execute(
            """
            INSERT INTO retrieval_review_logs (
                item_id, user_id, class_id, review_date,
                result, stage_before, stage_after, next_date_after,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id, user_id, item["class_id"], today_str,
                result, stage_before, stage_after, next_date,
                now_str,
            ),
        )
        
        updated = conn.execute(
            "SELECT * FROM retrieval_review_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        ).fetchone()
        return _row_to_dict(updated)


def snooze_item(
    *,
    user_id: int,
    item_id: int,
    days: int = 3,
    custom_date: str | None = None,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Postpone an item by a specified number of days or until an explicit date."""
    now_str = _utc_now()
    today_d = datetime.now(timezone.utc).date()
    
    if custom_date and _parse_date(custom_date):
        parsed_custom = _parse_date(custom_date)
        target_date_str = _format_date(parsed_custom) if parsed_custom else _format_date(today_d + timedelta(days=max(1, days)))
    else:
        target_date_str = _format_date(today_d + timedelta(days=max(1, days)))

    with database_connection(database_path) as conn:
        conn.execute(
            """
            UPDATE retrieval_review_items
            SET status = 'snoozed',
                snoozed_until = ?,
                next_review_date = ?,
                updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (target_date_str, target_date_str, now_str, item_id, user_id),
        )
        row = conn.execute(
            "SELECT * FROM retrieval_review_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        ).fetchone()
        return _row_to_dict(row)


def pause_item(
    *,
    user_id: int,
    item_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Pause an item so it does not appear in due queues."""
    now_str = _utc_now()
    with database_connection(database_path) as conn:
        conn.execute(
            """
            UPDATE retrieval_review_items
            SET status = 'paused', updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (now_str, item_id, user_id),
        )
        row = conn.execute(
            "SELECT * FROM retrieval_review_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        ).fetchone()
        return _row_to_dict(row)


def resume_item(
    *,
    user_id: int,
    item_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Resume a paused or snoozed item, recomputing due date from today."""
    now_str = _utc_now()
    today_d = datetime.now(timezone.utc).date()
    
    with database_connection(database_path) as conn:
        item = conn.execute(
            "SELECT * FROM retrieval_review_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        ).fetchone()
        if not item:
            return None
            
        intervals = _resolve_intervals(item["interval_days_json"])
        stage = int(item["interval_stage"])
        next_date = _compute_next_review_date(intervals, stage, today_d)
        
        conn.execute(
            """
            UPDATE retrieval_review_items
            SET status = 'active',
                snoozed_until = NULL,
                next_review_date = ?,
                updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (next_date, now_str, item_id, user_id),
        )
        row = conn.execute(
            "SELECT * FROM retrieval_review_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        ).fetchone()
        return _row_to_dict(row)


def archive_item(
    *,
    user_id: int,
    item_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Archive an item out of active circulation."""
    now_str = _utc_now()
    with database_connection(database_path) as conn:
        conn.execute(
            """
            UPDATE retrieval_review_items
            SET status = 'archived', updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (now_str, item_id, user_id),
        )
        row = conn.execute(
            "SELECT * FROM retrieval_review_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        ).fetchone()
        return _row_to_dict(row)


def update_confidence(
    *,
    user_id: int,
    item_id: int,
    confidence: str,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Update teacher-judged confidence (low, medium, high)."""
    confidence = str(confidence).strip().lower()
    if confidence not in VALID_CONFIDENCE:
        raise ValueError(f"Invalid confidence: {confidence}. Must be one of {sorted(VALID_CONFIDENCE)}")
        
    now_str = _utc_now()
    with database_connection(database_path) as conn:
        conn.execute(
            """
            UPDATE retrieval_review_items
            SET confidence = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (confidence, now_str, item_id, user_id),
        )
        row = conn.execute(
            "SELECT * FROM retrieval_review_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        ).fetchone()
        return _row_to_dict(row)


def override_review_schedule(
    *,
    user_id: int,
    item_id: int,
    next_review_date: str,
    stage: int | None = None,
    notes: str | None = None,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Teacher manual override of the review schedule."""
    clean_date = str(next_review_date).strip()[:10]
    if not _parse_date(clean_date):
        raise ValueError(f"Invalid date format: {next_review_date}. Expected YYYY-MM-DD.")
        
    now_str = _utc_now()
    with database_connection(database_path) as conn:
        query = "UPDATE retrieval_review_items SET next_review_date = ?, updated_at = ?"
        params: list[Any] = [clean_date, now_str]
        
        if stage is not None and stage >= 0:
            query += ", interval_stage = ?"
            params.append(stage)
            
        if notes is not None:
            query += ", notes = ?"
            params.append(notes)
            
        query += " WHERE id = ? AND user_id = ?"
        params.extend([item_id, user_id])
        
        conn.execute(query, params)
        row = conn.execute(
            "SELECT * FROM retrieval_review_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        ).fetchone()
        return _row_to_dict(row)


def update_class_intervals(
    *,
    user_id: int,
    class_id: int,
    intervals: Sequence[int],
    database_path: Path | None = None,
) -> int:
    """Update review intervals for all active items in a class."""
    if not intervals or len(intervals) < 2 or any(not isinstance(x, int) or x <= 0 for x in intervals):
        raise ValueError("Intervals must be a list of at least 2 positive integers.")
        
    intervals_json = json.dumps([int(x) for x in intervals])
    now_str = _utc_now()
    
    with database_connection(database_path) as conn:
        cursor = conn.execute(
            """
            UPDATE retrieval_review_items
            SET interval_days_json = ?, updated_at = ?
            WHERE user_id = ? AND class_id = ? AND status != 'archived'
            """,
            (intervals_json, now_str, user_id, class_id),
        )
        return cursor.rowcount


def get_class_intervals(
    *,
    user_id: int,
    class_id: int,
    database_path: Path | None = None,
) -> list[int]:
    """Get the current interval schedule for a class."""
    with database_connection(database_path) as conn:
        row = conn.execute(
            """
            SELECT interval_days_json FROM retrieval_review_items
            WHERE user_id = ? AND class_id = ? AND status != 'archived'
            ORDER BY updated_at DESC LIMIT 1
            """,
            (user_id, class_id),
        ).fetchone()
        if row and row["interval_days_json"]:
            return _resolve_intervals(row["interval_days_json"])
    return list(DEFAULT_INTERVALS)


def handle_deleted_source(
    *,
    source_type: str,
    source_id: int,
    database_path: Path | None = None,
) -> int:
    """Orphan-safe handler: set source_id to NULL when source lesson/evidence is deleted.
    
    Items remain active in the queue under teacher control.
    """
    now_str = _utc_now()
    with database_connection(database_path) as conn:
        cursor = conn.execute(
            """
            UPDATE retrieval_review_items
            SET source_id = NULL, updated_at = ?
            WHERE source_type = ? AND source_id = ?
            """,
            (now_str, source_type, source_id),
        )
        return cursor.rowcount


# ---------------------------------------------------------------------------
# Retrieval Block Proposal for Lesson Planning
# ---------------------------------------------------------------------------

def propose_retrieval_block(
    *,
    user_id: int,
    class_id: int,
    max_items: int = MAX_DUE_ITEMS_PER_LESSON,
    today_date: str | None = None,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Generate a structured retrieval warm-up block for lesson planning.
    
    Returns capped due items with recommended warm-up activity ideas.
    """
    due = get_due_items(
        user_id=user_id,
        class_id=class_id,
        today_date=today_date,
        limit=max_items,
        database_path=database_path,
    )
    
    if not due:
        return {
            "has_due_items": False,
            "due_count": 0,
            "items": [],
            "retrieval_block_text": "",
            "estimated_minutes": 0,
        }
        
    lines = [
        "### 🔁 Retrieval & Spaced-Review Warm-Up (5–8 mins)",
        "Prompt students to recall and activate previously taught language before introducing new concepts:\n",
    ]
    
    for idx, it in enumerate(due, 1):
        cat_icon = CATEGORY_ICONS.get(it["category"], "•")
        cat_label = CATEGORY_LABELS.get(it["category"], it["category"].title())
        lines.append(f"{idx}. {cat_icon} **[{cat_label}]** {it['prompt_text']}")
        lines.append(f"   - *Target:* {it['target_answer']}")
        if it.get("notes"):
            lines.append(f"   - *Note:* {it['notes']}")
            
    lines.append("\n*Procedure:* Pair students for a 3-minute rapid retrieval round, then elicit answers on the board.")
    
    return {
        "has_due_items": True,
        "due_count": len(due),
        "items": due,
        "retrieval_block_text": "\n".join(lines),
        "estimated_minutes": min(8, max(4, len(due) * 2)),
    }


def get_review_queue_stats(
    *,
    user_id: int,
    class_id: int,
    database_path: Path | None = None,
) -> dict[str, int]:
    """Get queue breakdown counts by status and category."""
    with database_connection(database_path) as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) as cnt
            FROM retrieval_review_items
            WHERE user_id = ? AND class_id = ?
            GROUP BY status
            """,
            (user_id, class_id),
        ).fetchall()
        
        status_counts = {r["status"]: int(r["cnt"]) for r in rows}
        
        cat_rows = conn.execute(
            """
            SELECT category, COUNT(*) as cnt
            FROM retrieval_review_items
            WHERE user_id = ? AND class_id = ? AND status != 'archived'
            GROUP BY category
            """,
            (user_id, class_id),
        ).fetchall()
        category_counts = {r["category"]: int(r["cnt"]) for r in cat_rows}
        
        due_count = count_due_items(user_id=user_id, class_id=class_id, database_path=database_path)
        
        return {
            "total": sum(status_counts.values()),
            "active": status_counts.get("active", 0),
            "due": due_count,
            "snoozed": status_counts.get("snoozed", 0),
            "paused": status_counts.get("paused", 0),
            "mastered": status_counts.get("mastered", 0),
            "archived": status_counts.get("archived", 0),
            "by_category": category_counts,
        }
