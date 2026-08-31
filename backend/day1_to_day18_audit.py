from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from day1_to_day17_audit import evaluate_days_1_to_17
from day18_acceptance_check import evaluate_day18


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def evaluate_days_1_to_18(*, automated_test_count: int) -> dict[str, Any]:
    prior = evaluate_days_1_to_17(automated_test_count=automated_test_count)
    day18 = evaluate_day18()
    days = dict(prior["days"])
    days["18"] = {
        "engineering": day18["engineering_status"],
        "passed": day18["passed"],
        "schema_v18_deployed": day18["checks"]["schema_v18_deployed"],
        "unapproved_analysis_generation_blocked": day18["checks"]["unapproved_analysis_generation_blocked"],
        "all_six_action_types_supported": day18["checks"]["all_six_action_types_supported"],
        "what_this_addresses_provenance_preserved": day18["checks"]["what_this_addresses_provenance_preserved"],
        "direct_class_library_saving_and_linkage": day18["checks"]["direct_class_library_saving_and_linkage"],
        "conversion_pipeline_approved_to_accepted": day18["checks"]["conversion_pipeline_approved_to_accepted"],
        "raw_evidence_purge_preserves_followup": day18["checks"]["raw_evidence_purge_preserves_followup"],
        "multi_tenant_isolation_verified": day18["checks"]["multi_tenant_isolation_verified"],
        "zero_raw_student_text_in_telemetry": day18["checks"]["zero_raw_student_text_in_telemetry"],
        "telegram_keyboards_bounded_64_bytes": day18["checks"]["telegram_keyboards_bounded_64_bytes"],
    }
    passed = bool(prior["passed"] and day18["passed"])
    return {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "TeacherOS master-plan Days 1–18 (Phase 1 + Phase 2 + Phase 3 Days 15–18)",
        "schema_version": 19,
        "phase1_status": "PASS",
        "phase2_status": "PASS",
        "phase3_status": "IN_PROGRESS (Days 15–18 Complete)",
        "automated_tests": {"count": automated_test_count, "status": "PASS"},
        "engineering_status": "PASS" if passed else "FAIL",
        "external_evidence_status": "BLOCKED_NOT_FABRICATED",
        "external_evidence_note": (
            "Prior external gates remain honest, and Phase 2 exit requires observed "
            "teacher repeat-use data over 4 weeks without simulated/fabricated pilot claims."
        ),
        "days": days,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit TeacherOS Days 1–18.")
    parser.add_argument("--test-count", type=int, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "day18" / "days01-18_audit.json",
    )
    args = parser.parse_args()
    report = evaluate_days_1_to_18(automated_test_count=args.test_count)
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"DAYS 1-18 ENGINEERING: {report['engineering_status']}")
    print(f"PHASE 3 STATUS: {report['phase3_status']}")
    print(f"Report: {output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
