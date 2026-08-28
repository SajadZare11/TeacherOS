from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from class_setup_keyboards import choice_keyboard, multi_keyboard, review_keyboard, typed_step_keyboard
from class_setup_panel import AGES, DURATIONS, EQUIPMENT, GOALS, LEVELS, PREFERENCES, SIZES, WEAK
from day7_migration import SCHEMA_VERSION


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = re.compile(r"^v1\|[a-z]{2,4}\|[a-z0-9]{1,8}\|[0-9a-z]{1,13}\|[0-9a-z]{1,6}$")


def _callbacks(markup: Any) -> list[str]:
    return [str(button.callback_data) for row in markup.inline_keyboard for button in row if button.callback_data]


def evaluate_setup() -> dict[str, Any]:
    screens = (
        typed_step_keyboard(35),
        choice_keyboard("level", LEVELS, 35),
        choice_keyboard("age", AGES, 35),
        choice_keyboard("size", SIZES, 35),
        choice_keyboard("duration", DURATIONS, 35),
        choice_keyboard("goal", GOALS, 35),
        multi_keyboard("weak", WEAK, ["ns"], 35),
        typed_step_keyboard(35, skip=True),
        multi_keyboard("equip", EQUIPMENT, ["ns"], 35),
        multi_keyboard("prefer", PREFERENCES, ["ns"], 35),
        review_keyboard(9_223_372_036_854_775_807, 35),
    )
    callbacks = [callback for screen in screens for callback in _callbacks(screen)]
    over_limit = sorted({value for value in callbacks if len(value.encode("utf-8")) > 64})
    invalid = sorted({value for value in callbacks if CONTRACT.fullmatch(value) is None})
    missing_navigation = [
        index + 1
        for index, screen in enumerate(screens)
        if not all(any(f"|{action}|" in value for value in _callbacks(screen)) for action in ("back", "draft", "cancel"))
    ]
    passed = not over_limit and not invalid and not missing_navigation
    return {
        "day": 7,
        "schema_version": SCHEMA_VERSION,
        "engineering_status": "PASS" if passed else "FAIL",
        "passed": passed,
        "setup_screens_checked": len(screens),
        "callbacks_checked": len(callbacks),
        "maximum_callback_bytes": max(len(value.encode("utf-8")) for value in callbacks),
        "over_limit_callbacks": over_limit,
        "invalid_callbacks": invalid,
        "screens_missing_back_draft_cancel": missing_navigation,
        "required_free_text": {"class_label_max_words": 10},
        "optional_free_text": {"coursebook_unit_max_words": 14},
        "metrics": ["class_setup_started", "class_setup_completed", "class_setup_abandoned"],
        "timing_gate": {
            "status": "NOT_RUN",
            "required_observations": 3,
            "median_target_seconds_exclusive": 120,
            "recorded_observations": 0,
            "decision": "HOLD_EXTERNAL_VALIDATION",
            "reason": "No real observed setup timings were supplied or fabricated.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TeacherOS Day 7 class setup.")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "outputs" / "day07" / "setup_report.json")
    args = parser.parse_args()
    report = evaluate_setup()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
