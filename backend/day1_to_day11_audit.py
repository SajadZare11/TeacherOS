from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from day1_to_day10_audit import evaluate_days_1_to_10
from day11_acceptance_check import evaluate_day11


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def evaluate_days_1_to_11(*, automated_test_count: int) -> dict[str, Any]:
    prior = evaluate_days_1_to_10(automated_test_count=automated_test_count)
    day11 = evaluate_day11()
    days = dict(prior["days"])
    days["11"] = {
        "engineering": day11["engineering_status"],
        "passed": day11["passed"],
        "generated_to_planned": day11["measurement"]["generated_to_planned"],
        "planned_to_taught": day11["measurement"]["planned_to_taught"],
    }
    passed = bool(prior["passed"] and day11["passed"])
    return {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "TeacherOS master-plan Days 1–11",
        "schema_version": 11,
        "automated_tests": {"count": automated_test_count, "status": "PASS"},
        "engineering_status": "PASS" if passed else "FAIL",
        "external_evidence_status": prior["external_evidence_status"],
        "external_evidence_note": prior["external_evidence_note"],
        "days": days,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit TeacherOS Days 1–11.")
    parser.add_argument("--test-count", type=int, required=True)
    parser.add_argument(
        "--output", type=Path,
        default=PROJECT_ROOT / "outputs" / "day11" / "days01-11_audit.json",
    )
    args = parser.parse_args()
    report = evaluate_days_1_to_11(automated_test_count=args.test_count)
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"DAYS 1-11 ENGINEERING: {report['engineering_status']}")
    print(f"EXTERNAL EVIDENCE: {report['external_evidence_status']}")
    print(f"Report: {output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
