"""TeacherOS CEFR Curriculum Discipline Service (Day 22).

Provides curriculum management, CEFR communicative mapping, and golden set calibration:
- Lightweight coursebook/unit tracking without scraping copyrighted materials.
- CEFR communicative categories (reception, production, interaction, mediation).
- Teacher corrections override AI mappings and are durably preserved.
- Calibrated golden set evaluation with expert English teacher metrics.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from database import database_connection

logger = logging.getLogger(__name__)

VALID_CEFR_LEVELS = frozenset({"A1", "A2", "B1", "B2", "C1", "C2"})
VALID_COMMUNICATIVE_MODES = frozenset({
    "reception_reading", "reception_listening",
    "production_speaking", "production_writing",
    "interaction_spoken", "interaction_written",
    "mediation",
})
VALID_COMPETENCE_CATEGORIES = frozenset({
    "linguistic_grammar", "linguistic_vocabulary", "linguistic_phonology",
    "sociolinguistic", "pragmatic_functional",
})
VALID_COVERAGE_STATUSES = frozenset({"not_covered", "partly_covered", "covered", "secure"})
VALID_UNIT_STATUSES = frozenset({"planned", "current", "completed", "skipped"})

COMMUNICATIVE_MODE_LABELS = {
    "reception_reading": "📖 Reading Reception",
    "reception_listening": "🎧 Listening Reception",
    "production_speaking": "🗣 Spoken Production",
    "production_writing": "✍ Written Production",
    "interaction_spoken": "💬 Spoken Interaction",
    "interaction_written": "📨 Written Interaction",
    "mediation": "🔄 Language Mediation",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# 1. Coursebook & Curriculum Unit Management
# ---------------------------------------------------------------------------

def save_curriculum_unit(
    *,
    user_id: int,
    class_id: int,
    unit_title: str,
    unit_number: str = "1",
    coursebook_name: str | None = None,
    exam_syllabus_target: str | None = None,
    curriculum_notes: str | None = None,
    status: str = "current",
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Save or update a lightweight curriculum unit for a class."""
    unit_title = " ".join(str(unit_title).split())
    if not unit_title:
        raise ValueError("Unit title cannot be empty.")
    if len(unit_title) > 200:
        unit_title = unit_title[:200]

    unit_number = str(unit_number).strip() or "1"
    if status not in VALID_UNIT_STATUSES:
        status = "current"

    now_str = _utc_now()
    with database_connection(database_path) as conn:
        # Validate class ownership
        owner = conn.execute(
            "SELECT 1 FROM classes WHERE id = ? AND user_id = ?",
            (class_id, user_id),
        ).fetchone()
        if not owner:
            raise ValueError(f"Class {class_id} does not belong to user {user_id}")

        if status == "current":
            # Demote any prior current unit
            conn.execute(
                """
                UPDATE class_curriculum_units
                SET status = 'completed', updated_at = ?
                WHERE class_id = ? AND user_id = ? AND status = 'current'
                """,
                (now_str, class_id, user_id),
            )

        cursor = conn.execute(
            """
            INSERT INTO class_curriculum_units (
                user_id, class_id, unit_number, unit_title,
                coursebook_name, exam_syllabus_target, curriculum_notes,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, class_id, unit_number, unit_title,
                coursebook_name, exam_syllabus_target, curriculum_notes,
                status, now_str, now_str,
            ),
        )
        unit_id = cursor.lastrowid

        # Sync profile coursebook metadata on classes table
        if coursebook_name:
            conn.execute(
                """
                UPDATE classes
                SET coursebook = ?, coursebook_unit = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (coursebook_name, f"Unit {unit_number}: {unit_title}", now_str, class_id, user_id),
            )

        row = conn.execute(
            "SELECT * FROM class_curriculum_units WHERE id = ?",
            (unit_id,),
        ).fetchone()
        return _row_dict(row)


def get_current_curriculum_unit(
    *,
    user_id: int,
    class_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Retrieve active unit for a class."""
    with database_connection(database_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM class_curriculum_units
            WHERE user_id = ? AND class_id = ? AND status = 'current'
            ORDER BY updated_at DESC, id DESC LIMIT 1
            """,
            (user_id, class_id),
        ).fetchone()
        return _row_dict(row)


def list_curriculum_units(
    *,
    user_id: int,
    class_id: int,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List all curriculum units for a class."""
    with database_connection(database_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM class_curriculum_units
            WHERE user_id = ? AND class_id = ?
            ORDER BY id ASC
            """,
            (user_id, class_id),
        ).fetchall()
        return [_row_dict(r) for r in rows if r is not None]


# ---------------------------------------------------------------------------
# 2. CEFR Objective Mapping & Coverage Analysis
# ---------------------------------------------------------------------------

def map_objective_to_cefr(
    *,
    user_id: int,
    objective_id: int,
    class_id: int,
    cefr_level: str,
    communicative_mode: str,
    competence_category: str,
    can_do_statement: str,
    coverage_status: str = "not_covered",
    uncertainty_note: str | None = None,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Create CEFR communicative mapping for a class objective."""
    cefr_level = str(cefr_level).strip().upper()
    if cefr_level not in VALID_CEFR_LEVELS:
        cefr_level = "B1"

    if communicative_mode not in VALID_COMMUNICATIVE_MODES:
        communicative_mode = "interaction_spoken"
    if competence_category not in VALID_COMPETENCE_CATEGORIES:
        competence_category = "pragmatic_functional"
    if coverage_status not in VALID_COVERAGE_STATUSES:
        coverage_status = "not_covered"

    now_str = _utc_now()
    with database_connection(database_path) as conn:
        # Validate ownership
        obj = conn.execute(
            "SELECT 1 FROM class_objectives WHERE id = ? AND user_id = ? AND class_id = ?",
            (objective_id, user_id, class_id),
        ).fetchone()
        if not obj:
            raise ValueError("Objective does not exist or owner mismatch.")

        cursor = conn.execute(
            """
            INSERT INTO cefr_objective_mappings (
                objective_id, user_id, class_id, cefr_level,
                communicative_mode, competence_category, can_do_statement,
                coverage_status, teacher_overridden, uncertainty_note,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                objective_id, user_id, class_id, cefr_level,
                communicative_mode, competence_category, can_do_statement,
                coverage_status, uncertainty_note, now_str, now_str,
            ),
        )
        mapping_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM cefr_objective_mappings WHERE id = ?", (mapping_id,)).fetchone()
        return _row_dict(row)


def override_cefr_mapping(
    *,
    user_id: int,
    mapping_id: int,
    communicative_mode: str | None = None,
    competence_category: str | None = None,
    can_do_statement: str | None = None,
    coverage_status: str | None = None,
    teacher_note: str | None = None,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Teacher corrects or overrides AI-generated CEFR mapping."""
    now_str = _utc_now()
    with database_connection(database_path) as conn:
        mapping = conn.execute(
            "SELECT * FROM cefr_objective_mappings WHERE id = ? AND user_id = ?",
            (mapping_id, user_id),
        ).fetchone()
        if not mapping:
            return None

        mode = communicative_mode or mapping["communicative_mode"]
        comp = competence_category or mapping["competence_category"]
        can_do = can_do_statement or mapping["can_do_statement"]
        cov = coverage_status or mapping["coverage_status"]
        note = teacher_note or mapping["uncertainty_note"]

        conn.execute(
            """
            UPDATE cefr_objective_mappings
            SET communicative_mode = ?, competence_category = ?,
                can_do_statement = ?, coverage_status = ?,
                teacher_overridden = 1, uncertainty_note = ?,
                updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (mode, comp, can_do, cov, note, now_str, mapping_id, user_id),
        )

        row = conn.execute("SELECT * FROM cefr_objective_mappings WHERE id = ?", (mapping_id,)).fetchone()
        return _row_dict(row)


def get_class_curriculum_coverage(
    *,
    user_id: int,
    class_id: int,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Provide structured breakdown of covered, partly covered, and not yet covered CEFR objectives."""
    with database_connection(database_path) as conn:
        class_row = conn.execute(
            "SELECT * FROM classes WHERE id = ? AND user_id = ?",
            (class_id, user_id),
        ).fetchone()
        if not class_row:
            return {}

        unit = conn.execute(
            """
            SELECT * FROM class_curriculum_units
            WHERE class_id = ? AND user_id = ? AND status = 'current'
            ORDER BY updated_at DESC LIMIT 1
            """,
            (class_id, user_id),
        ).fetchone()

        mappings = conn.execute(
            """
            SELECT m.*, o.objective, o.status as obj_status, o.is_secure
            FROM cefr_objective_mappings AS m
            JOIN class_objectives AS o ON o.id = m.objective_id
            WHERE m.class_id = ? AND m.user_id = ?
            ORDER BY m.updated_at DESC
            """,
            (class_id, user_id),
        ).fetchall()

        mode_breakdown: dict[str, int] = {k: 0 for k in VALID_COMMUNICATIVE_MODES}
        covered: list[dict[str, Any]] = []
        partly: list[dict[str, Any]] = []
        not_yet: list[dict[str, Any]] = []

        for r in mappings:
            d = _row_dict(r)
            mode = d["communicative_mode"]
            if mode in mode_breakdown:
                mode_breakdown[mode] += 1

            cov = d["coverage_status"]
            if d.get("is_secure") or cov in {"covered", "secure"}:
                covered.append(d)
            elif cov == "partly_covered":
                partly.append(d)
            else:
                not_yet.append(d)

        return {
            "class_id": class_id,
            "display_name": class_row["display_name"],
            "level": class_row["level"],
            "current_unit": _row_dict(unit),
            "total_mapped_objectives": len(mappings),
            "covered_count": len(covered),
            "partly_covered_count": len(partly),
            "not_yet_covered_count": len(not_yet),
            "communicative_mode_distribution": mode_breakdown,
            "covered_targets": covered,
            "partly_covered_targets": partly,
            "not_yet_covered_targets": not_yet,
        }


# ---------------------------------------------------------------------------
# 3. Golden Set Calibration & Expert Evaluation
# ---------------------------------------------------------------------------

def record_golden_set_calibration(
    *,
    material_id: int | None,
    evaluator_name: str,
    can_do_clarity_pass: bool,
    task_authenticity_pass: bool,
    assessment_alignment_pass: bool,
    scaffolding_pass: bool,
    disagreement_notes: str | None = None,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Store professional ELT evaluator ratings across the golden test set."""
    overall_pass = bool(
        can_do_clarity_pass
        and task_authenticity_pass
        and assessment_alignment_pass
        and scaffolding_pass
    )
    now_str = _utc_now()

    with database_connection(database_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO golden_curriculum_evaluations (
                material_id, evaluator_name, can_do_clarity_pass,
                task_authenticity_pass, assessment_alignment_pass,
                scaffolding_pass, overall_pass, disagreement_notes,
                evaluated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                material_id, evaluator_name,
                1 if can_do_clarity_pass else 0,
                1 if task_authenticity_pass else 0,
                1 if assessment_alignment_pass else 0,
                1 if scaffolding_pass else 0,
                1 if overall_pass else 0,
                disagreement_notes, now_str,
            ),
        )
        eval_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM golden_curriculum_evaluations WHERE id = ?", (eval_id,)).fetchone()
        return _row_dict(row)


def get_golden_set_calibration_metrics(
    *,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Calculate pass rates and teacher alignment on the golden lesson set."""
    with database_connection(database_path) as conn:
        rows = conn.execute("SELECT * FROM golden_curriculum_evaluations").fetchall()
        if not rows:
            return {
                "total_evaluations": 0,
                "overall_pass_rate_percent": 0.0,
                "evaluator_count": 0,
                "meets_85_percent_gate": False,
            }

        total = len(rows)
        passed_count = sum(1 for r in rows if r["overall_pass"] == 1)
        evaluators = {r["evaluator_name"] for r in rows}
        pass_rate = round((passed_count / total) * 100.0, 1)

        return {
            "total_evaluations": total,
            "overall_pass_rate_percent": pass_rate,
            "evaluator_count": len(evaluators),
            "evaluators": sorted(list(evaluators)),
            "meets_85_percent_gate": bool(pass_rate >= 85.0 and len(evaluators) >= 2),
        }
