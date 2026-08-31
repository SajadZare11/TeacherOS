from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from day1_to_day11_audit import evaluate_days_1_to_11
from day12_acceptance_check import evaluate_day12


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def evaluate_days_1_to_12(*, automated_test_count: int) -> dict[str, Any]:
    prior = evaluate_days_1_to_11(automated_test_count=automated_test_count)
    day12 = evaluate_day12()
    days = dict(prior["days"])
    days["12"] = {
        "engineering": day12["engineering_status"],
        "passed": day12["passed"],
        "three_fact_taps_structurally_defined": day12["checks"][
            "three_fact_taps_structurally_defined"
        ],
        "fixture_recording_rate_percent": day12["measurement"][
            "fixture_recording_rate_percent"
        ],
        "pilot_measurement_status": day12["measurement"][
            "pilot_measurement_status"
        ],
    }
    passed = bool(prior["passed"] and day12["passed"])
    return {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "TeacherOS master-plan Days 1–12",
        "schema_version": 12,
        "automated_tests": {"count": automated_test_count, "status": "PASS"},
        "engineering_status": "PASS" if passed else "FAIL",
        "external_evidence_status": "BLOCKED_NOT_FABRICATED",
        "external_evidence_note": (
            "Prior external gates remain honest, and Day 12 still requires observed "
            "teacher timing plus pilot outcome-recording evidence."
        ),
        "days": days,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit TeacherOS Days 1–12.")
    parser.add_argument("--test-count", type=int, required=True)
    parser.add_argument(
        "--output", type=Path,
        default=PROJECT_ROOT / "outputs" / "day12" / "days01-12_audit.json",
    )
    args = parser.parse_args()
    report = evaluate_days_1_to_12(automated_test_count=args.test_count)
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"DAYS 1-12 ENGINEERING: {report['engineering_status']}")
    print(f"EXTERNAL EVIDENCE: {report['external_evidence_status']}")
    print(f"Report: {output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
