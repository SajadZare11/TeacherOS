from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from class_dashboard_keyboards import (
    archived_dashboard_keyboard,
    class_action_keyboard,
    class_dashboard_keyboard,
    class_details_keyboard,
    class_profile_keyboard,
    confirmation_keyboard,
    edit_choice_keyboard,
    edit_multi_keyboard,
    edit_text_keyboard,
    today_queue_keyboard,
)
from class_dashboard_panel import FIELD_CODES
from class_setup_panel import LEVELS, PREFERENCES
from day8_migration import SCHEMA_VERSION


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = re.compile(
    r"^v1\|[a-z]{2,4}\|[a-z0-9]{1,8}\|[0-9a-z]{1,13}\|[0-9a-z]{1,6}$"
)
SECONDARY_LABELS = {
    "🔬 Analyze Work",
    "🧰 Create Materials",
    "✅ Record Outcome",
    "📈 Progress",
    "📁 Library",
    "👤 Profile",
}
TODAY_KINDS = {
    "unfinished_setup",
    "planned_lesson",
    "missing_outcome",
    "pending_analysis",
    "review_due",
}


def _buttons(markup: Any) -> list[Any]:
    return [button for row in markup.inline_keyboard for button in row]


def evaluate_dashboard() -> dict[str, Any]:
    maximum_id = 9_223_372_036_854_775_807
    maximum_revision = 2_176_782_335
    today_items = [
        {
            "kind": kind,
            "class_id": None if kind == "unfinished_setup" else 35,
            "display_name": "B1 Evening",
            "revision": 35,
        }
        for kind in (
            "unfinished_setup",
            "missing_outcome",
            "pending_analysis",
            "planned_lesson",
            "review_due",
        )
    ]
    markups = (
        class_dashboard_keyboard(maximum_id, maximum_revision),
        archived_dashboard_keyboard(maximum_id, maximum_revision),
        class_details_keyboard(maximum_id, maximum_revision, archived=False),
        class_profile_keyboard(maximum_id, maximum_revision, archived=False),
        confirmation_keyboard(maximum_id, maximum_revision, archive=True),
        confirmation_keyboard(maximum_id, maximum_revision, archive=False),
        edit_choice_keyboard(tuple(("lv" + code, label) for code, label in LEVELS), maximum_revision),
        edit_multi_keyboard("pf", PREFERENCES, ["struct"], maximum_revision),
        edit_text_keyboard(maximum_id, maximum_revision, coursebook=True),
        today_queue_keyboard(today_items),
        class_action_keyboard(maximum_id, maximum_revision, "plan"),
        class_action_keyboard(maximum_id, maximum_revision, "create"),
    )
    buttons = [button for markup in markups for button in _buttons(markup)]
    callbacks = [str(button.callback_data) for button in buttons if button.callback_data]
    contracted = [value for value in callbacks if value.startswith("v1|")]
    invalid = sorted({value for value in contracted if CONTRACT.fullmatch(value) is None})
    over_limit = sorted(
        {value for value in callbacks if len(value.encode("utf-8")) > 64}
    )
    dashboard = class_dashboard_keyboard(35, 7)
    dashboard_buttons = _buttons(dashboard)
    primary_ok = bool(dashboard_buttons) and dashboard_buttons[0].text == "🎯 Plan Next Lesson"
    labels = {button.text for button in dashboard_buttons}
    secondary_missing = sorted(SECONDARY_LABELS - labels)
    today_rendered = {
        item["kind"] for item in today_items
        if any(item["display_name"] in button.text or item["kind"] == "unfinished_setup" for button in _buttons(today_queue_keyboard([item])))
    }
    destructive_callbacks = {
        value
        for value in callbacks
        if "|archyes|" in value or "|restyes|" in value
    }
    passed = all(
        (
            not invalid,
            not over_limit,
            primary_ok,
            not secondary_missing,
            today_rendered == TODAY_KINDS,
            len(FIELD_CODES) == 10,
            len(destructive_callbacks) == 2,
        )
    )
    return {
        "day": 8,
        "schema_version": SCHEMA_VERSION,
        "engineering_status": "PASS" if passed else "FAIL",
        "passed": passed,
        "dashboard_primary_action": "Plan Next Lesson",
        "primary_action_is_first": primary_ok,
        "secondary_actions_missing": secondary_missing,
        "profile_fields_editable": len(FIELD_CODES),
        "today_queue_kinds": sorted(today_rendered),
        "destructive_confirmations_checked": len(destructive_callbacks),
        "callbacks_checked": len(callbacks),
        "maximum_callback_bytes": max(len(value.encode("utf-8")) for value in callbacks),
        "invalid_callbacks": invalid,
        "over_limit_callbacks": over_limit,
        "phone_message_character_budget": 700,
        "usability_gate": {
            "status": "NOT_RUN",
            "decision": "HOLD_EXTERNAL_VALIDATION",
            "minimum_testers": 5,
            "target_primary_action_selection_rate": 0.8,
            "identification_target_seconds": 5,
            "recorded_observations": 0,
            "reason": "No real usability observations were supplied or fabricated.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TeacherOS Day 8 class dashboard.")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "day08" / "dashboard_report.json",
    )
    args = parser.parse_args()
    report = evaluate_dashboard()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
