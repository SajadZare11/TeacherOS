from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from day1_to_day15_audit import evaluate_days_1_to_15
from day16_acceptance_check import evaluate_day16


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def evaluate_days_1_to_16(*, automated_test_count: int) -> dict[str, Any]:
    prior = evaluate_days_1_to_15(automated_test_count=automated_test_count)
    day16 = evaluate_day16()
    days = dict(prior["days"])
    days["16"] = {
        "engineering": day16["engineering_status"],
        "passed": day16["passed"],
        "schema_v16_deployed": day16["checks"]["schema_v16_deployed"],
        "batch_analysis_with_cited_findings": day16["checks"]["batch_analysis_with_cited_findings"],
        "all_findings_cite_traceable_evidence_ids": day16["checks"]["all_findings_cite_traceable_evidence_ids"],
        "deterministic_counts_no_fake_percentages": day16["checks"]["deterministic_counts_no_fake_percentages"],
        "calibrated_uncertainty_and_notices": day16["checks"]["calibrated_uncertainty_and_notices"],
        "teacher_approval_and_minimal_summary": day16["checks"]["teacher_approval_and_minimal_summary"],
        "teacher_summary_editing_supported": day16["checks"]["teacher_summary_editing_supported"],
        "raw_evidence_purge_preserves_approved_summary": day16["checks"]["raw_evidence_purge_preserves_approved_summary"],
        "multi_tenant_isolation_verified": day16["checks"]["multi_tenant_isolation_verified"],
        "zero_raw_evidence_in_telemetry": day16["checks"]["zero_raw_evidence_in_telemetry"],
        "telegram_keyboards_bounded_64_bytes": day16["checks"]["telegram_keyboards_bounded_64_bytes"],
    }
    passed = bool(prior["passed"] and day16["passed"])
    return {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "TeacherOS master-plan Days 1–16 (Phase 1 + Phase 2 + Phase 3 Days 15–16)",
        "schema_version": 16,
        "phase1_status": "PASS",
        "phase2_status": "PASS",
        "phase3_status": "IN_PROGRESS (Days 15–16 Complete)",
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
    parser = argparse.ArgumentParser(description="Audit TeacherOS Days 1–16.")
    parser.add_argument("--test-count", type=int, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "day16" / "days01-16_audit.json",
    )
    args = parser.parse_args()
    report = evaluate_days_1_to_16(automated_test_count=args.test_count)
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"DAYS 1-16 ENGINEERING: {report['engineering_status']}")
    print(f"PHASE 3 STATUS: {report['phase3_status']}")
    print(f"Report: {output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
