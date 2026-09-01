r"""Offline Day 30 progressive-launch acceptance gate."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND = PROJECT_ROOT / "backend"
WEBSITE = PROJECT_ROOT / "website"
BACKUPS = PROJECT_ROOT / "backups"
CHECKLIST = PROJECT_ROOT / "docs" / "Day30_Launch_Checklist.md"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "day30" / "acceptance_report.json"


def _run(command: list[str], *, feature_flags_enabled: bool = False) -> tuple[int, str]:
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    if feature_flags_enabled:
        environment.update(
            {
                "TEACHEROS_FEATURE_CLASSES": "true",
                "TEACHEROS_FEATURE_CONTINUITY": "true",
                "TEACHEROS_FEATURE_EVIDENCE": "true",
                "TEACHEROS_FEATURE_DIFFERENTIATION": "true",
                "TEACHEROS_FEATURE_REPORTS": "true",
                "TEACHEROS_FEATURE_ENTITLEMENTS": "true",
            }
        )
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def _latest_healthy_backup() -> dict[str, Any] | None:
    candidates = sorted(
        (path for path in BACKUPS.glob("teacheros_*.db") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            with sqlite3.connect(path) as connection:
                integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0]).lower()
                foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
                schema = int(connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0])
            if integrity == "ok" and not foreign_keys and schema >= 28:
                return {
                    "path": str(path.relative_to(PROJECT_ROOT)),
                    "integrity": integrity,
                    "foreign_key_issues": len(foreign_keys),
                    "schema_version": schema,
                }
        except (OSError, sqlite3.Error, TypeError, ValueError):
            continue
    return None


def evaluate_day30() -> dict[str, Any]:
    checklist = CHECKLIST.read_text(encoding="utf-8") if CHECKLIST.is_file() else ""
    launch_code, launch_output = _run(
        [sys.executable, str(BACKEND / "launch_check.py"), "--mode", "beta", "--require-flags"],
        feature_flags_enabled=True,
    )
    website_code, website_output = _run([sys.executable, str(WEBSITE / "check_website.py")])
    backup = _latest_healthy_backup()

    checks = {
        "launch_check_beta_passes": launch_code == 0 and "Launch status: FREE/BETA" in launch_output,
        "all_day30_feature_flags_enabled": "All Day 30 feature flags are enabled" in launch_output,
        "website_check_passes": website_code == 0 and "Landing page check passed" in website_output,
        "fresh_schema_28_or_newer_backup_is_healthy": backup is not None,
        "backup_integrity_is_explicitly_checked": "integrity_check" in (BACKEND / "backup_teacheros.py").read_text(encoding="utf-8"),
        "public_privacy_and_terms_are_linked": (
            (WEBSITE / "privacy.html").is_file()
            and (WEBSITE / "terms.html").is_file()
            and 'href="privacy.html"' in (WEBSITE / "index.html").read_text(encoding="utf-8")
            and 'href="terms.html"' in (WEBSITE / "index.html").read_text(encoding="utf-8")
        ),
        "pricing_drift_is_machine_checked": "pricing matches backend subscription configuration" in launch_output,
        "progressive_five_teacher_mission_is_documented": (
            "Invite five teachers first" in checklist
            and "remaining 5–10 teachers" in checklist
            and "complete mission" in checklist
        ),
        "daily_monitoring_and_interviews_are_documented": (
            "Monitor every day" in checklist
            and "Day 3, Day 7, and Day 14" in checklist
            and "weekly verified teaching loops" in checklist
        ),
        "day14_thresholds_and_non_claims_are_documented": (
            "7 classes created" in checklist
            and "4 return in week two" in checklist
            and "3 teachers say they would be very disappointed" in checklist
            and "Do not claim" in checklist
        ),
        "launch_checker_handles_unicode_console": "reconfigure(encoding=\"utf-8\"" in (BACKEND / "launch_check.py").read_text(encoding="utf-8"),
        "all_runtime_dependencies_are_checked": "openpyxl" in (BACKEND / "launch_check.py").read_text(encoding="utf-8"),
    }
    passed = all(checks.values())
    return {
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "gate": "Day 30 — Progressive Launch and 14-Day Learning System",
        "checks": checks,
        "details": {
            "backup": backup,
            "launch_last_line": launch_output.strip().splitlines()[-1] if launch_output.strip() else "",
        },
        "passed": passed,
        "engineering_status": "PASS" if passed else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate TeacherOS Day 30 launch readiness.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = evaluate_day30()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"DAY 30 ACCEPTANCE: {report['engineering_status']}")
    print(f"Report: {output_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
