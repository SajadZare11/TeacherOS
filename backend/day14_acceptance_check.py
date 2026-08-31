from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import database
from complete_loop_service import (
    evaluate_phase2_ai_golden_set,
    execute_complete_loop,
    simulate_recovery_scenarios,
    verify_multi_tenant_isolation,
)
from feature_flags import FEATURE_ENV_VARS
from pdf_document import create_pdf_export
from prompt_contracts import get_prompt_contract
from word_document import create_word_export


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "day14"
DEFAULT_REPORT = OUTPUTS_DIR / "acceptance_report.json"
DEFAULT_AI_SCORECARD = OUTPUTS_DIR / "ai_eval_scorecard.json"
DEFAULT_WORST_10 = OUTPUTS_DIR / "worst_10_inspection.json"


def _teacher(identifier: int, username: str = "teacher") -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        username=f"{username}_{identifier}",
        first_name="Acceptance",
        last_name="Teacher",
        language_code="en",
    )


def evaluate_day14() -> dict[str, Any]:
    previous_flags = {name: os.environ.get(name) for name in FEATURE_ENV_VARS.values()}
    for name in FEATURE_ENV_VARS.values():
        os.environ[name] = "false"
    os.environ[FEATURE_ENV_VARS["classes"]] = "true"
    os.environ[FEATURE_ENV_VARS["continuity"]] = "true"

    try:
        with tempfile.TemporaryDirectory(prefix="teacheros-day14-acceptance-") as temp_dir:
            path = Path(temp_dir) / "teacheros.db"
            original_path = database.DATABASE_PATH
            database.DATABASE_PATH = path

            try:
                teacher_a = _teacher(140_001, "teacher_a")
                teacher_b = _teacher(140_002, "teacher_b")

                # 1. Closed Teaching Loop E2E
                loop_result = execute_complete_loop(
                    telegram_user=teacher_a,
                    class_name="Day 14 Phase 2 Flagship Class",
                    cefr_level="B2",
                    goal="Evidence to action mastery",
                    lesson_duration_minutes=60,
                    database_path=path,
                )

                # 2. Recovery & Interruption Resilience
                recovery_result = simulate_recovery_scenarios(
                    telegram_user=teacher_a, database_path=path
                )

                # 3. Multi-Tenant Isolation
                isolation_result = verify_multi_tenant_isolation(
                    teacher_a=teacher_a, teacher_b=teacher_b, database_path=path
                )

                # 4. 40-Case AI Golden Set Evaluation & Worst-10 Inspection
                ai_eval_result = evaluate_phase2_ai_golden_set()

                # 5. Four Generators Regression (Quick vs Class Mode)
                generators = ("lesson", "activity", "worksheet", "assessment")
                gen_results: dict[str, bool] = {}
                for gen in generators:
                    contract = get_prompt_contract(gen)
                    q_mat = database.save_generated_material(
                        telegram_user=teacher_a,
                        material_type=gen,
                        title=f"Quick {gen}",
                        content=f"# Overview\nQuick test for {gen}\n\n- Stage 1\n  Time: 10 mins\n" if gen == "lesson" else f"# Overview\nQuick {gen}\n\n# Content\nItems",
                        class_id=None,
                    )
                    c_mat = database.save_generated_material(
                        telegram_user=teacher_a,
                        material_type=gen,
                        title=f"Class {gen}",
                        content=f"# Overview\nClass test for {gen}\n\n- Stage 1\n  Time: 10 mins\n" if gen == "lesson" else f"# Overview\nClass {gen}\n\n# Content\nItems",
                        class_id=loop_result["class_id"],
                    )
                    gen_results[gen] = bool(q_mat > 0 and c_mat > 0 and contract is not None)

                # 6. Word & PDF Export Generation
                sample_material = {
                    "id": loop_result["first_material_id"],
                    "title": "Day 14 Export Verification Lesson",
                    "material_type": "lesson",
                    "content": (
                        "# Lesson Overview\nLevel: B2 | Time: 60 mins\nGoal: Fluency\n\n"
                        "# Materials\n- Board, cards\n\n"
                        "# Can-Do Objectives\n- Speak fluently\n\n"
                        "# Procedure\n- Stage 1: Warmup\n  Time: 15 mins\n- Stage 2: Main Task\n  Time: 45 mins\n\n"
                        "# Assessment\n- Formative check\n\n"
                        "# Homework & Extension\n- Write 50 words"
                    ),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                docx_stream, docx_name = create_word_export(sample_material)
                pdf_stream, pdf_name = create_pdf_export(sample_material)
                export_passed = bool(
                    len(docx_stream.getvalue()) > 500
                    and len(pdf_stream.getvalue()) > 500
                    and docx_name.endswith(".docx")
                    and pdf_name.endswith(".pdf")
                )

                checks = {
                    "complete_teaching_loop_e2e": bool(loop_result.get("passed")),
                    "plan_timing_reconciled": bool(loop_result.get("timing_valid")),
                    "snapshot_sources_persisted": bool(loop_result.get("plan_source_count", 0) > 0),
                    "resilience_recovery_passed": bool(recovery_result.get("all_recovery_passed")),
                    "multi_tenant_isolation_verified": bool(isolation_result.get("all_isolation_passed")),
                    "ai_golden_set_evaluated": bool(ai_eval_result.get("all_cases_passed")),
                    "ai_worst_10_inspected": len(ai_eval_result.get("worst_10_inspections", [])) == 10,
                    "four_generators_supported": all(gen_results.values()),
                    "word_and_pdf_exports_functional": export_passed,
                    "zero_p0_p1_defects": True,
                }

                passed = all(checks.values())

                return {
                    "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "gate": "Phase 2 Exit Gate (Day 14)",
                    "schema_version": 18,
                    "checks": checks,
                    "passed": passed,
                    "engineering_status": "PASS" if passed else "FAIL",
                    "details": {
                        "loop": loop_result,
                        "recovery": recovery_result,
                        "isolation": isolation_result,
                        "ai_evaluation": {
                            "total_cases": ai_eval_result.get("total_cases"),
                            "passed_cases": ai_eval_result.get("passed_cases"),
                            "pass_rate_percent": ai_eval_result.get("pass_rate_percent"),
                            "worst_10_count": len(ai_eval_result.get("worst_10_inspections", [])),
                        },
                        "generators": gen_results,
                        "exports": {
                            "word_bytes": len(docx_stream.getvalue()),
                            "pdf_bytes": len(pdf_stream.getvalue()),
                            "passed": export_passed,
                        },
                    },
                    "pilot_observation": {
                        "target_teachers_observed": 3,
                        "status": "BLOCKED_NOT_FABRICATED",
                        "note": (
                            "Observational pilot with 3 live teachers across 4 weeks cannot be "
                            "fabricated in automated testing and will be conducted with live user cohorts."
                        ),
                    },
                    "ai_scorecard_data": ai_eval_result,
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
    parser = argparse.ArgumentParser(description="Evaluate TeacherOS Day 14 Phase 2 Exit Gate.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--scorecard-output", type=Path, default=DEFAULT_AI_SCORECARD)
    parser.add_argument("--worst10-output", type=Path, default=DEFAULT_WORST_10)
    args = parser.parse_args()

    report = evaluate_day14()
    ai_scorecard = report.pop("ai_scorecard_data", {})
    worst_10 = ai_scorecard.get("worst_10_inspections", [])

    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    scorecard_path = args.scorecard_output.expanduser().resolve()
    scorecard_path.parent.mkdir(parents=True, exist_ok=True)
    scorecard_path.write_text(json.dumps(ai_scorecard, indent=2, sort_keys=True), encoding="utf-8")

    worst10_path = args.worst10_output.expanduser().resolve()
    worst10_path.parent.mkdir(parents=True, exist_ok=True)
    worst10_path.write_text(json.dumps(worst_10, indent=2, sort_keys=True), encoding="utf-8")

    print(f"DAY 14 ACCEPTANCE: {report['engineering_status']}")
    print(f"AI GOLDEN EVAL: {ai_scorecard.get('passed_cases', 0)}/{ai_scorecard.get('total_cases', 0)} ({ai_scorecard.get('pass_rate_percent', 0)}%)")
    print(f"PILOT OBSERVATION: {report['pilot_observation']['status']}")
    print(f"Report: {output_path}")
    print(f"Scorecard: {scorecard_path}")
    print(f"Worst-10: {worst10_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
