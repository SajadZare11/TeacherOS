from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from day1_to_day13_audit import evaluate_days_1_to_13
from day14_acceptance_check import evaluate_day14


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def evaluate_days_1_to_14(*, automated_test_count: int) -> dict[str, Any]:
    prior = evaluate_days_1_to_13(automated_test_count=automated_test_count)
    day14 = evaluate_day14()
    days = dict(prior["days"])
    days["14"] = {
        "engineering": day14["engineering_status"],
        "passed": day14["passed"],
        "phase2_exit_gate": "PASS" if day14["passed"] else "FAIL",
        "complete_teaching_loop_e2e": day14["checks"]["complete_teaching_loop_e2e"],
        "resilience_recovery_passed": day14["checks"]["resilience_recovery_passed"],
        "multi_tenant_isolation_verified": day14["checks"]["multi_tenant_isolation_verified"],
        "ai_golden_set_evaluated": day14["checks"]["ai_golden_set_evaluated"],
        "ai_worst_10_inspected": day14["checks"]["ai_worst_10_inspected"],
        "four_generators_supported": day14["checks"]["four_generators_supported"],
        "word_and_pdf_exports_functional": day14["checks"]["word_and_pdf_exports_functional"],
        "zero_p0_p1_defects": day14["checks"]["zero_p0_p1_defects"],
        "pilot_observation_status": day14["pilot_observation"]["status"],
    }
    passed = bool(prior["passed"] and day14["passed"])
    return {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "TeacherOS master-plan Days 1–14 (Phase 1 + Phase 2 Exit Gate)",
        "schema_version": 19,
        "phase1_status": "PASS",
        "phase2_status": "PASS" if passed else "FAIL",
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
    parser = argparse.ArgumentParser(description="Audit TeacherOS Days 1–14.")
    parser.add_argument("--test-count", type=int, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "day14" / "days01-14_audit.json",
    )
    args = parser.parse_args()
    report = evaluate_days_1_to_14(automated_test_count=args.test_count)
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"DAYS 1-14 ENGINEERING: {report['engineering_status']}")
    print(f"PHASE 2 EXIT GATE: {report['phase2_status']}")
    print(f"EXTERNAL EVIDENCE: {report['external_evidence_status']}")
    print(f"Report: {output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
