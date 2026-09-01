from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import class_service
import database
from class_dashboard_keyboards import (
    outcome_completion_keyboard,
    outcome_difficulty_keyboard,
    outcome_reminder_keyboard,
    outcome_result_keyboard,
)
from class_dashboard_service import class_dashboard_snapshot
from day12_migration import SCHEMA_VERSION
from feature_flags import FEATURE_ENV_VARS
from lesson_history_service import mark_lesson_taught, schedule_material_lesson
from outcome_checkin_service import (
    claim_due_outcome_reminders,
    get_lesson_outcome,
    list_outcome_lessons,
    outcome_recording_metrics,
    reminder_due_utc,
    schedule_outcome_reminder,
    save_outcome_facts,
    update_outcome_note,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "day12" / "acceptance_report.json"


def _teacher(identifier: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier, username=f"day12_acceptance_{identifier}",
        first_name="Acceptance", last_name="Teacher", language_code="en",
    )


def _callbacks(markup: object) -> list[str]:
    return [
        str(button.callback_data)
        for row in markup.inline_keyboard for button in row if button.callback_data
    ]


def evaluate_day12() -> dict[str, Any]:
    previous_flags = {name: os.environ.get(name) for name in FEATURE_ENV_VARS.values()}
    for name in FEATURE_ENV_VARS.values():
        os.environ[name] = "false"
    os.environ[FEATURE_ENV_VARS["classes"]] = "true"
    os.environ[FEATURE_ENV_VARS["continuity"]] = "true"
    try:
        with tempfile.TemporaryDirectory(prefix="teacheros-day12-acceptance-") as temp_dir:
            path = Path(temp_dir) / "teacheros.db"
            original_path = database.DATABASE_PATH
            database.DATABASE_PATH = path
            try:
                owner = _teacher(120_001)
                other = _teacher(120_002)
                class_record = class_service.create_class(
                    telegram_user=owner, display_name="Day 12 acceptance",
                    level="B1", cadence="weekly", goal="Fast truthful outcomes",
                )
                assert class_record is not None
                with database.database_connection(path) as connection:
                    database.ensure_database_user(connection, other)

                def taught_lesson(title: str) -> dict[str, Any]:
                    material_id = database.save_generated_material(
                        telegram_user=owner, material_type="lesson", title=title,
                        content="Acceptance-only fixture", class_id=int(class_record["id"]),
                    )
                    planned = schedule_material_lesson(
                        telegram_user_id=owner.id, material_id=material_id, date_choice="today"
                    )["lesson"]
                    taught, changed = mark_lesson_taught(
                        telegram_user_id=owner.id, lesson_id=int(planned["id"])
                    )
                    assert taught is not None and changed
                    return taught

                lessons = [taught_lesson(f"Outcome fixture {index}") for index in range(1, 6)]
                first, first_changed = save_outcome_facts(
                    telegram_user_id=owner.id, lesson_id=int(lessons[0]["id"]),
                    result="achieved", difficulty_categories=["none"],
                    completion_status="completed",
                )
                duplicate, duplicate_changed = save_outcome_facts(
                    telegram_user_id=owner.id, lesson_id=int(lessons[0]["id"]),
                    result="achieved", difficulty_categories=["none"],
                    completion_status="completed",
                )
                corrected, corrected_changed = save_outcome_facts(
                    telegram_user_id=owner.id, lesson_id=int(lessons[0]["id"]),
                    result="partly_achieved", difficulty_categories=["language", "pace"],
                    completion_status="partly_completed",
                )
                note_added, note_changed = update_outcome_note(
                    telegram_user_id=owner.id, lesson_id=int(lessons[0]["id"]),
                    note="Acceptance fixture note",
                )
                note_cleared, note_cleared_changed = update_outcome_note(
                    telegram_user_id=owner.id, lesson_id=int(lessons[0]["id"]), note=None
                )
                save_outcome_facts(
                    telegram_user_id=owner.id, lesson_id=int(lessons[1]["id"]),
                    result="needs_reteaching", difficulty_categories=["instructions"],
                    completion_status="not_completed",
                )
                save_outcome_facts(
                    telegram_user_id=owner.id, lesson_id=int(lessons[2]["id"]),
                    result="achieved", difficulty_categories=["none"],
                    completion_status="completed",
                )
                cross_owner, cross_changed = save_outcome_facts(
                    telegram_user_id=other.id, lesson_id=int(lessons[4]["id"]),
                    result="achieved", difficulty_categories=["none"],
                    completion_status="completed",
                )

                fixed_now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
                reminder = schedule_outcome_reminder(
                    telegram_user_id=owner.id, lesson_id=int(lessons[3]["id"]),
                    choice="local_18", now_utc=fixed_now,
                )
                reminder_duplicate = schedule_outcome_reminder(
                    telegram_user_id=owner.id, lesson_id=int(lessons[3]["id"]),
                    choice="local_18", now_utc=fixed_now,
                )
                due = claim_due_outcome_reminders(
                    now_utc=fixed_now + timedelta(hours=4), database_path=path
                )
                due_again = claim_due_outcome_reminders(
                    now_utc=fixed_now + timedelta(hours=5), database_path=path
                )
                metrics = outcome_recording_metrics(
                    telegram_user_id=owner.id, class_id=int(class_record["id"]),
                    database_path=path,
                )
                snapshot = class_dashboard_snapshot(
                    telegram_user_id=owner.id, class_id=int(class_record["id"]),
                    database_path=path,
                )
                picker = list_outcome_lessons(
                    telegram_user_id=owner.id, class_id=int(class_record["id"]),
                    database_path=path,
                )
                first_outcome_available = get_lesson_outcome(
                    telegram_user_id=owner.id, lesson_id=int(lessons[0]["id"]),
                    database_path=path,
                ) is not None
                markups = (
                    outcome_result_keyboard(int(lessons[0]["id"]), int(class_record["revision"])),
                    outcome_difficulty_keyboard(int(lessons[0]["id"]), "a", 63, int(class_record["revision"])),
                    outcome_completion_keyboard(int(lessons[0]["id"]), "p", 63, int(class_record["revision"])),
                    outcome_reminder_keyboard(int(lessons[3]["id"]), int(class_record["revision"])),
                )
                callback_values = [value for markup in markups for value in _callbacks(markup)]
                normal_path_actions = {
                    "ores": any("|ores|" in value for value in _callbacks(markups[0])),
                    "odone": any("|odone|" in value for value in _callbacks(markups[1])),
                    "ocomp": any("|ocomp|" in value for value in _callbacks(markups[2])),
                }

                with database.database_connection(path) as connection:
                    version = int(connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0])
                    foreign_key_errors = len(connection.execute("PRAGMA foreign_key_check").fetchall())
                    outcome_count = int(connection.execute("SELECT COUNT(*) FROM lesson_outcomes").fetchone()[0])
                    revision_count = int(connection.execute("SELECT COUNT(*) FROM lesson_outcome_fact_revisions").fetchone()[0])
                    suggestion_count = int(connection.execute("SELECT COUNT(*) FROM lesson_outcome_ai_suggestions").fetchone()[0])
                    product_event_count = int(connection.execute(
                        "SELECT COUNT(*) FROM product_events WHERE event_name = 'outcome_saved'"
                    ).fetchone()[0])
            finally:
                database.DATABASE_PATH = original_path
    finally:
        for name, value in previous_flags.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    checks = {
        "schema_v12_and_foreign_keys": version >= SCHEMA_VERSION and foreign_key_errors == 0,
        "normal_path_saves_without_note": bool(
            first and first_changed and first["notes"] is None
            and first["difficulty_categories"] == ["none"]
        ),
        "duplicate_prevention": bool(
            duplicate and first and duplicate["id"] == first["id"]
            and not duplicate_changed and outcome_count == 3
        ),
        "correction_keeps_one_outcome_and_revision_history": bool(
            corrected and corrected_changed and first
            and corrected["id"] == first["id"] and corrected["facts_version"] == 2
            and revision_count == 6
        ),
        "optional_note_add_and_clear": bool(
            note_added and note_changed and note_cleared and note_cleared_changed
            and note_cleared["notes"] is None
        ),
        "cross_owner_fails_closed": cross_owner is None and not cross_changed,
        "one_shot_local_reminder": bool(
            reminder["status"] == "scheduled"
            and reminder_duplicate["status"] == "already_scheduled"
            and len(due) == 1 and not due_again
            and reminder_due_utc("local_18", now_utc=fixed_now)
            == datetime(2026, 8, 31, 14, 30, tzinfo=timezone.utc)
        ),
        "dashboard_and_correction_picker_update": bool(
            snapshot and snapshot["outcome_recording_rate_percent"] == 60
            and len(picker) == 5 and sum(item["outcome_id"] is not None for item in picker) == 3
            and first_outcome_available
        ),
        "facts_separate_from_ai_suggestions": suggestion_count == 0,
        "operational_measurement_is_content_free": product_event_count == 4,
        "callbacks_compact": bool(callback_values) and all(
            len(value.encode("utf-8")) <= 64 for value in callback_values
        ),
        "three_fact_taps_structurally_defined": all(normal_path_actions.values()),
    }
    passed = all(checks.values())
    return {
        "day": 12,
        "engineering_status": "PASS" if passed else "FAIL",
        "passed": passed,
        "checks": checks,
        "measurement": {
            "fixture_taught_lessons": metrics["taught"],
            "fixture_outcomes_recorded": metrics["outcomes_recorded"],
            "fixture_recording_rate_percent": metrics["recording_rate_percent"],
            "pilot_target_percent": 60,
            "pilot_observed_rate_percent": None,
            "pilot_measurement_status": "BLOCKED_NOT_FABRICATED",
        },
        "external_evidence": {
            "three_tap_under_30_seconds_observed_test": "BLOCKED_NOT_FABRICATED",
            "reason": "Requires observed testing with target teachers; engineering tests cannot substitute.",
        },
        "privacy": "Report contains aggregate fixture counts and booleans only; no teacher note or user identifier.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check TeacherOS Day 12 acceptance.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = evaluate_day12()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"DAY 12 ENGINEERING: {report['engineering_status']}")
    print(
        "Fixture outcome capture: "
        f"{report['measurement']['fixture_recording_rate_percent']}% "
        "(pilot evidence remains blocked, not fabricated)"
    )
    print(f"Report: {args.report}")
    if report["engineering_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
