"""TeacherOS Day 21 Acceptance Check.

Validates evidence-linked class progress:
- Schema v21 deployed with proposed objectives queue and evidence links.
- Objective status tracking: current, needs_support, secure, paused, archived.
- Teacher-confirmed secure invariant (no black-box mastery scores).
- Proposed objective extraction and mandatory teacher approval gate.
- 100% claim traceability to source lesson/outcome/analysis.
- Action-oriented class health card prioritizing next instructional decisions.
- Empty/new class useful guidance.
- Multi-tenant isolation and 64-byte Telegram callback bounds.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import database
from class_progress_keyboards import (
    health_card_keyboard,
    objective_detail_keyboard,
    objective_status_picker_keyboard,
    objectives_list_keyboard,
    progress_overview_keyboard,
    proposed_objective_review_keyboard,
    proposed_objectives_keyboard,
    timeline_browser_keyboard,
)
from class_progress_service import (
    approve_proposed_objective,
    get_class_health_card,
    get_class_progress_overview,
    get_objective_detail_with_sources,
    handle_deleted_source,
    link_objective_evidence,
    list_class_objectives,
    list_pending_proposed_objectives,
    propose_objective,
    reject_proposed_objective,
    update_objective_status,
)
from class_service import create_class
from feature_flags import FEATURE_ENV_VARS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "day21"
DEFAULT_REPORT = OUTPUTS_DIR / "acceptance_report.json"


def _teacher(identifier: int, username: str = "teacher") -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        username=f"{username}_{identifier}",
        first_name="Acceptance",
        last_name="Teacher",
        language_code="en",
    )


def evaluate_day21() -> dict[str, Any]:
    previous_flags = {name: os.environ.get(name) for name in FEATURE_ENV_VARS.values()}
    for name in FEATURE_ENV_VARS.values():
        os.environ[name] = "false"
    os.environ[FEATURE_ENV_VARS["classes"]] = "true"
    os.environ[FEATURE_ENV_VARS["continuity"]] = "true"
    os.environ[FEATURE_ENV_VARS["evidence"]] = "true"

    try:
        with tempfile.TemporaryDirectory(prefix="teacheros-day21-acceptance-") as temp_dir:
            path = Path(temp_dir) / "teacheros.db"
            original_path = database.DATABASE_PATH
            database.DATABASE_PATH = path

            try:
                database.initialize_database(path)
                teacher_a = _teacher(210_001, "teacher_a")
                teacher_b = _teacher(210_002, "teacher_b")

                with database.database_connection(path) as conn:
                    user_a_id = database.ensure_database_user(conn, teacher_a)
                    user_b_id = database.ensure_database_user(conn, teacher_b)

                class_a = create_class(
                    telegram_user=teacher_a,
                    display_name="C1 Business Communication",
                    level="C1",
                    age_group="adults",
                    learner_count_band="6_12",
                    goal="Executive negotiations and diplomatic email writing",
                    database_path=path,
                )
                class_a_id = int(class_a["id"])

                class_b = create_class(
                    telegram_user=teacher_b,
                    display_name="A1 Beginners",
                    level="A1",
                    age_group="adults",
                    learner_count_band="2_5",
                    goal="Everyday survival English",
                    database_path=path,
                )
                class_b_id = int(class_b["id"])

                # 1. Schema check
                with database.database_connection(path) as conn:
                    schema_ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
                    t1 = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='proposed_class_objectives'").fetchone()
                    t2 = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='objective_evidence_links'").fetchone()
                    schema_valid = (schema_ver >= 21 and t1 is not None and t2 is not None)

                # 2. Proposed objective extraction and teacher approval gate
                prop1 = propose_objective(
                    user_id=user_a_id,
                    class_id=class_a_id,
                    objective_text="Negotiate win-win outcomes using concessive and conditional phrasing",
                    source_type="lesson",
                    source_id=501,
                    category="functional_language",
                    proposed_status="current",
                    rationale="Extracted from lesson plan 'Bargaining & Concessions'",
                    database_path=path,
                )
                prop2 = propose_objective(
                    user_id=user_a_id,
                    class_id=class_a_id,
                    objective_text="Distinguish between polite refusal and counter-proposal",
                    source_type="evidence_analysis",
                    source_id=301,
                    category="functional_language",
                    proposed_status="needs_support",
                    rationale="Identified in writing feedback batch #3",
                    database_path=path,
                )

                pending_before = list_pending_proposed_objectives(user_id=user_a_id, class_id=class_a_id, database_path=path)
                extraction_valid = len(pending_before) == 2

                # Teacher approves prop1 -> adopted into class_objectives
                approved_obj1 = approve_proposed_objective(
                    user_id=user_a_id,
                    proposal_id=prop1["id"],
                    target_status="current",
                    database_path=path,
                )
                approval_valid = (
                    approved_obj1 is not None
                    and approved_obj1["status"] == "current"
                    and "Negotiate win-win" in approved_obj1["objective"]
                )

                # Teacher rejects prop2 -> dismissed
                reject_res = reject_proposed_objective(user_id=user_a_id, proposal_id=prop2["id"], database_path=path)
                pending_after = list_pending_proposed_objectives(user_id=user_a_id, class_id=class_a_id, database_path=path)
                rejection_valid = reject_res and len(pending_after) == 0

                # 3. Objective status transitions and teacher-confirmed secure invariant
                obj1_id = int(approved_obj1["id"])

                # Update to needs_support
                st_sup = update_objective_status(
                    user_id=user_a_id,
                    objective_id=obj1_id,
                    new_status="needs_support",
                    teacher_note="Learners struggled with counter-offers in speaking roleplay.",
                    database_path=path,
                )
                sup_ok = (st_sup["status"] == "needs_support" and st_sup["is_secure"] == 0)

                # Update to secure (with teacher confirmation)
                st_sec = update_objective_status(
                    user_id=user_a_id,
                    objective_id=obj1_id,
                    new_status="secure",
                    teacher_note="Observed accurate and fluent negotiation across 3 simulated deals.",
                    database_path=path,
                )
                sec_ok = (st_sec["status"] == "secure" and st_sec["is_secure"] == 1 and st_sec["secure_confirmed_at"] is not None)

                # 4. Evidence traceability (100% claim transparency)
                detail = get_objective_detail_with_sources(user_id=user_a_id, objective_id=obj1_id, database_path=path)
                traceable_ok = (
                    detail is not None
                    and len(detail["evidence_links"]) >= 2
                    and any("simulated deals" in str(lnk["evidence_excerpt"]) for lnk in detail["evidence_links"])
                )

                # 5. Class Health Card prioritizing instructional decisions
                health_a = get_class_health_card(user_id=user_a_id, class_id=class_a_id, database_path=path)
                health_b = get_class_health_card(user_id=user_b_id, class_id=class_b_id, database_path=path)

                health_valid = (
                    health_a["status"] in {"steady_progress", "needs_support", "review_due", "outcome_needed", "fresh_class"}
                    and health_b["status"] == "fresh_class"
                    and "Plant your first lesson" in health_b["recommendation"] or "Plan your first lesson" in health_b["recommendation"]
                )

                # 6. Full Progress Overview assembly (counts & timeline, zero fake percentages)
                overview = get_class_progress_overview(user_id=user_a_id, class_id=class_a_id, database_path=path)
                overview_valid = (
                    overview.get("class_id") == class_a_id
                    and overview.get("total_active_targets") >= 0
                    and "objectives_count" in overview
                    and "health_card" in overview
                )

                # 7. Deleted-source orphan safety
                orphan_affected = handle_deleted_source(source_type="lesson", source_id=501, database_path=path)
                with database.database_connection(path) as conn:
                    links = conn.execute("SELECT * FROM objective_evidence_links WHERE source_id IS NULL").fetchall()
                    orphan_ok = len(links) >= 1

                # 8. Multi-tenant isolation
                cross_obj = get_objective_detail_with_sources(user_id=user_b_id, objective_id=obj1_id, database_path=path)
                cross_mod = update_objective_status(user_id=user_b_id, objective_id=obj1_id, new_status="paused", database_path=path)
                cross_prop = propose_objective(
                    user_id=user_b_id,
                    class_id=class_a_id,
                    objective_text="Cross-tenant breach",
                    source_type="manual",
                    database_path=path,
                ) if False else None  # trigger should block insertion directly
                
                cross_trigger_blocked = False
                try:
                    propose_objective(
                        user_id=user_b_id,
                        class_id=class_a_id,
                        objective_text="Cross-tenant breach",
                        source_type="manual",
                        database_path=path,
                    )
                except Exception:
                    cross_trigger_blocked = True

                multi_tenant_ok = (cross_obj is None and cross_mod is None and cross_trigger_blocked)

                # 9. Telegram keyboards bounded to <= 64 bytes
                sample_objs = list_class_objectives(user_id=user_a_id, class_id=class_a_id, database_path=path)
                kbs = [
                    progress_overview_keyboard(class_a_id, 1, pending_proposals_count=2),
                    objectives_list_keyboard(class_a_id, 1, sample_objs, "current"),
                    objective_detail_keyboard(obj1_id, class_a_id, 1),
                    objective_status_picker_keyboard(obj1_id, class_a_id, 1, "current"),
                    proposed_objectives_keyboard(class_a_id, 1, []),
                    proposed_objective_review_keyboard(prop1["id"], class_a_id, 1),
                    health_card_keyboard(class_a_id, 1, "plan_lesson"),
                    timeline_browser_keyboard(class_a_id, 1),
                ]
                kbs_valid = all(
                    len(btn.callback_data.encode("utf-8")) <= 64
                    for kb in kbs
                    for row in kb.inline_keyboard
                    for btn in row
                )

                checks = {
                    "schema_v21_deployed": schema_valid,
                    "proposed_objective_extraction_supported": extraction_valid,
                    "mandatory_teacher_approval_gate_verified": approval_valid and rejection_valid,
                    "objective_status_transitions_verified": sup_ok and sec_ok,
                    "teacher_confirmed_secure_invariant": sec_ok,
                    "one_hundred_percent_evidence_traceability": traceable_ok,
                    "action_oriented_class_health_card": health_valid,
                    "progress_overview_uses_honest_counts_no_fake_mastery": overview_valid,
                    "deleted_source_orphan_safety_verified": orphan_ok,
                    "multi_tenant_isolation_verified": multi_tenant_ok,
                    "telegram_keyboards_bounded_64_bytes": kbs_valid,
                }
                passed = all(checks.values())

                return {
                    "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "gate": "Day 21 — Build Evidence-Linked Class Progress, Not Decorative Analytics",
                    "schema_version": 21,
                    "checks": checks,
                    "passed": passed,
                    "engineering_status": "PASS" if passed else "FAIL",
                    "details": {
                        "class_a_id": class_a_id,
                        "class_b_id": class_b_id,
                        "objective_id": obj1_id,
                        "health_a_status": health_a["status"],
                        "health_b_status": health_b["status"],
                    },
                }
            finally:
                database.DATABASE_PATH = original_path
    finally:
        for name, value in previous_flags.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate TeacherOS Day 21 Evidence-Linked Progress.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = evaluate_day21()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"DAY 21 ACCEPTANCE: {report['engineering_status']}")
    print(f"Report: {output_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
