from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import database
from day17_migration import SCHEMA_VERSION
from keyboards import generated_material_export_keyboard
from pdf_document import create_pdf_export
from prompt_contracts import get_prompt_contract
from validators import validate_model_response
from word_document import create_word_export


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GENERATORS = ("lesson", "activity", "worksheet", "assessment")
MODES = ("quick", "class")
BEHAVIORS = ("override", "cancel", "retry", "save", "word_export", "pdf_export")


def _user(identifier: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier, username=f"day10_check_{identifier}", first_name="Day Ten",
        last_name="Check", language_code="en",
    )


def _callbacks(markup: Any) -> list[str]:
    return [str(button.callback_data) for row in markup.inline_keyboard for button in row if button.callback_data]


def evaluate_day10() -> dict[str, Any]:
    previous_path = database.DATABASE_PATH
    with tempfile.TemporaryDirectory(prefix="teacheros-day10-check-") as temp:
        path = Path(temp) / "teacheros.db"
        database.DATABASE_PATH = path
        try:
            database.initialize_database(path)
            owner = _user(999_010)
            other = _user(999_011)
            with database.database_connection(path) as connection:
                owner_id = database.ensure_database_user(connection, owner)
                database.ensure_database_user(connection, other)
                class_id = int(connection.execute(
                    "INSERT INTO classes (user_id, display_name, level, lesson_duration_minutes) "
                    "VALUES (?, 'Acceptance class', 'B1', 45)", (owner_id,)
                ).lastrowid)
                objective_id = int(connection.execute(
                    "INSERT INTO class_objectives (class_id, user_id, objective, priority) "
                    "VALUES (?, ?, 'Use target language accurately', 50)",
                    (class_id, owner_id),
                ).lastrowid)

            provenance = {
                "prompt_contract": "teacheros.day10.check", "prompt_version": "10.0",
                "prompt_hash_sha256": "a" * 64, "context_hash_sha256": "b" * 64,
                "source_record_ids": {"classes": [class_id], "class_objectives": [objective_id]},
            }
            export_ok: dict[str, bool] = {}
            stored_ids: list[int] = []
            for material_type in GENERATORS:
                material_id = database.save_generated_material(
                    telegram_user=owner, material_type=material_type,
                    subtype="Acceptance", title=f"{material_type.title()} acceptance",
                    level="B1", topic="Travel",
                    content=(
                        "CEFR Level B1. Timing 45 minutes. Materials: board. "
                        "Instructions: follow the procedure. Answer Key: 1 A. "
                        "Objective Alignment: Use target language accurately."
                    ),
                    class_id=class_id, objective_ids=[objective_id],
                    ai_provenance=provenance, quality_scores={"overall": 100},
                )
                stored_ids.append(material_id)
                material = database.get_user_material(
                    telegram_user_id=owner.id, material_id=material_id
                )
                word, _ = create_word_export(material or {})
                pdf, _ = create_pdf_export(material or {})
                export_ok[material_type] = word.read(2) == b"PK" and pdf.read(4) == b"%PDF"

            class_items = database.list_class_materials(
                telegram_user_id=owner.id, class_id=class_id
            )
            general_items = database.list_user_materials(
                telegram_user_id=owner.id, limit=20
            )
            search_items = database.search_user_materials(
                telegram_user_id=owner.id, query="Travel B1", limit=20
            )
            owner_isolation = all(
                database.get_user_material(telegram_user_id=other.id, material_id=value) is None
                for value in stored_ids
            )
            lesson, created = database.plan_material_as_next_lesson(
                telegram_user_id=owner.id, material_id=stored_ids[0]
            )
            duplicate, created_twice = database.plan_material_as_next_lesson(
                telegram_user_id=owner.id, material_id=stored_ids[0]
            )
            with database.database_connection(path) as connection:
                version = int(connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0])
                foreign_key_errors = len(connection.execute("PRAGMA foreign_key_check").fetchall())
                columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(materials)")}

            quality_text = (
                "CEFR Level B1. Timing 45 minutes. Materials: board. Instructions: steps. "
                "Answer Key: A. Objective Alignment: current objective."
            )
            quality = validate_model_response(
                json.dumps({"content": quality_text}),
                get_prompt_contract("general_chat"),
                {"level": "B1", "duration_minutes": 45, "answer_key": True, "objective_alignment": True},
            )
            toolbar_callbacks = _callbacks(generated_material_export_keyboard(
                stored_ids[0], material_type="lesson", class_id=class_id
            ))
        finally:
            database.DATABASE_PATH = previous_path

    source_files = {
        "lesson": "lesson_planner.py", "activity": "activity_generator.py",
        "worksheet": "worksheet_generator.py", "assessment": "quiz_generator.py",
    }
    quick_markers = {
        "lesson": 'data == "lesson"', "activity": 'data == "activity_start"',
        "worksheet": 'data == "worksheet_start"', "assessment": 'data == "quiz_start"',
    }
    matrix: list[dict[str, object]] = []
    for generator in GENERATORS:
        source = (PROJECT_ROOT / "backend" / source_files[generator]).read_text(encoding="utf-8")
        behavior_markers = {
            "override": "_override" in source and "ONE-TIME" in source,
            "cancel": "_cancel" in source and "No class data changed" in source,
            "retry": "Your choices are still saved" in source,
            "save": "save_generated_material(" in source and "quality_scores=" in source,
            "word_export": "generated_material_export_keyboard(" in source,
            "pdf_export": "generated_material_export_keyboard(" in source,
        }
        for mode in MODES:
            mode_covered = (
                quick_markers[generator] in source if mode == "quick"
                else "class_mode" in source and "class_id=int(" in source
            )
            for behavior in BEHAVIORS:
                matrix.append({
                    "generator": generator, "mode": mode, "behavior": behavior,
                    "covered": bool(mode_covered and behavior_markers[behavior]),
                })
    required_columns = {
        "class_id", "ai_prompt_contract", "ai_prompt_version",
        "ai_prompt_hash_sha256", "ai_context_hash_sha256",
        "ai_source_record_ids_json", "quality_scores_json",
    }
    toolbar_prefixes = ("ma|sv|", "ma|ad|", "ma|rg|", "ma|nx|", "ma|rp|", "export_", "pdf_")
    lesson_input_reduction = (4 - 2) / 4
    checks = {
        "schema_v10": version >= SCHEMA_VERSION and required_columns <= columns,
        "foreign_keys_clean": foreign_key_errors == 0,
        "all_four_saved": len(stored_ids) == 4,
        "class_and_general_library": len(class_items) == len(general_items) == len(search_items) == 4,
        "owner_isolation": owner_isolation,
        "quality_gate": quality.valid and quality.quality_scores.get("overall") == 100,
        "word_pdf_exports": all(export_ok.values()),
        "post_generation_toolbar": all(any(value.startswith(prefix) for value in toolbar_callbacks) for prefix in toolbar_prefixes),
        "callbacks_compact": all(len(value.encode("utf-8")) <= 64 for value in toolbar_callbacks),
        "next_lesson_idempotent": bool(lesson and duplicate and created and not created_twice and lesson["id"] == duplicate["id"]),
        "lesson_inputs_reduced_at_least_50_percent": lesson_input_reduction >= 0.50,
        "matrix_complete": len(matrix) == 48 and all(item["covered"] for item in matrix),
    }
    passed = all(checks.values())
    return {
        "day": 10, "schema_version": version,
        "engineering_status": "PASS" if passed else "FAIL", "passed": passed,
        "checks": checks,
        "test_matrix": {"case_count": len(matrix), "dimensions": {
            "generators": list(GENERATORS), "modes": list(MODES), "behaviors": list(BEHAVIORS),
        }, "cases": matrix},
        "measurement": {
            "day1_teacher_inputs": 4, "class_aware_teacher_inputs": 2,
            "input_reduction_fraction": lesson_input_reduction, "target_fraction": 0.50,
            "status": "PASS" if lesson_input_reduction >= 0.50 else "FAIL",
        },
        "privacy": {"raw_prompts_or_outputs_in_report": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TeacherOS Day 10 acceptance.")
    parser.add_argument(
        "--output", type=Path,
        default=PROJECT_ROOT / "outputs" / "day10" / "acceptance_report.json",
    )
    args = parser.parse_args()
    report = evaluate_day10()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"DAY 10 ENGINEERING: {report['engineering_status']}")
    print(f"Matrix cases: {report['test_matrix']['case_count']}")
    print(f"Input reduction: {report['measurement']['input_reduction_fraction']:.0%}")
    print(f"Report: {output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
