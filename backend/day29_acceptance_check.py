r"""TeacherOS Day 29 stability acceptance gate.

This check is intentionally offline and deterministic.  It verifies the user-visible
stability contracts in source, documentation, and the release diagnostic without
calling Telegram, OpenRouter, or a payment provider.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND = PROJECT_ROOT / "backend"
DOCS = PROJECT_ROOT / "docs"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "day29" / "acceptance_report.json"


def _source(name: str) -> str:
    return (BACKEND / name).read_text(encoding="utf-8")


def evaluate_day29() -> dict[str, Any]:
    generators = {
        "lesson": ("lesson_planner.py", "Generate Lesson", "lesson"),
        "activity": ("activity_generator.py", "Generate Activity", "activity"),
        "worksheet": ("worksheet_generator.py", "Generate Worksheet", "worksheet"),
        "assessment": ("quiz_generator.py", "Generate Assessment", "quiz"),
    }
    retry_checks: dict[str, bool] = {}
    topic_checks: dict[str, bool] = {}
    cancel_checks: dict[str, bool] = {}
    for feature, (filename, retry_label, callback_prefix) in generators.items():
        text = _source(filename)
        retry_checks[feature] = (
            'state"] = "confirm"' in text
            and f"{retry_label} to retry" in text
            and "Your choices are still saved" in text
        )
        topic_checks[feature] = 'topic = " ".join((update.message.text or "").split())' in text
        cancel_checks[feature] = (
            f'callback_data="{callback_prefix}_cancel"' in text
            or f'data == "{callback_prefix}_cancel"' in text
        ) and "start_menu_keyboard()" in text

    main_text = _source("main.py")
    feedback_text = _source("feedback_panel.py")
    account_text = _source("account_panel.py")
    admin_text = _source("admin_panel.py")
    database_text = _source("database.py")
    payment_text = _source("payment_server.py")
    requirements = (PROJECT_ROOT / "requirements.txt").read_bytes()
    requirements_text = requirements.decode("utf-8")
    guide_text = (DOCS / "Day28_Beta_Testing_Guide.md").read_text(encoding="utf-8")
    check_text = _source("check_project.py")

    check_project = subprocess.run(
        [sys.executable, str(BACKEND / "check_project.py")],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    checks = {
        "all_generators_preserve_retry_state": all(retry_checks.values()),
        "all_generators_normalize_topics": all(topic_checks.values()),
        "all_generators_have_reachable_cancel": all(cancel_checks.values()),
        "command_cancel_returns_main_menu": (
            "context.user_data.clear()" in main_text
            and "Current operation cancelled." in main_text
            and "reply_markup=start_menu_keyboard()" in main_text
        ),
        "global_error_returns_main_menu": (
            "async def error_handler" in main_text
            and "Something unexpected happened" in main_text
            and "reply_markup=start_menu_keyboard()" in main_text
        ),
        "owner_feedback_return_keeps_admin": (
            "def _account_keyboard" in feedback_text
            and "is_admin_telegram_user" in feedback_text
            and "show_admin=is_admin_telegram_user" in feedback_text
            and "show_admin=is_admin_telegram_user" in account_text
        ),
        "configured_timezone_used_for_admin_metrics": (
            "_usage_day_start_utc()" in database_text
            and "get_usage_timezone()" in database_text
            and "USAGE_TIMEZONE" in admin_text
        ),
        "payment_server_reuses_port_and_explains_conflict": (
            "allow_reuse_address = True" in payment_text
            and "PAYMENT_SERVER_PORT" in main_text
            and "Close any older TeacherOS process" in main_text
        ),
        "requirements_are_utf8_and_complete": all(
            package in requirements_text
            for package in (
                "python-telegram-bot",
                "openai",
                "python-dotenv",
                "python-docx",
                "reportlab",
                "tzdata",
                "openpyxl",
            )
        ),
        "project_checker_covers_day29_and_passes": (
            "requirements.txt is not UTF-8" in check_text
            and "_validate_python_sources" in check_text
            and check_project.returncode == 0
            and "✅ Day 29 stability check passed" in check_project.stdout
        ),
        "beta_guide_matches_one_tap_feedback": (
            "one-tap rating flow" in guide_text.lower()
            and "Ratings 2–5 are saved immediately." in guide_text
        ),
    }
    passed = all(checks.values())
    return {
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "gate": "Day 29 — Stability and UX Fixes",
        "checks": checks,
        "details": {
            "retry_paths": retry_checks,
            "topic_normalization": topic_checks,
            "cancel_paths": cancel_checks,
            "project_check_output": check_project.stdout.strip().splitlines()[-1]
            if check_project.stdout.strip()
            else "",
        },
        "passed": passed,
        "engineering_status": "PASS" if passed else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate TeacherOS Day 29 stability contracts.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = evaluate_day29()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"DAY 29 ACCEPTANCE: {report['engineering_status']}")
    print(f"Report: {output_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
