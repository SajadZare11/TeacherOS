from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import database
from class_dashboard_service import class_dashboard_snapshot
from day11_migration import SCHEMA_VERSION
from keyboards import lesson_replace_keyboard, lesson_schedule_keyboard
from lesson_history_service import (
    cancel_planned_lesson,
    lesson_conversion_metrics,
    list_lesson_history,
    mark_lesson_taught,
    schedule_material_lesson,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _teacher(identifier: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier, username=f"day11_check_{identifier}",
        first_name="Day Eleven", last_name="Check", language_code="en",
    )


def _callbacks(markup: Any) -> list[str]:
    return [
        str(button.callback_data)
        for row in markup.inline_keyboard for button in row if button.callback_data
    ]


def evaluate_day11() -> dict[str, Any]:
    previous_path = database.DATABASE_PATH
    previous_classes_flag = os.environ.get("TEACHEROS_FEATURE_CLASSES")
    os.environ["TEACHEROS_FEATURE_CLASSES"] = "true"
    with tempfile.TemporaryDirectory(prefix="teacheros-day11-check-") as temp:
        path = Path(temp) / "teacheros.db"
        database.DATABASE_PATH = path
        try:
            database.initialize_database(path)
            owner = _teacher(999_110)
            other = _teacher(999_111)
            with database.database_connection(path) as connection:
                owner_id = database.ensure_database_user(connection, owner)
                database.ensure_database_user(connection, other)
                class_id = int(connection.execute(
                    "INSERT INTO classes (user_id, display_name, level, cadence) "
                    "VALUES (?, 'Day 11 acceptance', 'B1', 'weekly')", (owner_id,)
                ).lastrowid)
                empty_class_id = int(connection.execute(
                    "INSERT INTO classes (user_id, display_name) VALUES (?, 'Empty history')",
                    (owner_id,),
                ).lastrowid)
                objective_id = int(connection.execute(
                    "INSERT INTO class_objectives (class_id, user_id, objective, priority) "
                    "VALUES (?, ?, 'Use accurate requests', 60)", (class_id, owner_id),
                ).lastrowid)
                objective_before = dict(connection.execute(
                    "SELECT status, priority, updated_at FROM class_objectives WHERE id = ?",
                    (objective_id,),
                ).fetchone())

            def lesson(title: str) -> int:
                return database.save_generated_material(
                    telegram_user=owner, material_type="lesson", title=title,
                    content="B1 lesson with timing, materials, and instructions.",
                    level="B1", topic="Requests", class_id=class_id,
                    objective_ids=[objective_id],
                )

            taught_material = lesson("Taught acceptance lesson")
            taught_plan = schedule_material_lesson(
                telegram_user_id=owner.id, material_id=taught_material, date_choice="today"
            )
            duplicate_plan = schedule_material_lesson(
                telegram_user_id=owner.id, material_id=taught_material, date_choice="today"
            )
            taught_row, taught_changed = mark_lesson_taught(
                telegram_user_id=owner.id, lesson_id=int(taught_plan["lesson"]["id"])
            )
            _, taught_twice = mark_lesson_taught(
                telegram_user_id=owner.id, lesson_id=int(taught_plan["lesson"]["id"])
            )

            cancelled_material = lesson("Cancelled acceptance lesson")
            cancelled_plan = schedule_material_lesson(
                telegram_user_id=owner.id, material_id=cancelled_material, date_choice="later"
            )
            cancelled_row, cancelled_changed = cancel_planned_lesson(
                telegram_user_id=owner.id, lesson_id=int(cancelled_plan["lesson"]["id"])
            )
            _, cancelled_twice = cancel_planned_lesson(
                telegram_user_id=owner.id, lesson_id=int(cancelled_plan["lesson"]["id"])
            )

            generated_material = lesson("Generated only acceptance lesson")
            first_plan_material = lesson("Plan to replace")
            schedule_material_lesson(
                telegram_user_id=owner.id, material_id=first_plan_material,
                date_choice="next_class",
            )
            replacement_material = lesson("Replacement current plan")
            conflict = schedule_material_lesson(
                telegram_user_id=owner.id, material_id=replacement_material,
                date_choice="tomorrow",
            )
            replacement = schedule_material_lesson(
                telegram_user_id=owner.id, material_id=replacement_material,
                date_choice="tomorrow", replace=True,
            )

            history = list_lesson_history(
                telegram_user_id=owner.id, class_id=class_id
            )
            empty_history = list_lesson_history(
                telegram_user_id=owner.id, class_id=empty_class_id
            )
            cross_owner_history = list_lesson_history(
                telegram_user_id=other.id, class_id=class_id
            )
            dashboard = class_dashboard_snapshot(
                telegram_user_id=owner.id, class_id=class_id
            )
            metrics = lesson_conversion_metrics(
                telegram_user_id=owner.id, class_id=class_id
            )
            lifecycle_states = {str(item["lifecycle_state"]) for item in history}
            ids = [int(item["id"]) for item in history]
            linked_delete_blocked = not database.delete_user_material(
                telegram_user_id=owner.id, material_id=cancelled_material
            )
            resource_kept = database.get_user_material(
                telegram_user_id=owner.id, material_id=cancelled_material
            ) is not None
            cross_owner_plan = schedule_material_lesson(
                telegram_user_id=other.id, material_id=generated_material,
                date_choice="today",
            )

            immutable_link = False
            immutable_transition = False
            with database.database_connection(path) as connection:
                version = int(connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0])
                foreign_key_errors = len(connection.execute("PRAGMA foreign_key_check").fetchall())
                columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(class_lessons)")}
                objective_after = dict(connection.execute(
                    "SELECT status, priority, updated_at FROM class_objectives WHERE id = ?",
                    (objective_id,),
                ).fetchone())
                outcome_count = int(connection.execute("SELECT COUNT(*) FROM lesson_outcomes").fetchone()[0])
                review_count = int(connection.execute("SELECT COUNT(*) FROM class_action_items").fetchone()[0])
                try:
                    connection.execute(
                        "UPDATE class_lessons SET material_id = ? WHERE id = ?",
                        (replacement_material, int(taught_plan["lesson"]["id"])),
                    )
                except sqlite3.IntegrityError:
                    immutable_link = True
                try:
                    connection.execute(
                        "UPDATE class_lesson_transitions SET reason = 'rewritten' WHERE id = 1"
                    )
                except sqlite3.IntegrityError:
                    immutable_transition = True
        finally:
            database.DATABASE_PATH = previous_path
            if previous_classes_flag is None:
                os.environ.pop("TEACHEROS_FEATURE_CLASSES", None)
            else:
                os.environ["TEACHEROS_FEATURE_CLASSES"] = previous_classes_flag

    schedule_callbacks = _callbacks(lesson_schedule_keyboard(generated_material))
    replace_callbacks = _callbacks(lesson_replace_keyboard(generated_material, "td"))
    checks = {
        "schema_v11": version >= SCHEMA_VERSION and {
            "lifecycle_state", "lifecycle_version", "cancelled_at", "origin_key"
        } <= columns,
        "foreign_keys_clean": foreign_key_errors == 0,
        "all_four_states_present": lifecycle_states == {
            "generated", "planned", "taught", "cancelled"
        },
        "chronological_history": ids == sorted(ids),
        "empty_state": empty_history == [],
        "owner_isolation": cross_owner_history == [] and cross_owner_plan["status"] == "unavailable",
        "generated_not_progress": objective_before == objective_after and outcome_count == 0 and review_count == 0,
        "duplicate_plan_idempotent": taught_plan["status"] == "planned" and duplicate_plan["status"] == "already_planned",
        "mark_taught_idempotent": bool(taught_row and taught_changed and not taught_twice),
        "cancel_idempotent_auditable": bool(
            cancelled_row and cancelled_changed and not cancelled_twice
            and cancelled_row["lifecycle_state"] == "cancelled"
            and cancelled_row["taught_at"] is None
        ),
        "replace_preserves_resource": conflict["status"] == "conflict" and replacement["status"] == "replaced" and linked_delete_blocked and resource_kept,
        "dashboard_next_plan": bool(
            dashboard and dashboard["next_planned_lesson"]
            and dashboard["next_planned_lesson"]["material_id"] == replacement_material
        ),
        "immutable_audit_links": immutable_link and immutable_transition,
        "date_choices_complete": {
            value.rsplit("|", 1)[-1] for value in schedule_callbacks if "|pd|" in value
        } == {"td", "tm", "nc", "lt"},
        "callbacks_compact": all(
            len(value.encode("utf-8")) <= 64
            for value in schedule_callbacks + replace_callbacks
        ),
        "conversion_tracking": metrics == {
            "generated_to_planned": 4, "planned_to_taught": 1
        },
    }
    passed = all(checks.values())
    return {
        "day": 11,
        "schema_version": version,
        "engineering_status": "PASS" if passed else "FAIL",
        "passed": passed,
        "checks": checks,
        "measurement": {
            "generated_to_planned": metrics["generated_to_planned"],
            "planned_to_taught": metrics["planned_to_taught"],
            "status": "TRACKING_ACTIVE",
            "interpretation": "Conversion is a workflow signal; no activity is inferred.",
        },
        "history_fixture": {
            "record_count": len(history),
            "states": sorted(lifecycle_states),
            "raw_material_content_in_report": False,
        },
        "privacy": {"raw_prompts_or_outputs_in_report": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TeacherOS Day 11 acceptance.")
    parser.add_argument(
        "--output", type=Path,
        default=PROJECT_ROOT / "outputs" / "day11" / "acceptance_report.json",
    )
    args = parser.parse_args()
    report = evaluate_day11()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"DAY 11 ENGINEERING: {report['engineering_status']}")
    print(
        "Conversions: "
        f"generated->planned {report['measurement']['generated_to_planned']}, "
        f"planned->taught {report['measurement']['planned_to_taught']}"
    )
    print(f"Report: {output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
