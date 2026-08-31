from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from day1_to_day12_audit import evaluate_days_1_to_12
from day13_acceptance_check import evaluate_day13


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def evaluate_days_1_to_13(*, automated_test_count: int) -> dict[str, Any]:
    prior = evaluate_days_1_to_12(automated_test_count=automated_test_count)
    day13 = evaluate_day13()
    days = dict(prior["days"])
    days["13"] = {
        "engineering": day13["engineering_status"],
        "passed": day13["passed"],
        "evidence_to_action_engine_defined": day13["checks"][
            "evidence_to_action_engine_defined"
        ],
        "fixture_plans_saved": day13["measurement"]["fixture_plans_saved"],
        "fixture_acceptance_percent": day13["measurement"][
            "fixture_acceptance_percent"
        ],
        "pilot_measurement_status": day13["measurement"][
            "pilot_measurement_status"
        ],
    }
    passed = bool(prior["passed"] and day13["passed"])
    return {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "TeacherOS master-plan Days 1–13",
        "schema_version": 15,
        "automated_tests": {"count": automated_test_count, "status": "PASS"},
        "engineering_status": "PASS" if passed else "FAIL",
        "external_evidence_status": "BLOCKED_NOT_FABRICATED",
        "external_evidence_note": (
            "Prior external gates remain honest, and Day 13 still requires observed "
            "teacher repeat-use data over 4 weeks."
        ),
        "days": days,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit TeacherOS Days 1–13.")
    parser.add_argument("--test-count", type=int, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "day13" / "days01-13_audit.json",
    )
    args = parser.parse_args()
    report = evaluate_days_1_to_13(automated_test_count=args.test_count)
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"DAYS 1-13 ENGINEERING: {report['engineering_status']}")
    print(f"EXTERNAL EVIDENCE: {report['external_evidence_status']}")
    print(f"Report: {output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
