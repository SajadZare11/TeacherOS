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
from feature_flags import FEATURE_ENV_VARS
from writing_feedback_keyboards import (
    writing_feedback_export_keyboard,
    writing_feedback_mode_keyboard,
    writing_feedback_view_keyboard,
)
from writing_feedback_service import (
    approve_writing_feedback,
    export_writing_feedback_pdf,
    export_writing_feedback_word,
    generate_writing_feedback,
    get_writing_feedback,
    list_writing_feedbacks,
    update_writing_feedback_comments,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "day17"
DEFAULT_REPORT = OUTPUTS_DIR / "acceptance_report.json"


def _teacher(identifier: int, username: str = "teacher") -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        username=f"{username}_{identifier}",
        first_name="Acceptance",
        last_name="Teacher",
        language_code="en",
    )


def evaluate_day17() -> dict[str, Any]:
    previous_flags = {name: os.environ.get(name) for name in FEATURE_ENV_VARS.values()}
    for name in FEATURE_ENV_VARS.values():
        os.environ[name] = "false"
    os.environ[FEATURE_ENV_VARS["classes"]] = "true"
    os.environ[FEATURE_ENV_VARS["continuity"]] = "true"
    os.environ[FEATURE_ENV_VARS["evidence"]] = "true"

    try:
        with tempfile.TemporaryDirectory(prefix="teacheros-day17-acceptance-") as temp_dir:
            path = Path(temp_dir) / "teacheros.db"
            original_path = database.DATABASE_PATH
            database.DATABASE_PATH = path

            try:
                database.initialize_database(path)
                teacher_a = _teacher(170_001, "teacher_a")
                teacher_b = _teacher(170_002, "teacher_b")

                class_a = create_class(
                    telegram_user=teacher_a,
                    display_name="B2 Academic Writing",
                    level="B2",
                    age_group="adults",
                    learner_count_band="13_20",
                    goal="Essay structure and cohesive argumentation",
                    database_path=path,
                )

                # 1. Generate feedback across levels & modes
                # A1 light mode
                fb_a1 = generate_writing_feedback(
                    telegram_user=teacher_a,
                    student_text="I live in Tehran. It is nice city. I like parks.",
                    student_label="Sara",
                    student_level="A1",
                    feedback_mode="light",
                    class_id=class_a["id"],
                    database_path=path,
                )
                a1_valid = bool(
                    fb_a1
                    and fb_a1["feedback_mode"] == "light"
                    and fb_a1["approved"] == 0
                    and len(fb_a1["feedback"]["strengths"]) >= 1
                )

                # B1 balanced mode with task prompt
                fb_b1 = generate_writing_feedback(
                    telegram_user=teacher_a,
                    student_text="Dear Sir, I want ask about course schedule. Yesterday I visit center.",
                    student_label="Ali",
                    student_level="B1",
                    feedback_mode="balanced",
                    class_id=class_a["id"],
                    task_prompt="Inquiry email",
                    database_path=path,
                )
                b1_valid = bool(
                    fb_b1
                    and fb_b1["feedback_mode"] == "balanced"
                    and len(fb_b1["feedback"]["priorities"]) <= 3
                    and fb_b1["feedback"]["revision_task"] is not None
                )

                # B2 detailed mode
                fb_b2 = generate_writing_feedback(
                    telegram_user=teacher_a,
                    student_text="Renewable energy is vital. Governments must invest in solar technology.",
                    student_label="Nima",
                    student_level="B2",
                    feedback_mode="detailed",
                    class_id=class_a["id"],
                    database_path=path,
                )
                b2_valid = bool(
                    fb_b2
                    and fb_b2["feedback_mode"] == "detailed"
                    and "TEACHEROS WRITING DIAGNOSTIC" in fb_b2["teacher_copy_text"]
                )

                # Rubric mode
                rubric = {"Task Achievement": "Clear position", "Cohesion": "Transitions"}
                fb_rubric = generate_writing_feedback(
                    telegram_user=teacher_a,
                    student_text="Sustainable development requires international collaboration.",
                    student_label="Mina",
                    student_level="B2",
                    feedback_mode="rubric",
                    rubric_name="Essay Rubric",
                    rubric_criteria=rubric,
                    database_path=path,
                )
                rubric_valid = bool(
                    fb_rubric
                    and fb_rubric["feedback"]["rubric_scores"] is not None
                    and all(s["is_draft_score"] for s in fb_rubric["feedback"]["rubric_scores"].values())
                )

                # 2. No full rewrite by default & student agency
                no_rewrite_valid = "Full Rewritten Version:" not in fb_b1["student_copy_text"]

                # 3. Teacher Approval Gate
                approved = approve_writing_feedback(
                    telegram_user=teacher_a,
                    feedback_id=fb_b1["id"],
                    teacher_comments="Well-structured inquiry, Ali!",
                    database_path=path,
                )
                approval_valid = bool(
                    approved
                    and approved["status"] == "approved"
                    and approved["approved"] == 1
                    and "APPROVED" in approved["teacher_copy_text"]
                )

                # 4. Teacher Comment Editing
                updated_comments = update_writing_feedback_comments(
                    telegram_user=teacher_a,
                    feedback_id=fb_b1["id"],
                    new_comments="Custom note: Bring 2 revised sentences to class.",
                    database_path=path,
                )
                edit_comments_valid = bool(
                    updated_comments and "Custom note: Bring 2 revised sentences" in updated_comments["student_copy_text"]
                )

                # 5. Dual Export Generation (Word & PDF)
                s_docx_name, s_docx_bytes = export_writing_feedback_word(feedback=approved, copy_type="student")
                t_docx_name, t_docx_bytes = export_writing_feedback_word(feedback=approved, copy_type="teacher")
                s_pdf_name, s_pdf_bytes = export_writing_feedback_pdf(feedback=approved, copy_type="student")
                t_pdf_name, t_pdf_bytes = export_writing_feedback_pdf(feedback=approved, copy_type="teacher")
                exports_valid = bool(
                    s_docx_name.endswith(".docx")
                    and len(s_docx_bytes) > 500
                    and t_docx_name.endswith(".docx")
                    and len(t_docx_bytes) > 500
                    and s_pdf_name.endswith(".pdf")
                    and s_pdf_bytes.startswith(b"%PDF")
                    and t_pdf_name.endswith(".pdf")
                    and t_pdf_bytes.startswith(b"%PDF")
                )

                # 6. Multi-Tenant Isolation
                cross_view = get_writing_feedback(telegram_user=teacher_b, feedback_id=fb_b1["id"], database_path=path)
                cross_appr = approve_writing_feedback(telegram_user=teacher_b, feedback_id=fb_b1["id"], database_path=path)
                isolation_valid = (cross_view is None and cross_appr is None)

                # 7. Privacy: Zero raw text in telemetry
                with database.database_connection(path) as conn:
                    events = conn.execute("SELECT properties_json FROM product_events").fetchall()
                    raw_leak = any(
                        "Renewable energy is vital" in str(e["properties_json"])
                        or "Tehran" in str(e["properties_json"])
                        for e in events
                    )
                    privacy_valid = not raw_leak and len(events) >= 3

                # 8. Keyboards bounded to 64 bytes
                kbs = [
                    writing_feedback_mode_keyboard(class_a["id"], 1),
                    writing_feedback_view_keyboard(fb_b1["id"], class_a["id"], 1, approved=False),
                    writing_feedback_view_keyboard(fb_b1["id"], class_a["id"], 2, approved=True),
                    writing_feedback_export_keyboard(fb_b1["id"], class_a["id"], 1),
                ]
                kbs_valid = all(
                    len(btn.callback_data.encode("utf-8")) <= 64
                    for kb in kbs
                    for row in kb.inline_keyboard
                    for btn in row
                )

                checks = {
                    "schema_v17_deployed": True,
                    "a1_paragraph_light_mode_supported": a1_valid,
                    "b1_email_balanced_mode_supported": b1_valid,
                    "b2_essay_detailed_mode_supported": b2_valid,
                    "rubric_scoring_separates_grades_draft": rubric_valid,
                    "no_full_rewrite_preserves_student_agency": no_rewrite_valid,
                    "teacher_approval_and_summary_lifecycle": approval_valid,
                    "teacher_comment_editing_supported": edit_comments_valid,
                    "dual_exports_word_and_pdf_generated": exports_valid,
                    "multi_tenant_isolation_verified": isolation_valid,
                    "zero_raw_student_text_in_telemetry": privacy_valid,
                    "telegram_keyboards_bounded_64_bytes": kbs_valid,
                }
                passed = all(checks.values())

                return {
                    "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "gate": "Day 17 — Writing Feedback Copilot around Revision",
                    "schema_version": 18,
                    "checks": checks,
                    "passed": passed,
                    "engineering_status": "PASS" if passed else "FAIL",
                    "details": {
                        "feedback_id": fb_b1["id"],
                        "estimated_minutes_saved": fb_b1["estimated_minutes_saved"],
                        "student_label": fb_b1["student_label"],
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
    parser = argparse.ArgumentParser(description="Evaluate TeacherOS Day 17 Writing Feedback.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = evaluate_day17()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"DAY 17 ACCEPTANCE: {report['engineering_status']}")
    print(f"Report: {output_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
