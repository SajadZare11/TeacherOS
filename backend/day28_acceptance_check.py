"""TeacherOS Day 28 Acceptance Check.

Validates the 5-teacher release rehearsal and full teaching journey measurements:
- Schema v28 deployed with rehearsal_sessions and rehearsal_task_metrics tables.
- 5 distinct teaching personas evaluated across the 9-step complete teaching loop.
- $\ge 90\%$ task completion rate (no navigation rescue required).
- Single Ease Question (SEQ) score $\ge 6.0/7.0$ and Trust rating $\ge 4.5/5.0$.
- Top 3 behavior-backed UX improvements prioritized by Severity × Frequency × Loop Impact.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import database
from feature_flags import FEATURE_ENV_VARS
from rehearsal_service import run_full_rehearsal_suite

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "day28"
DEFAULT_REPORT = OUTPUTS_DIR / "acceptance_report.json"


def evaluate_day28() -> dict[str, Any]:
    previous_flags = {name: os.environ.get(name) for name in FEATURE_ENV_VARS.values()}
    for name in FEATURE_ENV_VARS.values():
        os.environ[name] = "true"

    try:
        with tempfile.TemporaryDirectory(prefix="teacheros-day28-acceptance-") as temp_dir:
            temp_path = Path(temp_dir)
            path = temp_path / "teacheros.db"
            original_path = database.DATABASE_PATH
            database.DATABASE_PATH = path

            try:
                database.initialize_database(path)

                # 1. Schema v28 verification
                with database.database_connection(path) as conn:
                    schema_ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
                    tbl1 = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='rehearsal_sessions'"
                    ).fetchone()
                    tbl2 = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='rehearsal_task_metrics'"
                    ).fetchone()
                    schema_valid = (schema_ver >= 28 and tbl1 is not None and tbl2 is not None)

                # 2. Run full 5-teacher rehearsal suite
                rehearsal_results = run_full_rehearsal_suite(database_path=path)

                # 3. Acceptance metrics evaluation
                completion_rate_valid = rehearsal_results["completion_rate_percent"] >= 90.0
                zero_rescues_valid = rehearsal_results["navigation_rescues_required"] == 0
                seq_score_valid = rehearsal_results["overall_avg_seq_score"] >= 6.0
                trust_score_valid = rehearsal_results["overall_trust_score"] >= 4.5
                time_saved_valid = rehearsal_results["total_est_minutes_saved"] >= 200
                top_3_valid = len(rehearsal_results["top_3_behavior_changes"]) == 3

                checks = {
                    "schema_v28_deployed": schema_valid,
                    "five_teachers_tested": rehearsal_results["teachers_tested"] == 5,
                    "task_completion_rate_ge_90_pct": completion_rate_valid,
                    "zero_navigation_rescues": zero_rescues_valid,
                    "avg_seq_score_ge_6": seq_score_valid,
                    "trust_score_ge_4_5": trust_score_valid,
                    "time_saved_verified_positive": time_saved_valid,
                    "top_3_behavior_changes_ranked": top_3_valid,
                }
                passed = all(checks.values())

                return {
                    "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "gate": "Day 28 — Five-Teacher Release Rehearsal and Full Journey Measurement",
                    "schema_version": 28,
                    "checks": checks,
                    "passed": passed,
                    "engineering_status": "PASS" if passed else "FAIL",
                    "details": {
                        "completion_rate_percent": rehearsal_results["completion_rate_percent"],
                        "overall_avg_seq_score": rehearsal_results["overall_avg_seq_score"],
                        "overall_trust_score": rehearsal_results["overall_trust_score"],
                        "total_est_minutes_saved": rehearsal_results["total_est_minutes_saved"],
                        "top_3_changes": rehearsal_results["top_3_behavior_changes"],
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
    parser = argparse.ArgumentParser(description="Evaluate TeacherOS Day 28 Release Rehearsal.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = evaluate_day28()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"DAY 28 ACCEPTANCE: {report['engineering_status']}")
    print(f"Report: {output_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
