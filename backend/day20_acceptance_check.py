"""TeacherOS Day 20 Acceptance Check.

Validates the transparent retrieval and spaced-review queue:
- Schema v20 deployed with audit logs and owner integrity trigger.
- All 6 language categories and 4 source types supported.
- Configurable interval schedule ([2, 7, 21, 45] days) with deterministic date arithmetic.
- Review load capped (max 5 items) to prevent lesson hijacking.
- Retrieval warm-up block proposal for next lesson planning.
- Full state handling: empty, overdue, snoozed, paused, archived, deleted-source, manual correction.
- Multi-tenant isolation and 64-byte Telegram callback bounds.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import database
from class_service import create_class
from feature_flags import FEATURE_ENV_VARS
from retrieval_review_keyboards import (
    add_category_keyboard,
    add_confirm_keyboard,
    confidence_picker_keyboard,
    due_item_card_keyboard,
    intervals_settings_keyboard,
    queue_browser_keyboard,
    queue_item_actions_keyboard,
    review_dashboard_keyboard,
    review_result_keyboard,
    snooze_picker_keyboard,
)
from retrieval_review_service import (
    DEFAULT_INTERVALS,
    MAX_DUE_ITEMS_PER_LESSON,
    VALID_CATEGORIES,
    VALID_SOURCE_TYPES,
    add_batch_review_items,
    add_review_item,
    archive_item,
    count_due_items,
    count_queue_items,
    get_class_intervals,
    get_due_items,
    get_review_item,
    get_review_queue,
    get_review_queue_stats,
    handle_deleted_source,
    override_review_schedule,
    pause_item,
    propose_retrieval_block,
    record_review,
    resume_item,
    snooze_item,
    update_class_intervals,
    update_confidence,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "day20"
DEFAULT_REPORT = OUTPUTS_DIR / "acceptance_report.json"


def _teacher(identifier: int, username: str = "teacher") -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        username=f"{username}_{identifier}",
        first_name="Acceptance",
        last_name="Teacher",
        language_code="en",
    )


def evaluate_day20() -> dict[str, Any]:
    previous_flags = {name: os.environ.get(name) for name in FEATURE_ENV_VARS.values()}
    for name in FEATURE_ENV_VARS.values():
        os.environ[name] = "false"
    os.environ[FEATURE_ENV_VARS["classes"]] = "true"
    os.environ[FEATURE_ENV_VARS["continuity"]] = "true"
    os.environ[FEATURE_ENV_VARS["evidence"]] = "true"

    try:
        with tempfile.TemporaryDirectory(prefix="teacheros-day20-acceptance-") as temp_dir:
            path = Path(temp_dir) / "teacheros.db"
            original_path = database.DATABASE_PATH
            database.DATABASE_PATH = path

            try:
                database.initialize_database(path)
                teacher_a = _teacher(200_001, "teacher_a")
                teacher_b = _teacher(200_002, "teacher_b")

                with database.database_connection(path) as conn:
                    user_a_id = database.ensure_database_user(conn, teacher_a)
                    user_b_id = database.ensure_database_user(conn, teacher_b)

                class_a = create_class(
                    telegram_user=teacher_a,
                    display_name="B2 Upper Intermediate",
                    level="B2",
                    age_group="adults",
                    learner_count_band="13_20",
                    goal="Spoken fluency and natural collocations",
                    database_path=path,
                )
                class_a_id = int(class_a["id"])

                class_b = create_class(
                    telegram_user=teacher_b,
                    display_name="A2 Elementary",
                    level="A2",
                    age_group="young_learners",
                    learner_count_band="6_12",
                    goal="Basic daily routines",
                    database_path=path,
                )
                class_b_id = int(class_b["id"])

                # 1. Schema check
                with database.database_connection(path) as conn:
                    schema_ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
                    items_tbl = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='retrieval_review_items'"
                    ).fetchone()
                    logs_tbl = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='retrieval_review_logs'"
                    ).fetchone()
                    schema_valid = (schema_ver >= 20 and items_tbl is not None and logs_tbl is not None)

                # 2. All 6 language categories supported
                items_by_cat = {}
                for cat in VALID_CATEGORIES:
                    item = add_review_item(
                        user_id=user_a_id,
                        class_id=class_a_id,
                        category=cat,
                        prompt_text=f"Test prompt for {cat}",
                        target_answer=f"Test answer for {cat}",
                        source_type="lesson",
                        source_id=101,
                        confidence="medium",
                        database_path=path,
                    )
                    items_by_cat[cat] = item
                all_cats_valid = len(items_by_cat) == 6 and all(v is not None for v in items_by_cat.values())

                # 3. All 4 source types supported
                src_types_valid = True
                for stype in VALID_SOURCE_TYPES:
                    res = add_review_item(
                        user_id=user_a_id,
                        class_id=class_a_id,
                        category="vocabulary",
                        prompt_text=f"Item from source {stype}",
                        target_answer=f"Answer from source {stype}",
                        source_type=stype,
                        source_id=202 if stype != "manual" else None,
                        database_path=path,
                    )
                    if not res or res["source_type"] != stype:
                        src_types_valid = False

                # 4. Configurable intervals schedule ([2, 7, 21, 45])
                default_intervals = get_class_intervals(user_id=user_a_id, class_id=class_a_id, database_path=path)
                intervals_default_ok = (default_intervals == DEFAULT_INTERVALS)

                custom_intervals = [3, 10, 30, 60]
                updated_count = update_class_intervals(
                    user_id=user_a_id,
                    class_id=class_a_id,
                    intervals=custom_intervals,
                    database_path=path,
                )
                intervals_custom_ok = (
                    updated_count > 0
                    and get_class_intervals(user_id=user_a_id, class_id=class_a_id, database_path=path) == custom_intervals
                )

                # Reset to default for remaining tests
                update_class_intervals(user_id=user_a_id, class_id=class_a_id, intervals=DEFAULT_INTERVALS, database_path=path)

                # 5. Deterministic due dates and stage transitions
                today_d = datetime.now(timezone.utc).date()
                today_str = today_d.strftime("%Y-%m-%d")

                test_item = add_review_item(
                    user_id=user_a_id,
                    class_id=class_a_id,
                    category="grammar",
                    prompt_text="Past continuous vs past simple interruption",
                    target_answer="While I was cooking, the phone rang.",
                    source_type="lesson",
                    database_path=path,
                )
                item_id = int(test_item["id"])

                # Advance with 'remembered': stage 0 -> 1 (+7 days)
                rec1 = record_review(
                    user_id=user_a_id,
                    item_id=item_id,
                    result="remembered",
                    review_date=today_str,
                    database_path=path,
                )
                expected_date_1 = (today_d + timedelta(days=DEFAULT_INTERVALS[1])).strftime("%Y-%m-%d")
                stage1_ok = (rec1["interval_stage"] == 1 and rec1["next_review_date"] == expected_date_1 and rec1["review_count"] == 1)

                # Advance with 'partly_remembered': stage 1 -> 1 (+7 days)
                review_date_2 = (today_d + timedelta(days=1)).strftime("%Y-%m-%d")
                rec2 = record_review(
                    user_id=user_a_id,
                    item_id=item_id,
                    result="partly_remembered",
                    review_date=review_date_2,
                    database_path=path,
                )
                expected_date_2 = (today_d + timedelta(days=1 + DEFAULT_INTERVALS[1])).strftime("%Y-%m-%d")
                stage2_ok = (rec2["interval_stage"] == 1 and rec2["next_review_date"] == expected_date_2 and rec2["review_count"] == 2)

                # Step back with 'forgotten': stage 1 -> 0 (+2 days)
                review_date_3 = (today_d + timedelta(days=2)).strftime("%Y-%m-%d")
                rec3 = record_review(
                    user_id=user_a_id,
                    item_id=item_id,
                    result="forgotten",
                    review_date=review_date_3,
                    database_path=path,
                )
                expected_date_3 = (today_d + timedelta(days=2 + DEFAULT_INTERVALS[0])).strftime("%Y-%m-%d")
                stage3_ok = (rec3["interval_stage"] == 0 and rec3["next_review_date"] == expected_date_3 and rec3["review_count"] == 3)

                transitions_valid = stage1_ok and stage2_ok and stage3_ok

                # 6. Review load capped at MAX_DUE_ITEMS_PER_LESSON (5)
                # Create 12 overdue items
                past_date = (today_d - timedelta(days=10)).strftime("%Y-%m-%d")
                for i in range(12):
                    add_review_item(
                        user_id=user_a_id,
                        class_id=class_a_id,
                        category="vocabulary",
                        prompt_text=f"Overdue vocabulary item #{i+1}",
                        target_answer=f"Overdue answer #{i+1}",
                        source_type="lesson",
                        custom_next_date=past_date,
                        database_path=path,
                    )

                due_items_capped = get_due_items(
                    user_id=user_a_id,
                    class_id=class_a_id,
                    today_date=today_str,
                    database_path=path,
                )
                total_due_count = count_due_items(user_id=user_a_id, class_id=class_a_id, today_date=today_str, database_path=path)
                capping_valid = (len(due_items_capped) == MAX_DUE_ITEMS_PER_LESSON and total_due_count >= 12)

                # 7. Retrieval warm-up block proposal for Next Lesson Planning
                block_proposal = propose_retrieval_block(
                    user_id=user_a_id,
                    class_id=class_a_id,
                    today_date=today_str,
                    database_path=path,
                )
                proposal_valid = (
                    block_proposal["has_due_items"]
                    and len(block_proposal["items"]) == MAX_DUE_ITEMS_PER_LESSON
                    and "Retrieval & Spaced-Review Warm-Up" in block_proposal["retrieval_block_text"]
                    and block_proposal["estimated_minutes"] > 0
                )

                # 8. State transitions: Snooze, Pause, Resume, Archive, Deleted Source, Manual Override
                # A. Snooze
                snz_res = snooze_item(user_id=user_a_id, item_id=item_id, days=3, database_path=path)
                snz_due = (today_d + timedelta(days=3)).strftime("%Y-%m-%d")
                snooze_ok = (snz_res["status"] == "snoozed" and snz_res["next_review_date"] == snz_due)

                # B. Pause & Resume
                pause_res = pause_item(user_id=user_a_id, item_id=item_id, database_path=path)
                pause_ok = (pause_res["status"] == "paused")

                resume_res = resume_item(user_id=user_a_id, item_id=item_id, database_path=path)
                resume_ok = (resume_res["status"] == "active" and resume_res["snoozed_until"] is None)

                # C. Archive
                arch_res = archive_item(user_id=user_a_id, item_id=item_id, database_path=path)
                archive_ok = (arch_res["status"] == "archived")

                # D. Manual override
                over_res = override_review_schedule(
                    user_id=user_a_id,
                    item_id=item_id,
                    next_review_date="2026-10-15",
                    stage=2,
                    notes="Teacher adjusted after diagnostic check",
                    database_path=path,
                )
                override_ok = (
                    over_res["next_review_date"] == "2026-10-15"
                    and over_res["interval_stage"] == 2
                    and "diagnostic check" in over_res["notes"]
                )

                # E. Deleted-source safety
                orphan_count = handle_deleted_source(source_type="lesson", source_id=101, database_path=path)
                with database.database_connection(path) as conn:
                    orphan_items = conn.execute(
                        "SELECT * FROM retrieval_review_items WHERE source_type = 'lesson' AND source_id IS NULL"
                    ).fetchall()
                    deleted_src_ok = (orphan_count >= 1 and len(orphan_items) >= orphan_count)

                # 9. Multi-tenant isolation
                cross_view = get_due_items(user_id=user_b_id, class_id=class_a_id, database_path=path)
                cross_access_blocked = (len(cross_view) == 0)

                cross_mod_res = record_review(
                    user_id=user_b_id,
                    item_id=item_id,
                    result="remembered",
                    database_path=path,
                )
                cross_mod_blocked = (cross_mod_res is None)

                cross_insert_blocked = False
                try:
                    add_review_item(
                        user_id=user_b_id,
                        class_id=class_a_id,
                        category="vocabulary",
                        prompt_text="Cross-tenant intrusion attempt",
                        target_answer="Blocked",
                        source_type="manual",
                        database_path=path,
                    )
                except (ValueError, Exception):
                    cross_insert_blocked = True

                multi_tenant_ok = cross_access_blocked and cross_mod_blocked and cross_insert_blocked

                # 10. Telegram keyboards bounded to <= 64 bytes
                sample_items = get_review_queue(user_id=user_a_id, class_id=class_a_id, limit=5, database_path=path)
                kbs = [
                    review_dashboard_keyboard(class_a_id, 1, 5, 20),
                    due_item_card_keyboard(item_id, class_a_id, 1, revealed=False),
                    due_item_card_keyboard(item_id, class_a_id, 1, revealed=True),
                    review_result_keyboard(item_id, class_a_id, 1, has_more_due=True),
                    snooze_picker_keyboard(item_id, class_a_id, 1),
                    confidence_picker_keyboard(item_id, class_a_id, 1),
                    queue_browser_keyboard(class_a_id, 1, sample_items, 0, 3, "active"),
                    queue_item_actions_keyboard(item_id, class_a_id, 1, "active"),
                    add_category_keyboard(class_a_id, 1),
                    add_confirm_keyboard(class_a_id, 1),
                    intervals_settings_keyboard(class_a_id, 1),
                ]
                kbs_valid = all(
                    len(btn.callback_data.encode("utf-8")) <= 64
                    for kb in kbs
                    for row in kb.inline_keyboard
                    for btn in row
                )

                checks = {
                    "schema_v20_deployed": schema_valid,
                    "all_six_categories_supported": all_cats_valid,
                    "all_four_source_types_supported": src_types_valid,
                    "configurable_intervals_schedule": intervals_default_ok and intervals_custom_ok,
                    "deterministic_due_dates_and_stage_transitions": transitions_valid,
                    "capped_retrieval_load_per_lesson": capping_valid,
                    "retrieval_block_proposal_generated": proposal_valid,
                    "snooze_state_transition_verified": snooze_ok,
                    "pause_and_resume_state_verified": pause_ok and resume_ok,
                    "archive_state_verified": archive_ok,
                    "manual_override_schedule_verified": override_ok,
                    "deleted_source_orphan_safety_verified": deleted_src_ok,
                    "multi_tenant_isolation_verified": multi_tenant_ok,
                    "telegram_keyboards_bounded_64_bytes": kbs_valid,
                }
                passed = all(checks.values())

                return {
                    "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "gate": "Day 20 — Add a Transparent Retrieval and Spaced-Review Queue",
                    "schema_version": 20,
                    "checks": checks,
                    "passed": passed,
                    "engineering_status": "PASS" if passed else "FAIL",
                    "details": {
                        "class_a_id": class_a_id,
                        "class_b_id": class_b_id,
                        "test_item_id": item_id,
                        "total_due_count": total_due_count,
                        "capped_retrieval_count": len(due_items_capped),
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
    parser = argparse.ArgumentParser(description="Evaluate TeacherOS Day 20 Retrieval & Spaced-Review Queue.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = evaluate_day20()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"DAY 20 ACCEPTANCE: {report['engineering_status']}")
    print(f"Report: {output_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
