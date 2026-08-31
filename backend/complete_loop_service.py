from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import database
from class_context import build_class_context
from class_dashboard_service import class_dashboard_snapshot
from class_service import create_class
from class_setup_service import (
    get_setup_draft,
    save_setup_draft,
    start_setup_draft,
)
from day4_quality_gate import run_evaluation
from lesson_history_service import (
    cancel_planned_lesson,
    lesson_conversion_metrics,
    list_lesson_history,
    mark_lesson_taught,
    schedule_material_lesson,
)
from next_lesson_service import (
    claim_recommendation_generation,
    complete_next_lesson_plan,
    get_or_create_recommendation,
    get_recommendation,
    next_lesson_metrics,
    plan_timing_total,
    record_next_lesson_edit,
    record_next_lesson_followup,
    select_recommendation_mode,
    set_manual_next_lesson_request,
    set_recommendation_priority,
    toggle_recommendation_source,
)
from outcome_checkin_service import (
    get_lesson_outcome,
    save_outcome_facts,
    schedule_outcome_reminder,
    update_outcome_note,
)
from prompt_contracts import get_prompt_contract
from validators import validate_model_response


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def execute_complete_loop(
    *,
    telegram_user: Any,
    class_name: str = "IELTS B2 Morning",
    cefr_level: str = "B2",
    goal: str = "Speaking fluency and exam preparation",
    lesson_duration_minutes: int = 60,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Execute and verify the full 14-day closed teaching loop."""
    user_id = telegram_user.id

    # 1. Class Setup
    created_class = create_class(
        telegram_user=telegram_user,
        display_name=class_name,
        level=cefr_level,
        goal=goal,
        database_path=database_path,
    )
    if created_class is None:
        raise RuntimeError("Failed to create class.")
    class_id = int(created_class["id"])
    if lesson_duration_minutes:
        with database.database_connection(database_path) as conn:
            conn.execute(
                "UPDATE classes SET lesson_duration_minutes = ? WHERE id = ?",
                (lesson_duration_minutes, class_id),
            )

    # 2. Class Dashboard Initial State
    dash_init = class_dashboard_snapshot(
        telegram_user_id=user_id, class_id=class_id, database_path=database_path
    )

    # 3. Generate and Save Class-Aware Lesson
    contract = get_prompt_contract("lesson")
    lesson_content = (
        f"# Lesson Overview\n"
        f"Level: {cefr_level} | Time: {lesson_duration_minutes} mins\n"
        f"Goal: {goal}\n\n"
        f"# Materials\n"
        f"- Whiteboard, discussion prompt cards, vocabulary handouts\n\n"
        f"# Can-Do Objectives\n"
        f"- Students can express and justify opinions in structured speaking tasks.\n\n"
        f"# Procedure\n"
        f"- Warm-up: Quick opinion elicitation (Time: 10 mins)\n"
        f"- Input: Useful phrases for hedging and debate (Time: 15 mins)\n"
        f"- Controlled Practice: Paired discussion prompts (Time: 15 mins)\n"
        f"- Communicative Task: Small group mini-debate (Time: 15 mins)\n"
        f"- Wrap-up & Diagnostic Check: Exit ticket (Time: 5 mins)\n\n"
        f"# Assessment\n"
        f"- Formative observation of fluency and accurate use of target expressions.\n\n"
        f"# Homework & Extension\n"
        f"- Write a short 100-word reflection justifying one side of today's debate topic."
    )
    validation = validate_model_response(
        raw=json.dumps({"content": lesson_content}),
        contract=contract,
    )
    if not validation.valid:
        raise ValueError(f"Lesson content validation failed: {validation.errors}")

    material_id = database.save_generated_material(
        telegram_user=telegram_user,
        material_type="lesson",
        title=f"Lesson 1: {class_name}",
        content=lesson_content,
        class_id=class_id,
    )

    # 4. Schedule Lesson as Next Planned Lesson
    scheduled = schedule_material_lesson(
        telegram_user_id=user_id,
        material_id=material_id,
        date_choice="today",
        database_path=database_path,
    )
    lesson = scheduled["lesson"]
    lesson_id = int(lesson["id"])

    # 5. Mark Lesson as Taught
    mark_lesson_taught(
        telegram_user_id=user_id, lesson_id=lesson_id, database_path=database_path
    )

    # 6. Capture 30-Second Outcome Facts
    save_outcome_facts(
        telegram_user_id=user_id,
        lesson_id=lesson_id,
        result="partly_achieved",
        difficulty_categories=["pace", "language"],
        completion_status="partly_completed",
        database_path=database_path,
    )
    update_outcome_note(
        telegram_user_id=user_id,
        lesson_id=lesson_id,
        note="Fluency was good, but group debate needed more scaffolding.",
        database_path=database_path,
    )
    outcome = get_lesson_outcome(
        telegram_user_id=user_id, lesson_id=lesson_id, database_path=database_path
    )

    # 7. Generate Next Lesson Recommendation Proposal
    rec = get_or_create_recommendation(
        telegram_user_id=user_id, class_id=class_id, force_refresh=True,
        database_path=database_path,
    )
    if rec is None:
        raise RuntimeError("Failed to generate next lesson recommendation.")
    rec_id = int(rec["id"])

    # 8. Select Mode and Claim Generation
    select_recommendation_mode(
        telegram_user_id=user_id,
        recommendation_id=rec_id,
        mode="continue_unfinished",
        database_path=database_path,
    )
    claim_recommendation_generation(
        telegram_user_id=user_id,
        recommendation_id=rec_id,
        database_path=database_path,
    )

    # 9. Generate & Save Next Lesson Plan
    t1 = max(5, int(lesson_duration_minutes * 0.15))
    t2 = max(5, int(lesson_duration_minutes * 0.25))
    t3 = max(5, int(lesson_duration_minutes * 0.25))
    t4 = max(5, int(lesson_duration_minutes * 0.25))
    t5 = lesson_duration_minutes - (t1 + t2 + t3 + t4)

    next_lesson_content = (
        f"# Lesson Overview\n"
        f"Level: {cefr_level} | Time: {lesson_duration_minutes} mins\n"
        f"Continuity Focus: Consolidate debate vocabulary with guided scaffolds\n\n"
        f"# Materials\n"
        f"- Scaffolding worksheets, peer feedback rubrics\n\n"
        f"# Can-Do Objectives\n"
        f"- Students can use debate phrases with accurate timing and peer feedback.\n\n"
        f"# Procedure\n"
        f"- Stage 1: Retrieval Warm-up\n"
        f"  Time: {t1} mins\n"
        f"  Review vocabulary from Lesson 1.\n"
        f"- Stage 2: Structured Input\n"
        f"  Time: {t2} mins\n"
        f"  Scaffolding difficult sentence structures.\n"
        f"- Stage 3: Guided Practice\n"
        f"  Time: {t3} mins\n"
        f"  Paired role-play with feedback check.\n"
        f"- Stage 4: Extended Communicative Task\n"
        f"  Time: {t4} mins\n"
        f"  Full debate simulation.\n"
        f"- Stage 5: Assessment Check\n"
        f"  Time: {t5} mins\n"
        f"  Self-evaluation rubric.\n\n"
        f"# Assessment\n"
        f"- Peer assessment using standardized rubric.\n\n"
        f"# Homework & Extension\n"
        f"- Review debate vocabulary cards on mobile app."
    )
    next_material_id = database.save_generated_material(
        telegram_user=telegram_user,
        material_type="lesson",
        title=f"Lesson 2 (Next Plan): {class_name}",
        content=next_lesson_content,
        class_id=class_id,
    )

    plan = complete_next_lesson_plan(
        telegram_user_id=user_id,
        recommendation_id=rec_id,
        material_id=next_material_id,
        validation={"timing": 100, "overall": 100},
        database_path=database_path,
    )
    if plan is None:
        raise RuntimeError("Failed to complete next lesson plan.")
    plan_id = int(plan["id"])

    # 10. Record Teacher Follow-up Feedback
    record_next_lesson_edit(
        telegram_user_id=user_id, plan_id=plan_id, database_path=database_path
    )
    record_next_lesson_followup(
        telegram_user_id=user_id, plan_id=plan_id, accepted=True,
        database_path=database_path,
    )

    # 11. Final Dashboard & Conversion Verification
    dash_final = class_dashboard_snapshot(
        telegram_user_id=user_id, class_id=class_id, database_path=database_path
    )
    history = list_lesson_history(
        telegram_user_id=user_id, class_id=class_id, database_path=database_path
    )
    metrics = next_lesson_metrics(database_path=database_path)
    conversion = lesson_conversion_metrics(telegram_user_id=user_id, database_path=database_path)

    # Verify snapshot source linkage
    with database.database_connection(database_path) as connection:
        source_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM next_lesson_plan_sources WHERE next_lesson_plan_id = ?",
                (plan_id,),
            ).fetchone()[0]
        )

    return {
        "class_id": class_id,
        "first_material_id": material_id,
        "first_lesson_id": lesson_id,
        "outcome_id": outcome["id"] if outcome else None,
        "recommendation_id": rec_id,
        "next_plan_id": plan_id,
        "next_material_id": next_material_id,
        "plan_source_count": source_count,
        "timing_total_minutes": plan["timing_total_minutes"],
        "duration_minutes": plan["duration_minutes"],
        "timing_valid": plan["timing_total_minutes"] == plan["duration_minutes"],
        "history_count": len(history),
        "dash_outcome_rate": dash_final.get("outcome_recording_rate_percent"),
        "followup_accepted": metrics.get("followup_accepted", 0),
        "conversions": conversion,
        "passed": bool(
            class_id and material_id and lesson_id and outcome and rec_id and plan_id
            and source_count > 0 and plan["timing_total_minutes"] == plan["duration_minutes"]
        ),
    }


def simulate_recovery_scenarios(*, telegram_user: Any, database_path: Path | None = None) -> dict[str, bool]:
    """Test mid-conversation interruption, restart recovery, and safe fallbacks."""
    user_id = telegram_user.id

    # A. Interrupted setup draft resumption
    draft = start_setup_draft(telegram_user=telegram_user, database_path=database_path)
    save_setup_draft(
        telegram_user_id=user_id,
        expected_revision=int(draft["revision"]),
        step="level",
        payload={
            "display_name": "Draft Recovery Class",
            "weak_areas": ["spk"],
            "equipment": ["board"],
            "teaching_preferences": ["comm"],
        },
        database_path=database_path,
    )
    draft_resumed = get_setup_draft(telegram_user_id=user_id, database_path=database_path)
    setup_recovered = bool(
        draft_resumed and draft_resumed.get("payload", {}).get("display_name") == "Draft Recovery Class"
    )

    # Create class to test recommendation generation recovery
    recovered_class = create_class(
        telegram_user=telegram_user,
        display_name="Recovery Test Class",
        level="B1",
        database_path=database_path,
    )
    if recovered_class is None:
        raise RuntimeError("Failed to create recovery test class.")
    class_id = int(recovered_class["id"])

    # B. Interrupted next-lesson generation claim recovery
    rec = get_or_create_recommendation(
        telegram_user_id=user_id, class_id=class_id, database_path=database_path
    )
    select_recommendation_mode(
        telegram_user_id=user_id, recommendation_id=int(rec["id"]),
        mode="new_topic", database_path=database_path,
    )
    claim_recommendation_generation(
        telegram_user_id=user_id, recommendation_id=int(rec["id"]),
        database_path=database_path,
    )
    # Simulate restart by requesting active recommendation again
    rec_after_restart = get_or_create_recommendation(
        telegram_user_id=user_id, class_id=class_id, database_path=database_path
    )
    generation_recovered = bool(
        rec_after_restart and rec_after_restart["status"] == "ready"
        and rec_after_restart.get("last_error_code") == "interrupted_generation"
    )

    return {
        "setup_draft_resumption": setup_recovered,
        "generation_interruption_recovery": generation_recovered,
        "all_recovery_passed": setup_recovered and generation_recovered,
    }


def verify_multi_tenant_isolation(
    *, teacher_a: Any, teacher_b: Any, database_path: Path | None = None
) -> dict[str, bool]:
    """Verify complete tenant isolation between two distinct teachers."""
    # Teacher A creates class and lesson
    res_a = execute_complete_loop(
        telegram_user=teacher_a, class_name="Teacher A Class", cefr_level="A2",
        database_path=database_path,
    )
    class_a_id = res_a["class_id"]
    rec_a_id = res_a["recommendation_id"]
    lesson_a_id = res_a["first_lesson_id"]

    # Teacher B tries to access Teacher A's resources
    dash_b = class_dashboard_snapshot(
        telegram_user_id=teacher_b.id, class_id=class_a_id, database_path=database_path
    )
    rec_b = get_recommendation(
        telegram_user_id=teacher_b.id, recommendation_id=rec_a_id, database_path=database_path
    )
    history_b = list_lesson_history(
        telegram_user_id=teacher_b.id, class_id=class_a_id, database_path=database_path
    )
    outcome_b = get_lesson_outcome(
        telegram_user_id=teacher_b.id, lesson_id=lesson_a_id, database_path=database_path
    )

    isolation = {
        "dashboard_cross_access_blocked": dash_b is None,
        "recommendation_cross_access_blocked": rec_b is None,
        "history_cross_access_blocked": history_b == [],
        "outcome_cross_access_blocked": outcome_b is None,
    }
    isolation["all_isolation_passed"] = all(isolation.values())
    return isolation


def evaluate_phase2_ai_golden_set(
    *, mode: str = "fixture", output_path: Path | None = None
) -> dict[str, Any]:
    """Run the 40-case evaluation harness and inspect the worst 10 cases."""
    report = asyncio.run(run_evaluation(mode=mode, model="deterministic-contract-fixture", concurrency=2))
    cases = report.get("cases", [])
    
    # Sort cases by score ascending to identify worst 10
    sorted_cases = sorted(
        cases,
        key=lambda c: (float(c.get("score_percent", 0)), 0 if c.get("passed") else -1),
    )
    worst_10 = sorted_cases[:10]
    summary = report["summary"]
    inspections = [
        {
            "case_id": case.get("case_id"),
            "passed": case.get("passed"),
            "score_percent": case.get("score_percent"),
            "checks": case.get("checks"),
            "timing_valid": case.get("checks", {}).get("timing_totals", True),
            "schema_valid": case.get("checks", {}).get("schema", True),
            "safety_valid": case.get("checks", {}).get("prohibited_claims", True),
        }
        for case in worst_10
    ]
    all_passed = bool(
        summary["cases_passed"] == len(cases)
        and summary["safety_invariant_failures"] == 0
        and not summary["release_blocked"]
    )
    pass_rate = round((summary["cases_passed"] / len(cases)) * 100) if cases else 0
    eval_result = {
        "evaluated_at_utc": _utc_now(),
        "total_cases": len(cases),
        "passed_cases": summary["cases_passed"],
        "pass_rate_percent": pass_rate,
        "schema_pass_rate": summary["schema_pass_rate"],
        "pedagogical_pass_rate": summary["pedagogical_qa_pass_rate"],
        "unsupported_claim_rate": summary["unsupported_claim_rate"],
        "injection_pass_rate": summary["injection_pass_rate"],
        "safety_invariant_failures": summary["safety_invariant_failures"],
        "release_blocked": summary["release_blocked"],
        "worst_10_inspection": inspections,
        "worst_10_inspections": inspections,
        "all_cases_passed": all_passed,
        "passed": all_passed,
    }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(eval_result, indent=2, sort_keys=True), encoding="utf-8")

    return eval_result
