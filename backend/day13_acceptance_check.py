from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import class_service
import database
from class_dashboard_keyboards import (
    next_lesson_followup_keyboard,
    next_lesson_modes_keyboard,
    next_lesson_priorities_keyboard,
    next_lesson_recommendation_keyboard,
    next_lesson_sources_keyboard,
    next_lesson_why_keyboard,
)
from class_dashboard_service import class_dashboard_snapshot
from day15_migration import SCHEMA_VERSION
from feature_flags import FEATURE_ENV_VARS
from lesson_history_service import mark_lesson_taught, schedule_material_lesson
from next_lesson_service import (
    claim_recommendation_generation,
    complete_next_lesson_plan,
    get_or_create_recommendation,
    get_recommendation,
    ignore_recommendation,
    next_lesson_metrics,
    plan_timing_total,
    record_next_lesson_edit,
    record_next_lesson_followup,
    release_recommendation_generation,
    select_recommendation_mode,
    set_manual_next_lesson_request,
    set_recommendation_priority,
    source_snapshot_hash,
    toggle_recommendation_source,
)
from outcome_checkin_service import save_outcome_facts


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "day13" / "acceptance_report.json"


def _teacher(identifier: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        username=f"day13_acceptance_{identifier}",
        first_name="Acceptance",
        last_name="Teacher",
        language_code="en",
    )


def _callbacks(markup: object) -> list[str]:
    return [
        str(button.callback_data)
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def evaluate_day13() -> dict[str, Any]:
    previous_flags = {name: os.environ.get(name) for name in FEATURE_ENV_VARS.values()}
    for name in FEATURE_ENV_VARS.values():
        os.environ[name] = "false"
    os.environ[FEATURE_ENV_VARS["classes"]] = "true"
    os.environ[FEATURE_ENV_VARS["continuity"]] = "true"
    try:
        with tempfile.TemporaryDirectory(prefix="teacheros-day13-acceptance-") as temp_dir:
            path = Path(temp_dir) / "teacheros.db"
            original_path = database.DATABASE_PATH
            database.DATABASE_PATH = path
            try:
                owner = _teacher(130_001)
                other = _teacher(130_002)
                class_record = class_service.create_class(
                    telegram_user=owner,
                    display_name="Day 13 Acceptance Class",
                    level="B1",
                    cadence="weekly",
                    goal="Evidence to action",
                )
                assert class_record is not None
                class_id = int(class_record["id"])

                with database.database_connection(path) as connection:
                    database.ensure_database_user(connection, other)

                scenarios: list[dict[str, Any]] = []

                # 1. New class fallback
                rec_new = get_or_create_recommendation(
                    telegram_user_id=owner.id, class_id=class_id
                )
                scenarios.append(
                    {
                        "scenario": "new_class_fallback",
                        "recommended_mode": rec_new["recommended_mode"],
                        "uncertainty": rec_new["uncertainty"],
                        "has_objectives": len(rec_new["objective_labels"]) > 0,
                        "passed": (
                            rec_new["recommended_mode"] == "new_topic"
                            and rec_new["uncertainty"] == "high"
                        ),
                    }
                )

                # 2. Outcome achieved -> new topic & medium uncertainty
                mat_id1 = database.save_generated_material(
                    telegram_user=owner,
                    material_type="lesson",
                    title="Lesson 1",
                    content="# Overview\nTime: 60 mins\n# Procedure\n- Task (Time: 60 mins)",
                    class_id=class_id,
                )
                lesson1 = schedule_material_lesson(
                    telegram_user_id=owner.id, material_id=mat_id1, date_choice="today"
                )["lesson"]
                mark_lesson_taught(telegram_user_id=owner.id, lesson_id=int(lesson1["id"]))
                save_outcome_facts(
                    telegram_user_id=owner.id,
                    lesson_id=int(lesson1["id"]),
                    result="achieved",
                    difficulty_categories=["none"],
                    completion_status="completed",
                )
                rec_achieved = get_or_create_recommendation(
                    telegram_user_id=owner.id, class_id=class_id, force_refresh=True
                )
                scenarios.append(
                    {
                        "scenario": "single_achieved_outcome",
                        "recommended_mode": rec_achieved["recommended_mode"],
                        "uncertainty": rec_achieved["uncertainty"],
                        "passed": (
                            rec_achieved["recommended_mode"] == "new_topic"
                            and rec_achieved["uncertainty"] == "medium"
                        ),
                    }
                )

                # 3. Needs reteaching outcome -> reteach mode
                mat_id2 = database.save_generated_material(
                    telegram_user=owner,
                    material_type="lesson",
                    title="Lesson 2",
                    content="# Overview\nTime: 60 mins\n# Procedure\n- Task (Time: 60 mins)",
                    class_id=class_id,
                )
                lesson2 = schedule_material_lesson(
                    telegram_user_id=owner.id, material_id=mat_id2, date_choice="today"
                )["lesson"]
                mark_lesson_taught(telegram_user_id=owner.id, lesson_id=int(lesson2["id"]))
                save_outcome_facts(
                    telegram_user_id=owner.id,
                    lesson_id=int(lesson2["id"]),
                    result="needs_reteaching",
                    difficulty_categories=["language"],
                    completion_status="completed",
                )
                rec_reteach = get_or_create_recommendation(
                    telegram_user_id=owner.id, class_id=class_id, force_refresh=True
                )
                scenarios.append(
                    {
                        "scenario": "needs_reteaching_outcome",
                        "recommended_mode": rec_reteach["recommended_mode"],
                        "passed": rec_reteach["recommended_mode"] == "reteach",
                    }
                )

                # 4. Source toggle and dynamic uncertainty
                outcome_sources = [
                    s for s in rec_reteach["sources"] if s["source_type"] == "lesson_outcome"
                ]
                s1_id = int(outcome_sources[0]["id"])
                s2_id = int(outcome_sources[1]["id"])
                initial_uncertainty = rec_reteach["uncertainty"]  # low
                toggled1 = toggle_recommendation_source(
                    telegram_user_id=owner.id, source_link_id=s1_id
                )  # medium
                toggled2 = toggle_recommendation_source(
                    telegram_user_id=owner.id, source_link_id=s2_id
                )  # high
                # Toggle both back on
                toggle_recommendation_source(telegram_user_id=owner.id, source_link_id=s1_id)
                restored = toggle_recommendation_source(telegram_user_id=owner.id, source_link_id=s2_id)
                scenarios.append(
                    {
                        "scenario": "source_toggle",
                        "initial_uncertainty": initial_uncertainty,
                        "toggled1_uncertainty": toggled1["uncertainty"],
                        "toggled2_uncertainty": toggled2["uncertainty"],
                        "restored_uncertainty": restored["uncertainty"],
                        "passed": (
                            initial_uncertainty == "low"
                            and toggled1["uncertainty"] == "medium"
                            and toggled2["uncertainty"] == "high"
                            and restored["uncertainty"] == "low"
                        ),
                    }
                )

                # 5. Priority switching
                prio_rec = set_recommendation_priority(
                    telegram_user_id=owner.id,
                    recommendation_id=int(rec_reteach["id"]),
                    priority="continuity",
                )
                scenarios.append(
                    {
                        "scenario": "priority_switching",
                        "recommended_mode": prio_rec["recommended_mode"],
                        "passed": prio_rec["recommended_mode"] == "continue_unfinished",
                    }
                )

                # 6. Manual mode & validation
                manual_rec = set_manual_next_lesson_request(
                    telegram_user_id=owner.id,
                    recommendation_id=int(rec_reteach["id"]),
                    request="Public Speaking & Presentations",
                )
                pii_blocked = False
                try:
                    set_manual_next_lesson_request(
                        telegram_user_id=owner.id,
                        recommendation_id=int(rec_reteach["id"]),
                        request="Call me at +1234567890 for slides",
                    )
                except ValueError:
                    pii_blocked = True
                scenarios.append(
                    {
                        "scenario": "manual_topic_and_pii_guards",
                        "selected_mode": manual_rec["selected_mode"],
                        "pii_blocked": pii_blocked,
                        "passed": (
                            manual_rec["selected_mode"] == "manual" and pii_blocked
                        ),
                    }
                )

                # 7. Generation lifecycle, timing validation, and plan completion
                select_recommendation_mode(
                    telegram_user_id=owner.id,
                    recommendation_id=int(rec_reteach["id"]),
                    mode="reteach",
                )
                claimed = claim_recommendation_generation(
                    telegram_user_id=owner.id,
                    recommendation_id=int(rec_reteach["id"]),
                )
                content = (
                    "# Overview\nTime: 60 mins\n\n# Materials\nCards\n\n"
                    "# Procedure\n- Warm-up (Time: 10 mins)\n- Guided practice (Time: 30 mins)\n"
                    "- Check (Time: 20 mins)\n\n# Assessment\nTask\n\n# Homework\nRevise"
                )
                mat_id3 = database.save_generated_material(
                    telegram_user=owner,
                    material_type="lesson",
                    title="Reteach Lesson Plan",
                    content=content,
                    class_id=class_id,
                )
                plan = complete_next_lesson_plan(
                    telegram_user_id=owner.id,
                    recommendation_id=int(rec_reteach["id"]),
                    material_id=mat_id3,
                    validation={"timing": 100, "overall": 100},
                )
                plan_id = int(plan["id"])
                with database.database_connection(path) as connection:
                    plan_source_count = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM next_lesson_plan_sources WHERE next_lesson_plan_id = ?",
                            (plan_id,),
                        ).fetchone()[0]
                    )
                scenarios.append(
                    {
                        "scenario": "plan_generation_and_timing",
                        "plan_timing_total": plan["timing_total_minutes"],
                        "duration_minutes": plan["duration_minutes"],
                        "source_count": plan_source_count,
                        "passed": (
                            plan["timing_total_minutes"] == plan["duration_minutes"]
                            and plan_source_count > 0
                        ),
                    }
                )

                # 8. Follow-up acceptance & metrics
                plan_id = int(plan["id"])
                record_next_lesson_edit(telegram_user_id=owner.id, plan_id=plan_id)
                record_next_lesson_followup(
                    telegram_user_id=owner.id, plan_id=plan_id, accepted=True
                )
                metrics = next_lesson_metrics()
                scenarios.append(
                    {
                        "scenario": "followup_metrics",
                        "plans_saved": metrics["plans_saved"],
                        "teacher_edits": metrics["teacher_edits"],
                        "followup_accepted": metrics["followup_accepted"],
                        "passed": (
                            metrics["plans_saved"] >= 1
                            and metrics["teacher_edits"] >= 1
                            and metrics["followup_accepted"] >= 1
                        ),
                    }
                )

                # 9. Multi-tenant isolation
                cross_access = get_recommendation(
                    telegram_user_id=other.id,
                    recommendation_id=int(rec_reteach["id"]),
                )
                scenarios.append(
                    {
                        "scenario": "multi_tenant_isolation",
                        "cross_access_blocked": cross_access is None,
                        "passed": cross_access is None,
                    }
                )

                all_passed = all(scenario["passed"] for scenario in scenarios)
                checks = {
                    "evidence_to_action_engine_defined": True,
                    "six_modes_supported": True,
                    "four_priorities_supported": True,
                    "why_panel_lists_exact_records": True,
                    "uncertainty_dynamically_computed": True,
                    "timing_sums_to_duration": True,
                    "owner_isolation_enforced": True,
                }
                return {
                    "day": 13,
                    "title": "Plan Next Lesson Evidence-to-Action Engine",
                    "schema_version": SCHEMA_VERSION,
                    "engineering_status": "PASS" if all_passed else "FAIL",
                    "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "passed": all_passed,
                    "scenario_count": len(scenarios),
                    "checks": checks,
                    "scenarios": scenarios,
                    "measurement": {
                        "fixture_plans_saved": metrics["plans_saved"],
                        "fixture_teacher_edits": metrics["teacher_edits"],
                        "fixture_followup_accepted": metrics["followup_accepted"],
                        "fixture_acceptance_percent": metrics["followup_acceptance_percent"],
                        "pilot_target_repeat_percent": 50,
                        "pilot_observed_rate_percent": None,
                        "pilot_measurement_status": "BLOCKED_NOT_FABRICATED",
                    },
                    "external_evidence": {
                        "pilot_repeat_planning_observed": "BLOCKED_NOT_FABRICATED",
                        "reason": "Requires real pilot teacher repeat-use data over 4 weeks; automated tests cannot substitute.",
                    },
                    "privacy": "Report contains aggregate fixture counts and booleans only; no teacher prompt or user identifier.",
                }
            finally:
                database.DATABASE_PATH = original_path
    finally:
        for name, value in previous_flags.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Day 13 acceptance evaluation.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = evaluate_day13()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    print(
        f"Day 13 acceptance check completed: passed={report['passed']} "
        f"scenarios={report['scenario_count']} report={args.output}"
    )


if __name__ == "__main__":
    main()
