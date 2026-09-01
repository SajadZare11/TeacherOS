"""TeacherOS Day 23 Acceptance Check.

Validates editable, evidence-safe progress reports:
- Schema v23 deployed with reports and audit revisions.
- Three V1 report types: whole-class summary, end-of-unit summary, teacher reflection.
- Insufficient evidence boundary: transparent notices, never invent attendance or proficiency.
- Section editing with versioning and revision history.
- Explicit teacher approval gate before final/share-safe status.
- Word (.docx) and PDF (.pdf) export generation.
- Multi-tenant isolation and 64-byte Telegram bounds.
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
from class_service import create_class
from curriculum_discipline_service import save_curriculum_unit
from feature_flags import FEATURE_ENV_VARS
from progress_report_keyboards import (
    report_dashboard_keyboard,
    report_edit_cancel_keyboard,
    report_edit_section_picker_keyboard,
    report_list_keyboard,
    report_type_picker_keyboard,
    report_view_keyboard,
)
from progress_report_service import (
    approve_progress_report,
    export_progress_report_pdf,
    export_progress_report_word,
    generate_progress_report,
    get_progress_report,
    handle_deleted_source,
    list_progress_reports,
    update_progress_report_section,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "day23"
DEFAULT_REPORT = OUTPUTS_DIR / "acceptance_report.json"


def _teacher(identifier: int, username: str = "teacher") -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        username=f"{username}_{identifier}",
        first_name="Acceptance",
        last_name="Teacher",
        language_code="en",
    )


def evaluate_day23() -> dict[str, Any]:
    previous_flags = {name: os.environ.get(name) for name in FEATURE_ENV_VARS.values()}
    for name in FEATURE_ENV_VARS.values():
        os.environ[name] = "false"
    os.environ[FEATURE_ENV_VARS["classes"]] = "true"
    os.environ[FEATURE_ENV_VARS["continuity"]] = "true"

    try:
        with tempfile.TemporaryDirectory(prefix="teacheros-day23-acceptance-") as temp_dir:
            path = Path(temp_dir) / "teacheros.db"
            original_path = database.DATABASE_PATH
            database.DATABASE_PATH = path

            try:
                database.initialize_database(path)
                teacher_a = _teacher(230_001, "teacher_a")
                teacher_b = _teacher(230_002, "teacher_b")

                with database.database_connection(path) as conn:
                    user_a_id = database.ensure_database_user(conn, teacher_a)
                    user_b_id = database.ensure_database_user(conn, teacher_b)

                class_a = create_class(
                    telegram_user=teacher_a,
                    display_name="C1 Academic Writing & Debate",
                    level="C1",
                    age_group="adults",
                    learner_count_band="6_12",
                    goal="IELTS 7.5+ Academic writing and seminar participation",
                    database_path=path,
                )
                class_a_id = int(class_a["id"])

                class_b = create_class(
                    telegram_user=teacher_b,
                    display_name="B1 Everyday English",
                    level="B1",
                    age_group="adults",
                    learner_count_band="2_5",
                    goal="Conversational fluency",
                    database_path=path,
                )
                class_b_id = int(class_b["id"])

                # 1. Schema v23 check
                with database.database_connection(path) as conn:
                    schema_ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
                    t1 = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='class_progress_reports'").fetchone()
                    t2 = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='progress_report_revisions'").fetchone()
                    schema_valid = (schema_ver >= 23 and t1 is not None and t2 is not None)

                # 2. Insufficient evidence boundary enforcement
                rep_empty = generate_progress_report(
                    user_id=user_a_id,
                    class_id=class_a_id,
                    report_type="whole_class_summary",
                    reporting_period_start="2026-08-01",
                    reporting_period_end="2026-08-31",
                    database_path=path,
                )
                insufficient_valid = (
                    rep_empty is not None
                    and rep_empty["has_insufficient_evidence"] == 1
                    and "Insufficient recorded" in rep_empty["learning_covered_text"]
                    and rep_empty["status"] == "draft"
                )

                # 3. Populate approved evidence & test all 3 report types
                unit1 = save_curriculum_unit(
                    user_id=user_a_id,
                    class_id=class_a_id,
                    unit_number="4",
                    unit_title="Academic Argumentation & Synthesis",
                    status="current",
                    database_path=path,
                )
                with database.database_connection(path) as conn:
                    # Insert lesson & outcome
                    c_lesson = conn.execute(
                        """
                        INSERT INTO class_lessons (class_id, user_id, title, scheduled_for, status)
                        VALUES (?, ?, 'Hedging in Academic Writing', '2026-08-15', 'taught')
                        """,
                        (class_a_id, user_a_id),
                    )
                    lesson_id = c_lesson.lastrowid
                    conn.execute(
                        """
                        INSERT INTO lesson_outcomes (
                            class_lesson_id, class_id, user_id, result,
                            confidence, support_needed, notes, status, created_at
                        ) VALUES (?, ?, ?, 'met', 'high', 'none', 'Students used tentative language well', 'saved', '2026-08-15T10:00:00Z')
                        """,
                        (lesson_id, class_a_id, user_a_id),
                    )
                    # Insert approved analysis
                    b_cur = conn.execute(
                        """
                        INSERT INTO evidence_batches (
                            batch_uuid, class_id, user_id, evidence_type, source_format, item_count, status
                        ) VALUES ('bat_test_1', ?, ?, 'writing', 'pasted_text', 5, 'ready')
                        """,
                        (class_a_id, user_a_id),
                    )
                    batch_id = b_cur.lastrowid
                    conn.execute(
                        """
                        INSERT INTO evidence_analysis_results (
                            analysis_uuid, batch_id, class_id, user_id, response_count,
                            findings_json, uncertainty, uncertainty_reason, approved,
                            approved_summary, status, prompt_contract, prompt_version, created_at
                        ) VALUES ('ana_test_1', ?, ?, ?, 5, '{"findings": []}', 'low', 'Sample', 1, 'Observed strong thesis statement formulation', 'approved', 'contract', 'v1', '2026-08-16T10:00:00Z')
                        """,
                        (batch_id, class_a_id, user_a_id),
                    )

                # Report 1: Whole-Class Summary
                rep1 = generate_progress_report(
                    user_id=user_a_id,
                    class_id=class_a_id,
                    report_type="whole_class_summary",
                    reporting_period_start="2026-08-01",
                    reporting_period_end="2026-08-31",
                    database_path=path,
                )
                # Report 2: End-of-Unit Summary
                rep2 = generate_progress_report(
                    user_id=user_a_id,
                    class_id=class_a_id,
                    report_type="end_of_unit_summary",
                    reporting_period_start="2026-08-01",
                    reporting_period_end="2026-08-31",
                    unit_id=unit1["id"],
                    database_path=path,
                )
                # Report 3: Teacher Reflection
                rep3 = generate_progress_report(
                    user_id=user_a_id,
                    class_id=class_a_id,
                    report_type="teacher_reflection",
                    reporting_period_start="2026-08-01",
                    reporting_period_end="2026-08-31",
                    database_path=path,
                )

                all_three_types = (
                    rep1 is not None and rep1["has_insufficient_evidence"] == 0
                    and rep2 is not None and rep2["report_type"] == "end_of_unit_summary"
                    and rep3 is not None and rep3["report_type"] == "teacher_reflection"
                )

                # 4. Section editing and audit versioning
                edited = update_progress_report_section(
                    user_id=user_a_id,
                    report_id=rep1["id"],
                    field_name="teacher_comments",
                    new_value="Teacher verified: strong improvement in counter-argument structures.",
                    database_path=path,
                )
                with database.database_connection(path) as conn:
                    revs = conn.execute(
                        "SELECT * FROM progress_report_revisions WHERE report_id = ?",
                        (rep1["id"],),
                    ).fetchall()

                editing_valid = (
                    edited is not None
                    and edited["version"] == 2
                    and "counter-argument" in edited["teacher_comments"]
                    and len(revs) == 1
                    and revs[0]["field_changed"] == "teacher_comments"
                )

                # 5. Teacher Approval Gate
                self_report = get_progress_report(user_id=user_a_id, report_id=rep1["id"], database_path=path)
                draft_unshared = (self_report["status"] == "draft" and self_report["share_safe_verified"] == 0)

                approved = approve_progress_report(user_id=user_a_id, report_id=rep1["id"], database_path=path)
                approval_valid = (
                    draft_unshared
                    and approved is not None
                    and approved["status"] == "approved"
                    and approved["share_safe_verified"] == 1
                    and approved["approved_at"] is not None
                )

                # 6. Word & PDF Exports
                doc_name, doc_bytes = export_progress_report_word(user_id=user_a_id, report_id=rep1["id"], database_path=path)
                pdf_name, pdf_bytes = export_progress_report_pdf(user_id=user_a_id, report_id=rep1["id"], database_path=path)

                exports_valid = (
                    doc_name.endswith(".docx") and len(doc_bytes) > 500
                    and pdf_name.endswith(".pdf") and len(pdf_bytes) > 500
                )

                # 7. Deleted source orphan safety
                deleted_count = handle_deleted_source(
                    source_type="lesson_outcome",
                    source_id=1,
                    database_path=path,
                )
                orphan_safe_valid = (deleted_count >= 1)

                # 8. Multi-tenant isolation
                cross_view = get_progress_report(user_id=user_b_id, report_id=rep1["id"], database_path=path)
                cross_list = list_progress_reports(user_id=user_b_id, class_id=class_a_id, database_path=path)

                cross_trigger_blocked = False
                try:
                    with database.database_connection(path) as conn:
                        conn.execute(
                            """
                            INSERT INTO class_progress_reports (
                                report_uuid, user_id, class_id, report_type, title,
                                reporting_period_start, reporting_period_end,
                                learning_covered_text, strengths_text, priorities_text,
                                change_observed_text, next_steps_text
                            ) VALUES ('hacked_rep', ?, ?, 'whole_class_summary', 'Hacked', '2026-08-01', '2026-08-31', 'a', 'b', 'c', 'd', 'e')
                            """,
                            (user_b_id, class_a_id),
                        )
                except Exception:
                    cross_trigger_blocked = True

                multi_tenant_ok = (cross_view is None and len(cross_list) == 0 and cross_trigger_blocked)

                # 9. Telegram Keyboards strictly <= 64 bytes
                kbs = [
                    report_dashboard_keyboard(class_a_id, 1, 3),
                    report_type_picker_keyboard(class_a_id, 1),
                    report_view_keyboard(rep1["id"], class_a_id, 1, status="draft"),
                    report_view_keyboard(rep1["id"], class_a_id, 1, status="approved"),
                    report_edit_section_picker_keyboard(rep1["id"], class_a_id, 1),
                    report_edit_cancel_keyboard(rep1["id"], 1),
                    report_list_keyboard(class_a_id, 1, [rep1, rep2, rep3]),
                ]
                kbs_valid = all(
                    len(btn.callback_data.encode("utf-8")) <= 64
                    for kb in kbs
                    for row in kb.inline_keyboard
                    for btn in row
                )

                checks = {
                    "schema_v23_deployed": schema_valid,
                    "all_three_report_types_supported": all_three_types,
                    "insufficient_evidence_boundary_enforced": insufficient_valid,
                    "section_editing_and_audit_versioning": editing_valid,
                    "mandatory_teacher_approval_gate": approval_valid,
                    "word_export_generated_and_validated": exports_valid,
                    "pdf_export_generated_and_validated": exports_valid,
                    "deleted_source_orphan_safety_verified": orphan_safe_valid,
                    "multi_tenant_isolation_verified": multi_tenant_ok,
                    "telegram_keyboards_bounded_64_bytes": kbs_valid,
                }
                passed = all(checks.values())

                return {
                    "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "gate": "Day 23 — Generate Editable, Evidence-Safe Progress Reports",
                    "schema_version": 23,
                    "checks": checks,
                    "passed": passed,
                    "engineering_status": "PASS" if passed else "FAIL",
                    "details": {
                        "class_a_id": class_a_id,
                        "report_count": len(list_progress_reports(user_id=user_a_id, class_id=class_a_id, database_path=path)),
                        "doc_size_bytes": len(doc_bytes),
                        "pdf_size_bytes": len(pdf_bytes),
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
    parser = argparse.ArgumentParser(description="Evaluate TeacherOS Day 23 Progress Reports.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = evaluate_day23()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"DAY 23 ACCEPTANCE: {report['engineering_status']}")
    print(f"Report: {output_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
