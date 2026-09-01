"""TeacherOS Evidence-Linked Class Progress Service (Day 21).

Provides honest, traceable class progress and health analytics:
- What is active, supported, uncertain, and due next.
- No unsupported mastery percentages, fake dials, or student comparisons.
- Every claim cites its underlying source record.
- Proposed objective extraction from lessons & evidence with teacher approval gate.
- Action-oriented class health card prioritizing the next instructional decision.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from database import database_connection
from feature_flags import feature_enabled

logger = logging.getLogger(__name__)

VALID_OBJECTIVE_STATUSES = frozenset({"current", "needs_support", "secure", "paused", "archived"})
VALID_PROPOSAL_STATUSES = frozenset({"pending", "approved", "rejected"})
VALID_SUPPORT_LEVELS = frozenset({"introduced", "observed_working", "needs_support", "secure_confirmed"})
VALID_SOURCE_TYPES = frozenset({
    "lesson", "lesson_outcome", "evidence_analysis",
    "writing_feedback", "retrieval_review", "manual_judgment", "manual"
})

OBJECTIVE_STATUS_LABELS = {
    "current": "🎯 Active / In Progress",
    "needs_support": "🟡 Needs Support / Scaffolding",
    "secure": "✅ Teacher-Confirmed Secure",
    "paused": "⏸ Paused",
    "archived": "🗃 Archived",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _normalize_obj_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    if d.get("status") in {"paused", "archived"}:
        d["status"] = d["status"]
    elif d.get("is_secure") == 1:
        d["status"] = "secure"
    elif d.get("support_level") == "needs_support":
        d["status"] = "needs_support"
    else:
        d["status"] = "current"
    return d


# ---------------------------------------------------------------------------
# 1. Proposed Objective Extraction & Approval Queue
# ---------------------------------------------------------------------------

def propose_objective(
    *,
    user_id: int,
    class_id: int,
    objective_text: str,
    source_type: str,
    source_id: int | None = None,
    category: str = "general",
    proposed_status: str = "current",
    confidence: str = "medium",
    rationale: str = "Extracted from lesson target",
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Propose an objective extracted from lesson or evidence. Requires teacher approval."""
    objective_text = " ".join(str(objective_text).split())
    if not objective_text:
        raise ValueError("Objective text cannot be empty.")
    if len(objective_text) > 1000:
        objective_text = objective_text[:1000]

    source_type = str(source_type).strip().lower()
    if source_type not in {"lesson", "evidence_analysis", "writing_feedback", "manual"}:
        raise ValueError(f"Invalid source_type: {source_type}")

    proposed_status = str(proposed_status).strip().lower()
    if proposed_status not in {"current", "needs_support", "secure"}:
        proposed_status = "current"

    proposal_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{user_id}:{class_id}:{objective_text.lower()}"))
    now_str = _utc_now()

    with database_connection(database_path) as conn:
        # Validate class ownership
        owner_check = conn.execute(
            "SELECT 1 FROM classes WHERE id = ? AND user_id = ?",
            (class_id, user_id),
        ).fetchone()
        if not owner_check:
            raise ValueError(f"Class {class_id} does not belong to user {user_id}")

        conn.execute(
            """
            INSERT INTO proposed_class_objectives (
                proposal_uuid, user_id, class_id, source_type, source_id,
                objective_text, category, proposed_status, confidence,
                rationale, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            ON CONFLICT (proposal_uuid) DO UPDATE SET
                rationale = excluded.rationale,
                updated_at = excluded.updated_at
            """,
            (
                proposal_uuid, user_id, class_id, source_type, source_id,
                objective_text, category, proposed_status, confidence,
                rationale, now_str, now_str,
            ),
        )
        row = conn.execute(
            "SELECT * FROM proposed_class_objectives WHERE proposal_uuid = ?",
            (proposal_uuid,),
        ).fetchone()
        return _row_dict(row)


def list_pending_proposed_objectives(
    *,
    user_id: int,
    class_id: int,
    limit: int = 20,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List pending objective proposals waiting for teacher review."""
    with database_connection(database_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM proposed_class_objectives
            WHERE user_id = ? AND class_id = ? AND status = 'pending'
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, class_id, limit),
        ).fetchall()
        return [_row_dict(r) for r in rows if r is not None]


def approve_proposed_objective(
    *,
    user_id: int,
    proposal_id: int,
    target_status: str | None = None,
    priority: int = 0,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Teacher approves proposed objective, adopting it into class_objectives."""
    now_str = _utc_now()
    with database_connection(database_path) as conn:
        proposal = conn.execute(
            "SELECT * FROM proposed_class_objectives WHERE id = ? AND user_id = ?",
            (proposal_id, user_id),
        ).fetchone()
        if not proposal:
            return None
        # Callback retries must not create duplicate objectives/evidence links.
        if proposal["status"] == "approved":
            existing = conn.execute(
                "SELECT * FROM class_objectives WHERE class_id = ? AND user_id = ? AND objective = ? ORDER BY id DESC LIMIT 1",
                (proposal["class_id"], user_id, proposal["objective_text"]),
            ).fetchone()
            return _normalize_obj_dict(existing)
        if proposal["status"] != "pending":
            return None

        status = target_status or proposal["proposed_status"]
        if status not in VALID_OBJECTIVE_STATUSES:
            status = "current"

        is_secure = 1 if status == "secure" else 0
        secure_at = now_str if is_secure else None
        support_level = "needs_support" if status == "needs_support" else ("secure_confirmed" if is_secure else "introduced")
        db_status = "paused" if status == "paused" else ("archived" if status == "archived" else "current")

        # Insert or adopt into class_objectives
        cursor = conn.execute(
            """
            INSERT INTO class_objectives (
                class_id, user_id, objective, status, priority,
                category, is_secure, secure_confirmed_at, support_level,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal["class_id"], user_id, proposal["objective_text"],
                db_status, priority, proposal["category"], is_secure, secure_at,
                support_level, now_str, now_str,
            ),
        )
        objective_id = cursor.lastrowid

        # Record traceable evidence link
        link_uuid = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO objective_evidence_links (
                link_uuid, objective_id, user_id, class_id,
                source_type, source_id, support_level,
                evidence_excerpt, teacher_confirmed, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                link_uuid, objective_id, user_id, proposal["class_id"],
                proposal["source_type"], proposal["source_id"],
                "secure_confirmed" if is_secure else support_level,
                proposal["rationale"], now_str,
            ),
        )

        # Mark proposal approved
        conn.execute(
            """
            UPDATE proposed_class_objectives
            SET status = 'approved', reviewed_at = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (now_str, now_str, proposal_id, user_id),
        )

        row = conn.execute(
            "SELECT * FROM class_objectives WHERE id = ?",
            (objective_id,),
        ).fetchone()
        return _normalize_obj_dict(row)


def reject_proposed_objective(
    *,
    user_id: int,
    proposal_id: int,
    database_path: Path | None = None,
) -> bool:
    """Teacher dismisses an AI-extracted proposed objective."""
    now_str = _utc_now()
    with database_connection(database_path) as conn:
        cursor = conn.execute(
            """
            UPDATE proposed_class_objectives
            SET status = 'rejected', reviewed_at = ?, updated_at = ?
            WHERE id = ? AND user_id = ? AND status = 'pending'
            """,
            (now_str, now_str, proposal_id, user_id),
        )
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# 2. Objective Status & Evidence Linkage
# ---------------------------------------------------------------------------

def update_objective_status(
    *,
    user_id: int,
    objective_id: int,
    new_status: str,
    teacher_note: str | None = None,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Explicitly update objective status with teacher confirmation."""
    new_status = str(new_status).strip().lower()
    if new_status not in VALID_OBJECTIVE_STATUSES:
        raise ValueError(f"Invalid status: {new_status}. Must be one of {sorted(VALID_OBJECTIVE_STATUSES)}")

    now_str = _utc_now()
    is_secure = 1 if new_status == "secure" else 0
    secure_at = now_str if is_secure else None
    support_level = "needs_support" if new_status == "needs_support" else ("secure_confirmed" if is_secure else "observed_working")
    db_status = "paused" if new_status == "paused" else ("archived" if new_status == "archived" else "current")

    with database_connection(database_path) as conn:
        obj = conn.execute(
            "SELECT * FROM class_objectives WHERE id = ? AND user_id = ?",
            (objective_id, user_id),
        ).fetchone()
        if not obj:
            return None

        conn.execute(
            """
            UPDATE class_objectives
            SET status = ?, is_secure = ?, secure_confirmed_at = ?, support_level = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (db_status, is_secure, secure_at, support_level, now_str, objective_id, user_id),
        )

        # Log judgment in evidence links
        link_uuid = str(uuid.uuid4())
        excerpt = teacher_note or f"Teacher set status to {OBJECTIVE_STATUS_LABELS.get(new_status, new_status)}"
        conn.execute(
            """
            INSERT INTO objective_evidence_links (
                link_uuid, objective_id, user_id, class_id,
                source_type, source_id, support_level,
                evidence_excerpt, teacher_confirmed, created_at
            ) VALUES (?, ?, ?, ?, 'manual_judgment', NULL, ?, ?, 1, ?)
            """,
            (
                link_uuid, objective_id, user_id, obj["class_id"],
                "secure_confirmed" if is_secure else ("needs_support" if new_status == "needs_support" else "observed_working"),
                excerpt, now_str,
            ),
        )

        updated = conn.execute(
            "SELECT * FROM class_objectives WHERE id = ? AND user_id = ?",
            (objective_id, user_id),
        ).fetchone()
        return _normalize_obj_dict(updated)


def link_objective_evidence(
    *,
    user_id: int,
    objective_id: int,
    class_id: int,
    source_type: str,
    source_id: int | None,
    support_level: str,
    evidence_excerpt: str,
    teacher_confirmed: bool = True,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Create a verifiable link between an objective and a concrete piece of evidence."""
    if support_level not in VALID_SUPPORT_LEVELS:
        support_level = "observed_working"
    if source_type not in VALID_SOURCE_TYPES:
        source_type = "manual_judgment"

    evidence_excerpt = " ".join(str(evidence_excerpt).split())
    if not evidence_excerpt:
        raise ValueError("Evidence excerpt cannot be empty.")
    if len(evidence_excerpt) > 1000:
        evidence_excerpt = evidence_excerpt[:1000]
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in evidence_excerpt):
        raise ValueError("Evidence excerpt contains unsupported control characters.")

    link_uuid = str(uuid.uuid4())
    now_str = _utc_now()

    with database_connection(database_path) as conn:
        # Validate ownership
        obj = conn.execute(
            "SELECT 1 FROM class_objectives WHERE id = ? AND user_id = ? AND class_id = ?",
            (objective_id, user_id, class_id),
        ).fetchone()
        if not obj:
            raise ValueError("Objective does not exist or belong to this user/class.")

        conn.execute(
            """
            INSERT INTO objective_evidence_links (
                link_uuid, objective_id, user_id, class_id,
                source_type, source_id, support_level,
                evidence_excerpt, teacher_confirmed, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link_uuid, objective_id, user_id, class_id,
                source_type, source_id, support_level,
                evidence_excerpt, 1 if teacher_confirmed else 0, now_str,
            ),
        )
        row = conn.execute(
            "SELECT * FROM objective_evidence_links WHERE link_uuid = ?",
            (link_uuid,),
        ).fetchone()
        return _row_dict(row)


def get_objective_detail_with_sources(
    *,
    user_id: int,
    objective_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Return objective facts together with ALL linked evidence records."""
    with database_connection(database_path) as conn:
        obj = conn.execute(
            "SELECT * FROM class_objectives WHERE id = ? AND user_id = ?",
            (objective_id, user_id),
        ).fetchone()
        if not obj:
            return None

        links = conn.execute(
            """
            SELECT * FROM objective_evidence_links
            WHERE objective_id = ? AND user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (objective_id, user_id),
        ).fetchall()

        d = _normalize_obj_dict(obj)
        d["evidence_links"] = [_row_dict(r) for r in links if r is not None]
        return d


def list_class_objectives(
    *,
    user_id: int,
    class_id: int,
    status_filter: str | None = None,
    limit: int = 50,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List objectives for a class filtered by status."""
    with database_connection(database_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM class_objectives
            WHERE user_id = ? AND class_id = ?
            ORDER BY priority DESC, updated_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, class_id, limit * 2),
        ).fetchall()

        normalized = [_normalize_obj_dict(r) for r in rows if r is not None]
        if status_filter and status_filter in VALID_OBJECTIVE_STATUSES:
            normalized = [obj for obj in normalized if obj["status"] == status_filter]
        elif status_filter != "all":
            normalized = [obj for obj in normalized if obj["status"] != "archived"]

        return normalized[:limit]


# ---------------------------------------------------------------------------
# 3. Class Health Card & Progress Overview
# ---------------------------------------------------------------------------

def get_class_health_card(
    *,
    user_id: int,
    class_id: int,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Action-oriented health card prioritizing the next instructional decision."""
    with database_connection(database_path) as conn:
        class_row = conn.execute(
            "SELECT * FROM classes WHERE id = ? AND user_id = ?",
            (class_id, user_id),
        ).fetchone()
        if not class_row:
            return {
                "status": "not_found",
                "headline": "Class Not Found",
                "recommendation": "Select an existing active class.",
                "action_type": "none",
            }

        # 1. Check review backlog
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        due_reviews = conn.execute(
            """
            SELECT COUNT(*) FROM retrieval_review_items
            WHERE user_id = ? AND class_id = ?
              AND ((status IN ('active', 'due') AND next_review_date <= ?)
                   OR (status = 'snoozed' AND snoozed_until <= ?))
            """,
            (user_id, class_id, today_str, today_str),
        ).fetchone()[0]

        # 2. Check unrecorded outcome for taught lesson
        unrecorded_lesson = conn.execute(
            """
            SELECT l.id, l.title FROM class_lessons AS l
            LEFT JOIN lesson_outcomes AS o ON o.class_lesson_id = l.id
            WHERE l.user_id = ? AND l.class_id = ? AND l.lifecycle_state = 'taught'
              AND (o.id IS NULL OR o.status = 'draft')
            ORDER BY l.taught_at DESC, l.id DESC LIMIT 1
            """,
            (user_id, class_id),
        ).fetchone()

        # 3. Check unresolved difficulty / needs support
        needs_support_rows = conn.execute(
            """
            SELECT * FROM class_objectives
            WHERE user_id = ? AND class_id = ?
            ORDER BY updated_at DESC LIMIT 10
            """,
            (user_id, class_id),
        ).fetchall()
        needs_support_objs = [
            _normalize_obj_dict(r) for r in needs_support_rows
            if _normalize_obj_dict(r).get("status") == "needs_support"
        ]

        # 4. Check active objectives
        all_objs = [
            _normalize_obj_dict(r) for r in conn.execute(
                "SELECT * FROM class_objectives WHERE user_id = ? AND class_id = ?",
                (user_id, class_id),
            ).fetchall()
        ]
        active_objs = [o for o in all_objs if o.get("status") == "current"]

        # 5. Check total taught lessons
        total_lessons = conn.execute(
            """
            SELECT COUNT(*) FROM class_lessons
            WHERE user_id = ? AND class_id = ? AND lifecycle_state = 'taught'
            """,
            (user_id, class_id),
        ).fetchone()[0]

        # Determine priority health diagnosis
        if int(due_reviews) >= 3:
            return {
                "status": "review_due",
                "headline": f"🔁 Spaced Retrieval Due ({due_reviews} items)",
                "recommendation": "Start a 5-minute retrieval warm-up before introducing new targets.",
                "action_type": "review_session",
                "due_count": int(due_reviews),
            }
        elif unrecorded_lesson:
            return {
                "status": "outcome_needed",
                "headline": f"📝 Record Lesson Outcome: '{unrecorded_lesson['title'][:35]}'",
                "recommendation": "Tap 3 factual check-in choices to record what was met and where support is needed.",
                "action_type": "record_outcome",
                "lesson_id": int(unrecorded_lesson["id"]),
            }
        elif needs_support_objs:
            obj_sample = needs_support_objs[0]["objective"][:40]
            return {
                "status": "needs_support",
                "headline": f"🟡 Reinforce Target: '{obj_sample}'",
                "recommendation": "Use 3-Tier Differentiation Support Route or a 1-tap emergency scaffold.",
                "action_type": "plan_reteach",
                "needs_support_count": len(needs_support_objs),
            }
        elif len(all_objs) == 0 and int(total_lessons) == 0:
            return {
                "status": "fresh_class",
                "headline": "🌱 Fresh Class Setup",
                "recommendation": "Plan your first lesson to introduce initial can-do syllabus objectives.",
                "action_type": "plan_lesson",
            }
        else:
            return {
                "status": "steady_progress",
                "headline": f"🟢 Steady Progress ({len(active_objs)} active targets)",
                "recommendation": "Continue following syllabus goals or submit student work to Analyze Work.",
                "action_type": "plan_lesson",
                "active_count": len(active_objs),
            }


def get_class_progress_overview(
    *,
    user_id: int,
    class_id: int,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Assemble complete evidence-linked progress summary for a class."""
    with database_connection(database_path) as conn:
        class_row = conn.execute(
            "SELECT * FROM classes WHERE id = ? AND user_id = ?",
            (class_id, user_id),
        ).fetchone()
        if not class_row:
            return {}

        # Objective counts by normalized status
        obj_counts = {
            "current": 0,
            "needs_support": 0,
            "secure": 0,
            "paused": 0,
            "archived": 0,
        }
        for r in conn.execute(
            "SELECT * FROM class_objectives WHERE user_id = ? AND class_id = ?",
            (user_id, class_id),
        ).fetchall():
            norm = _normalize_obj_dict(r)
            if norm and norm["status"] in obj_counts:
                obj_counts[norm["status"]] += 1

        # Recent outcomes & lessons timeline (last 5)
        timeline_rows = conn.execute(
            """
            SELECT l.id as lesson_id, l.title, l.lifecycle_state, l.taught_at,
                   o.result, o.confidence, o.support_needed, o.difficulty_categories_json,
                   o.notes, o.updated_at
            FROM class_lessons AS l
            LEFT JOIN lesson_outcomes AS o ON o.class_lesson_id = l.id
            WHERE l.user_id = ? AND l.class_id = ?
            ORDER BY COALESCE(l.taught_at, l.updated_at) DESC, l.id DESC
            LIMIT 5
            """,
            (user_id, class_id),
        ).fetchall()

        # Evidence count
        ev_batch_count = conn.execute(
            "SELECT COUNT(*) FROM evidence_batches WHERE user_id = ? AND class_id = ?",
            (user_id, class_id),
        ).fetchone()[0]

        # Review queue summary
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        due_review_count = conn.execute(
            """
            SELECT COUNT(*) FROM retrieval_review_items
            WHERE user_id = ? AND class_id = ?
              AND ((status IN ('active', 'due') AND next_review_date <= ?)
                   OR (status = 'snoozed' AND snoozed_until <= ?))
            """,
            (user_id, class_id, today_str, today_str),
        ).fetchone()[0]

        # Pending proposed objectives
        pending_proposals = conn.execute(
            "SELECT COUNT(*) FROM proposed_class_objectives WHERE user_id = ? AND class_id = ? AND status = 'pending'",
            (user_id, class_id),
        ).fetchone()[0]

        health = get_class_health_card(user_id=user_id, class_id=class_id, database_path=database_path)

        return {
            "class_id": class_id,
            "display_name": class_row["display_name"],
            "level": class_row["level"],
            "objectives_count": obj_counts,
            "total_active_targets": obj_counts["current"] + obj_counts["needs_support"],
            "secure_confirmed_count": obj_counts["secure"],
            "needs_support_count": obj_counts["needs_support"],
            "recent_timeline": [_row_dict(r) for r in timeline_rows if r is not None],
            "evidence_batches_count": int(ev_batch_count),
            "due_reviews_count": int(due_review_count),
            "pending_proposals_count": int(pending_proposals),
            "health_card": health,
        }


# ---------------------------------------------------------------------------
# 4. Orphan-Safety Handler
# ---------------------------------------------------------------------------

def handle_deleted_source(
    *,
    source_type: str,
    source_id: int,
    database_path: Path | None = None,
) -> int:
    """Nullify source pointers in proposed objectives and evidence links when source is deleted."""
    with database_connection(database_path) as conn:
        c1 = conn.execute(
            """
            UPDATE proposed_class_objectives
            SET source_id = NULL, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE source_type = ? AND source_id = ?
            """,
            (source_type, source_id),
        )
        c2 = conn.execute(
            """
            UPDATE objective_evidence_links
            SET source_id = NULL
            WHERE source_type = ? AND source_id = ?
            """,
            (source_type, source_id),
        )
        return c1.rowcount + c2.rowcount
