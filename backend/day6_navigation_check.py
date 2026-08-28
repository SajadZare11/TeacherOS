from __future__ import annotations

import argparse
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from feature_flags import FEATURE_ENV_VARS
from keyboards import (
    analyze_picker_keyboard,
    class_detail_keyboard,
    class_intro_keyboard,
    class_linked_back_keyboard,
    class_list_keyboard,
    class_recovery_keyboard,
    quick_create_keyboard,
    start_menu_keyboard,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CALLBACK_LIMIT_BYTES = 64
CALLBACK_CONTRACT = re.compile(
    r"^v1\|[a-z]{2,4}\|[a-z0-9]{1,8}\|[0-9a-z]{1,13}\|[0-9a-z]{1,6}$"
)
LEGACY_GENERATOR_CALLBACKS = (
    "lesson",
    "activity_start",
    "worksheet_start",
    "quiz_start",
)


@contextmanager
def _classes_flag(enabled: bool) -> Iterator[None]:
    env_name = FEATURE_ENV_VARS["classes"]
    previous = os.environ.get(env_name)
    try:
        os.environ[env_name] = "true" if enabled else "false"
        yield
    finally:
        if previous is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = previous


def _callbacks(markup: Any) -> list[str]:
    return [
        str(button.callback_data)
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def _route_name(callback: str) -> str | None:
    patterns = (
        (r"^lesson(?:$|_)", "lesson_callback"),
        (r"^activity_", "activity_callback"),
        (r"^worksheet_", "worksheet_callback"),
        (r"^quiz_", "quiz_callback"),
        (r"^search_", "search_callback"),
        (r"^account_", "account_callback"),
        (r"^home_", "home_callback"),
        (r"^v1\|(?:cl|rc)\|", "class_callback"),
    )
    for pattern, route in patterns:
        if re.search(pattern, callback):
            return route
    return None


def evaluate_navigation() -> dict[str, Any]:
    active = {
        "id": 9_223_372_036_854_775_807,
        "display_name": "Upper-intermediate evening conversation class",
        "revision": 35,
    }
    archived = {
        "id": 2,
        "display_name": "Archived Saturday class",
        "revision": 2,
    }
    with _classes_flag(True):
        screens = {
            "home": _callbacks(start_menu_keyboard()),
            "quick_create": _callbacks(quick_create_keyboard()),
            "active_classes": _callbacks(class_list_keyboard([active], archived=False)),
            "archived_classes": _callbacks(
                class_list_keyboard([archived], archived=True)
            ),
            "class_intro": _callbacks(class_intro_keyboard()),
            "active_class": _callbacks(
                class_detail_keyboard(int(active["id"]), int(active["revision"]))
            ),
            "archived_class": _callbacks(
                class_detail_keyboard(
                    int(archived["id"]),
                    int(archived["revision"]),
                    archived=True,
                )
            ),
            "analyze_picker": _callbacks(analyze_picker_keyboard([active])),
            "class_linked_analysis": _callbacks(
                class_linked_back_keyboard(int(active["id"]), int(active["revision"]))
            ),
            "stale_recovery": _callbacks(class_recovery_keyboard()),
        }
    with _classes_flag(False):
        legacy_home = _callbacks(start_menu_keyboard())

    all_callbacks = [callback for values in screens.values() for callback in values]
    over_limit = sorted(
        {callback for callback in all_callbacks if len(callback.encode("utf-8")) > 64}
    )
    contract_errors = sorted(
        {
            callback
            for callback in all_callbacks
            if callback.startswith("v1|") and CALLBACK_CONTRACT.fullmatch(callback) is None
        }
    )
    unregistered = sorted(
        {callback for callback in all_callbacks if _route_name(callback) is None}
    )
    escape_errors = sorted(
        screen
        for screen, values in screens.items()
        if screen != "home"
        and not any(
            callback in {"v1|cl|home|0|0", "v1|rc|home|0|0"}
            or "|list|" in callback
            or "|open|" in callback
            for callback in values
        )
    )
    quick_create = screens["quick_create"]
    legacy_preserved = tuple(quick_create[:4]) == LEGACY_GENERATOR_CALLBACKS
    expected_legacy_home = (
        "lesson",
        "activity_start",
        "worksheet_start",
        "quiz_start",
        "search_start",
        "account_home",
    )
    rollback_preserved = tuple(legacy_home) == expected_legacy_home
    archived_read_only = not any(
        "|analyze|" in callback for callback in screens["archived_class"]
    )
    passed = all(
        (
            not over_limit,
            not contract_errors,
            not unregistered,
            not escape_errors,
            legacy_preserved,
            rollback_preserved,
            archived_read_only,
        )
    )
    return {
        "day": 6,
        "engineering_status": "PASS" if passed else "FAIL",
        "passed": passed,
        "screens_checked": len(screens),
        "callbacks_checked": len(all_callbacks),
        "maximum_callback_bytes": max(
            len(callback.encode("utf-8")) for callback in all_callbacks
        ),
        "callback_limit_bytes": CALLBACK_LIMIT_BYTES,
        "over_limit_callbacks": over_limit,
        "contract_errors": contract_errors,
        "unregistered_callbacks": unregistered,
        "screens_without_escape": escape_errors,
        "legacy_generator_callbacks_preserved": legacy_preserved,
        "flag_off_legacy_home_preserved": rollback_preserved,
        "archived_class_read_only": archived_read_only,
        "hallway_gate": {
            "status": "NOT_RUN",
            "required_correct": 4,
            "required_participants": 5,
            "recorded_participants": 0,
            "decision": "HOLD_EXTERNAL_VALIDATION",
            "reason": "No real participant observations were supplied or fabricated.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TeacherOS Day 6 navigation.")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "day06" / "navigation_report.json",
    )
    args = parser.parse_args()
    report = evaluate_navigation()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
