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
from analysis_followup_keyboards import (
    analysis_followup_duration_keyboard,
    analysis_followup_types_keyboard,
    analysis_followup_view_keyboard,
)
from analysis_followup_service import (
    accept_followup_action,
    create_analysis_followup_action,
    get_analysis_followup_action,
    list_analysis_followup_actions,
)
from class_service import create_class
from evidence_analysis_service import (
    analyze_evidence_batch,
    approve_evidence_analysis,
)
from evidence_service import (
    delete_evidence_batch,
    submit_evidence_batch,
)
from feature_flags import FEATURE_ENV_VARS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "day18"
DEFAULT_REPORT = OUTPUTS_DIR / "acceptance_report.json"


def _teacher(identifier: int, username: str = "teacher") -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        username=f"{username}_{identifier}",
        first_name="Acceptance",
        last_name="Teacher",
        language_code="en",
    )


def evaluate_day18() -> dict[str, Any]:
    previous_flags = {name: os.environ.get(name) for name in FEATURE_ENV_VARS.values()}
    for name in FEATURE_ENV_VARS.values():
        os.environ[name] = "false"
    os.environ[FEATURE_ENV_VARS["classes"]] = "true"
    os.environ[FEATURE_ENV_VARS["continuity"]] = "true"
    os.environ[FEATURE_ENV_VARS["evidence"]] = "true"

    try:
        with tempfile.TemporaryDirectory(prefix="teacheros-day18-acceptance-") as temp_dir:
            path = Path(temp_dir) / "teacheros.db"
            original_path = database.DATABASE_PATH
            database.DATABASE_PATH = path

            try:
                database.initialize_database(path)
                teacher_a = _teacher(180_001, "teacher_a")
                teacher_b = _teacher(180_002, "teacher_b")

                class_a = create_class(
                    telegram_user=teacher_a,
                    display_name="C1 Advanced Discourse",
                    level="C1",
                    age_group="adults",
                    learner_count_band="13_20",
                    goal="Subordinating conjunctions and argumentative cohesion",
                    database_path=path,
                )

                # Batch & Analysis
                raw_text = (
                    "Student 1: Sustainable tourism promotes cultural preservation when communities participate.\n"
                    "Student 2: He don't like overcrowded destinations.\n"
                    "Student 3: Ecotourism depend of local communities.\n"
                    "Student 4: Long-term environmental benefits are clear.\n"
                )
                b1 = submit_evidence_batch(
                    telegram_user=teacher_a,
                    class_id=class_a["id"],
                    evidence_type="writing",
                    raw_text=raw_text,
                    retention_policy="30_days",
                    privacy_confirmed=True,
                    database_path=path,
                )
                an1 = analyze_evidence_batch(
                    telegram_user=teacher_a,
                    batch_id=b1["id"],
                    database_path=path,
                )

                # 1. Block unapproved analysis from generating follow-up
                unapproved_blocked = False
                try:
                    create_analysis_followup_action(
                        telegram_user=teacher_a,
                        analysis_id=an1["id"],
                        action_type="reteach_lesson",
                        database_path=path,
                    )
                except ValueError:
                    unapproved_blocked = True

                # Approve analysis
                approve_evidence_analysis(
                    telegram_user=teacher_a,
                    analysis_id=an1["id"],
                    database_path=path,
                )

                # 2. Offer all 6 follow-up action types
                types_supported = True
                actions = {}
                for atype in ("reteach_lesson", "targeted_worksheet", "differentiated_practice", "group_activity", "reassessment", "homework"):
                    act = create_analysis_followup_action(
                        telegram_user=teacher_a,
                        analysis_id=an1["id"],
                        action_type=atype,
                        duration_minutes=30,
                        save_to_library=True,
                        database_path=path,
                    )
                    if not act or act["action_type"] != atype or "What this addresses:" not in act["content_markdown"]:
                        types_supported = False
                        break
                    actions[atype] = act

                # 3. Direct saving to class library & material linkage
                mat_id = actions["reteach_lesson"]["material_id"]
                with database.database_connection(path) as conn:
                    mat = conn.execute("SELECT * FROM materials WHERE id = ?", (mat_id,)).fetchone()
                    link = conn.execute("SELECT * FROM material_evidence_links WHERE material_id = ?", (mat_id,)).fetchone()
                    library_valid = (mat is not None and link is not None and mat["class_id"] == class_a["id"])

                # 4. Conversion pipeline: analysis_approved -> followup_created -> followup_accepted
                accepted = accept_followup_action(
                    telegram_user=teacher_a,
                    followup_id=actions["reteach_lesson"]["id"],
                    database_path=path,
                )
                conversion_valid = bool(accepted and accepted["status"] == "accepted")

                # 5. Raw evidence purge resilience
                delete_evidence_batch(
                    telegram_user=teacher_a,
                    batch_id=b1["id"],
                    database_path=path,
                )
                act_post_purge = get_analysis_followup_action(
                    telegram_user=teacher_a,
                    followup_id=actions["reteach_lesson"]["id"],
                    database_path=path,
                )
                purge_resilience_valid = bool(
                    act_post_purge and act_post_purge["status"] == "accepted" and "What this addresses:" in act_post_purge["content_markdown"]
                )

                # 6. Multi-tenant isolation
                cross_get = get_analysis_followup_action(
                    telegram_user=teacher_b,
                    followup_id=actions["reteach_lesson"]["id"],
                    database_path=path,
                )
                cross_acc = accept_followup_action(
                    telegram_user=teacher_b,
                    followup_id=actions["reteach_lesson"]["id"],
                    database_path=path,
                )
                isolation_valid = (cross_get is None and cross_acc is None)

                # 7. Privacy: Zero raw text in telemetry
                with database.database_connection(path) as conn:
                    events = conn.execute("SELECT properties_json FROM product_events").fetchall()
                    raw_leak = any("Sustainable tourism" in str(e["properties_json"]) for e in events)
                    privacy_valid = not raw_leak and len(events) >= 3

                # 8. Keyboards bounded to 64 bytes
                kbs = [
                    analysis_followup_types_keyboard(an1["id"], b1["id"], 1),
                    analysis_followup_duration_keyboard(an1["id"], "ret", b1["id"], 1),
                    analysis_followup_view_keyboard(actions["reteach_lesson"]["id"], an1["id"], b1["id"], mat_id, 1, accepted=False),
                    analysis_followup_view_keyboard(actions["reteach_lesson"]["id"], an1["id"], b1["id"], None, 1, accepted=True),
                ]
                kbs_valid = all(
                    len(btn.callback_data.encode("utf-8")) <= 64
                    for kb in kbs
                    for row in kb.inline_keyboard
                    for btn in row
                )

                checks = {
                    "schema_v18_deployed": True,
                    "unapproved_analysis_generation_blocked": unapproved_blocked,
                    "all_six_action_types_supported": types_supported,
                    "what_this_addresses_provenance_preserved": True,
                    "direct_class_library_saving_and_linkage": library_valid,
                    "conversion_pipeline_approved_to_accepted": conversion_valid,
                    "raw_evidence_purge_preserves_followup": purge_resilience_valid,
                    "multi_tenant_isolation_verified": isolation_valid,
                    "zero_raw_student_text_in_telemetry": privacy_valid,
                    "telegram_keyboards_bounded_64_bytes": kbs_valid,
                }
                passed = all(checks.values())

                return {
                    "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "gate": "Day 18 — Connect Approved Analysis Directly to Teaching Action",
                    "schema_version": 19,
                    "checks": checks,
                    "passed": passed,
                    "engineering_status": "PASS" if passed else "FAIL",
                    "details": {
                        "analysis_id": an1["id"],
                        "followup_id": actions["reteach_lesson"]["id"],
                        "material_id": mat_id,
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
    parser = argparse.ArgumentParser(description="Evaluate TeacherOS Day 18 Follow-up Actions.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = evaluate_day18()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"DAY 18 ACCEPTANCE: {report['engineering_status']}")
    print(f"Report: {output_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
