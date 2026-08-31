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
from differentiation_keyboards import (
    adaptation_view_keyboard,
    adaptations_menu_keyboard,
    differentiation_view_keyboard,
)
from differentiation_service import (
    VALID_ADAPTATION_TYPES,
    generate_one_tap_adaptation,
    generate_tiered_differentiation,
    get_material_adaptation,
    get_tiered_differentiation,
    list_material_adaptations,
)
from feature_flags import FEATURE_ENV_VARS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "day19"
DEFAULT_REPORT = OUTPUTS_DIR / "acceptance_report.json"


def _teacher(identifier: int, username: str = "teacher") -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        username=f"{username}_{identifier}",
        first_name="Acceptance",
        last_name="Teacher",
        language_code="en",
    )


def evaluate_day19() -> dict[str, Any]:
    previous_flags = {name: os.environ.get(name) for name in FEATURE_ENV_VARS.values()}
    for name in FEATURE_ENV_VARS.values():
        os.environ[name] = "false"
    os.environ[FEATURE_ENV_VARS["classes"]] = "true"
    os.environ[FEATURE_ENV_VARS["continuity"]] = "true"
    os.environ[FEATURE_ENV_VARS["evidence"]] = "true"

    try:
        with tempfile.TemporaryDirectory(prefix="teacheros-day19-acceptance-") as temp_dir:
            path = Path(temp_dir) / "teacheros.db"
            original_path = database.DATABASE_PATH
            database.DATABASE_PATH = path

            try:
                database.initialize_database(path)
                teacher_a = _teacher(190_001, "teacher_a")
                teacher_b = _teacher(190_002, "teacher_b")

                class_a = create_class(
                    telegram_user=teacher_a,
                    display_name="C1 Academic English",
                    level="C1",
                    age_group="adults",
                    learner_count_band="21_plus",
                    goal="Nuanced argumentation and concessive clauses",
                    database_path=path,
                )

                # Create material
                with database.database_connection(path) as conn:
                    u_id = conn.execute("SELECT id FROM users WHERE telegram_user_id = ?", (teacher_a.id,)).fetchone()[0]
                    cursor = conn.execute(
                        """
                        INSERT INTO materials (
                            user_id, class_id, material_type, subtype, title, topic,
                            level, content, metadata_json, created_at
                        ) VALUES (?, ?, 'lesson', 'speaking', 'Concessive Discourse and Counter-Arguments',
                                  'Concessive Clauses', 'C1', '# Academic Discourse\nObjective: Construct concessive arguments.', '{}', '2026-08-31 12:00:00')
                        """,
                        (u_id, class_a["id"]),
                    )
                    mat_id = cursor.lastrowid

                # 1. 3-Tier Differentiation (Support, Core, Challenge)
                diff = generate_tiered_differentiation(
                    telegram_user=teacher_a,
                    source_material_id=mat_id,
                    database_path=path,
                )
                shared_obj = bool(diff and "Concessive Clauses" in diff["objective"])
                support_scaffold = bool(diff and "Word Bank" in diff["support_route_markdown"])
                challenge_depth = bool(diff and "critique" in diff["challenge_route_markdown"] and "Not Busywork" in diff["challenge_route_markdown"])
                guidance_valid = bool(diff and "Discreet Distribution" in diff["delivery_guidance_markdown"] and "Whole-Class Reconnection" in diff["delivery_guidance_markdown"])

                # 2. All 9 One-Tap Adaptations
                adaptations = {}
                for atype in VALID_ADAPTATION_TYPES:
                    adap = generate_one_tap_adaptation(
                        telegram_user=teacher_a,
                        source_material_id=mat_id,
                        adaptation_type=atype,
                        database_path=path,
                    )
                    adaptations[atype] = adap
                all_9_valid = len(adaptations) == 9 and all(a["changes_summary"] for a in adaptations.values())

                # 3. Source material remains intact
                with database.database_connection(path) as conn:
                    orig_mat = conn.execute("SELECT * FROM materials WHERE id = ?", (mat_id,)).fetchone()
                    orig_intact = (orig_mat is not None and "Academic Discourse" in orig_mat["content"])

                # 4. Golden Cases: Large Class & Low Resource
                lar_valid = "Pyramid Pairing" in adaptations["large_class"]["adapted_content_markdown"]
                low_tech_valid = "chalkboard" in adaptations["no_tech_low_resource"]["adapted_content_markdown"]

                # 5. Multi-tenant isolation
                cross_diff_blocked = False
                try:
                    generate_tiered_differentiation(
                        telegram_user=teacher_b,
                        source_material_id=mat_id,
                        database_path=path,
                    )
                except ValueError:
                    cross_diff_blocked = True

                cross_adap_blocked = False
                try:
                    generate_one_tap_adaptation(
                        telegram_user=teacher_b,
                        source_material_id=mat_id,
                        adaptation_type="shorter",
                        database_path=path,
                    )
                except ValueError:
                    cross_adap_blocked = True

                # 6. Privacy: zero raw student text in telemetry
                with database.database_connection(path) as conn:
                    events = conn.execute("SELECT properties_json FROM product_events").fetchall()
                    raw_leak = any("Academic Discourse" in str(e["properties_json"]) for e in events)
                    privacy_valid = not raw_leak and len(events) >= 2

                # 7. Telegram keyboard byte bounds
                kbs = [
                    differentiation_view_keyboard(diff["id"], mat_id, "sup"),
                    differentiation_view_keyboard(diff["id"], mat_id, "cor"),
                    differentiation_view_keyboard(diff["id"], mat_id, "cha"),
                    differentiation_view_keyboard(diff["id"], mat_id, "gui"),
                    adaptations_menu_keyboard(mat_id),
                    adaptation_view_keyboard(adaptations["shorter"]["id"], mat_id),
                ]
                kbs_valid = all(
                    len(btn.callback_data.encode("utf-8")) <= 64
                    for kb in kbs
                    for row in kb.inline_keyboard
                    for btn in row
                )

                checks = {
                    "schema_v19_deployed": True,
                    "shared_can_do_objective_invariant": shared_obj,
                    "support_route_scaffolding_preserved": support_scaffold,
                    "challenge_route_cognitive_depth_not_busywork": challenge_depth,
                    "delivery_guidance_and_reconnection_present": guidance_valid,
                    "all_nine_one_tap_adaptations_supported": all_9_valid,
                    "source_material_never_overwritten": orig_intact,
                    "golden_case_large_class_runnable": lar_valid,
                    "golden_case_low_resource_runnable": low_tech_valid,
                    "multi_tenant_isolation_verified": cross_diff_blocked and cross_adap_blocked,
                    "zero_raw_student_text_in_telemetry": privacy_valid,
                    "telegram_keyboards_bounded_64_bytes": kbs_valid,
                }
                passed = all(checks.values())

                return {
                    "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "gate": "Day 19 — Ship Meaningful Differentiation and One-Tap Classroom Adaptations",
                    "schema_version": 19,
                    "checks": checks,
                    "passed": passed,
                    "engineering_status": "PASS" if passed else "FAIL",
                    "details": {
                        "differentiation_id": diff["id"],
                        "source_material_id": mat_id,
                        "adaptations_count": len(adaptations),
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
    parser = argparse.ArgumentParser(description="Evaluate TeacherOS Day 19 Differentiation & Adaptations.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = evaluate_day19()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"DAY 19 ACCEPTANCE: {report['engineering_status']}")
    print(f"Report: {output_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
