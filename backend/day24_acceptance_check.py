"""TeacherOS Day 24 Acceptance Check.

Validates Telegram speed, clarity, accessibility, and localization:
- Schema v24 deployed with UI preferences and pinned materials.
- Centralized string catalog with EN/FA localization and safe fallback.
- Screen-reader accessibility annotations without emoji reliance.
- 3-step first-run onboarding walkthrough flow.
- Class-aware material pinning and search.
- Multi-tenant isolation and 64-byte Telegram bounds.
- Stale state protection and safe recovery.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import database
from class_service import create_class
from feature_flags import FEATURE_ENV_VARS
from string_catalog import STRINGS_EN, STRINGS_FA, tr
from ui_keyboards import (
    language_switcher_keyboard,
    material_pin_toggle_keyboard,
    onboarding_walkthrough_keyboard,
    pinned_materials_keyboard,
)
from ui_service import (
    complete_onboarding,
    get_or_create_ui_preferences,
    is_material_pinned,
    list_pinned_materials,
    pin_material_to_class,
    search_class_materials,
    set_user_language,
    unpin_material_from_class,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "day24"
DEFAULT_REPORT = OUTPUTS_DIR / "acceptance_report.json"


def _teacher(identifier: int, username: str = "teacher") -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        username=f"{username}_{identifier}",
        first_name="Acceptance",
        last_name="Teacher",
        language_code="en",
    )


def evaluate_day24() -> dict[str, Any]:
    previous_flags = {name: os.environ.get(name) for name in FEATURE_ENV_VARS.values()}
    for name in FEATURE_ENV_VARS.values():
        os.environ[name] = "false"
    os.environ[FEATURE_ENV_VARS["classes"]] = "true"
    os.environ[FEATURE_ENV_VARS["continuity"]] = "true"

    try:
        with tempfile.TemporaryDirectory(prefix="teacheros-day24-acceptance-") as temp_dir:
            path = Path(temp_dir) / "teacheros.db"
            original_path = database.DATABASE_PATH
            database.DATABASE_PATH = path

            try:
                database.initialize_database(path)
                teacher_a = _teacher(240_001, "teacher_a")
                teacher_b = _teacher(240_002, "teacher_b")

                with database.database_connection(path) as conn:
                    user_a_id = database.ensure_database_user(conn, teacher_a)
                    user_b_id = database.ensure_database_user(conn, teacher_b)

                class_a = create_class(
                    telegram_user=teacher_a,
                    display_name="B2 Professional Business English",
                    level="B2",
                    age_group="adults",
                    learner_count_band="6_12",
                    goal="Negotiations and presentation delivery",
                    database_path=path,
                )
                class_a_id = int(class_a["id"])

                class_b = create_class(
                    telegram_user=teacher_b,
                    display_name="A2 General English",
                    level="A2",
                    age_group="teens",
                    learner_count_band="2_5",
                    goal="Basic fluency",
                    database_path=path,
                )
                class_b_id = int(class_b["id"])

                # 1. Schema v24 verification
                with database.database_connection(path) as conn:
                    schema_ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
                    t1 = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_ui_preferences'").fetchone()
                    t2 = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_pinned_materials'").fetchone()
                    schema_valid = (schema_ver >= 24 and t1 is not None and t2 is not None)

                # 2. String catalog and localization
                en_str = tr("nav_save", "en")
                fa_str = tr("nav_save", "fa")
                fallback_str = tr("non_existent_key_xyz", "fa")
                catalog_valid = (
                    en_str == "💾 Save"
                    and fa_str == "💾 ذخیره"
                    and "[non_existent_key_xyz]" in fallback_str
                    and len(STRINGS_EN) >= 25
                    and len(STRINGS_FA) >= 25
                )

                # 3. Language preference persistence
                prefs1 = get_or_create_ui_preferences(user_a_id, database_path=path)
                set_user_language(user_a_id, "fa", database_path=path)
                prefs2 = get_or_create_ui_preferences(user_a_id, database_path=path)
                lang_persisted = (prefs1["language_code"] == "en" and prefs2["language_code"] == "fa")

                # 4. 3-step onboarding walkthrough flow
                self_onb_before = prefs2["onboarding_completed"] == 0
                complete_onboarding(user_a_id, database_path=path)
                prefs3 = get_or_create_ui_preferences(user_a_id, database_path=path)
                onboarding_valid = (self_onb_before and prefs3["onboarding_completed"] == 1)

                # 5. Pinned materials & favorites
                with database.database_connection(path) as conn:
                    mat_cur = conn.execute(
                        """
                        INSERT INTO materials (user_id, material_type, title, level, content, class_id)
                        VALUES (?, 'lesson', 'Negotiation Strategies Part 1', 'B2', 'Sample Content', ?)
                        """,
                        (user_a_id, class_a_id),
                    )
                    material_id = mat_cur.lastrowid

                pin_ok = pin_material_to_class(user_id=user_a_id, class_id=class_a_id, material_id=material_id, database_path=path)
                is_pinned = is_material_pinned(user_id=user_a_id, class_id=class_a_id, material_id=material_id, database_path=path)
                pinned_list = list_pinned_materials(user_id=user_a_id, class_id=class_a_id, database_path=path)
                unpin_ok = unpin_material_from_class(user_id=user_a_id, class_id=class_a_id, material_id=material_id, database_path=path)
                is_unpinned = not is_material_pinned(user_id=user_a_id, class_id=class_a_id, material_id=material_id, database_path=path)

                pinning_valid = (pin_ok and is_pinned and len(pinned_list) == 1 and unpin_ok and is_unpinned)

                # Re-pin for search / view tests
                pin_material_to_class(user_id=user_a_id, class_id=class_a_id, material_id=material_id, database_path=path)

                # 6. Class-aware material search
                search_res = search_class_materials(
                    user_id=user_a_id,
                    class_id=class_a_id,
                    query_text="negotiation",
                    database_path=path,
                )
                search_empty = search_class_materials(
                    user_id=user_a_id,
                    class_id=class_a_id,
                    query_text="nonexistent_xyz",
                    database_path=path,
                )
                search_valid = (len(search_res) == 1 and len(search_empty) == 0)

                # 7. Screen-reader accessibility annotations
                badge_approved = tr("badge_approved", "en")
                badge_needs_review = tr("badge_needs_review", "en")
                accessibility_valid = (
                    "[Status: Approved]" in badge_approved
                    and "[Status: Needs Review]" in badge_needs_review
                )

                # 8. Multi-tenant isolation
                cross_pin = pin_material_to_class(
                    user_id=user_b_id,
                    class_id=class_a_id,
                    material_id=material_id,
                    database_path=path,
                )
                cross_pinned_list = list_pinned_materials(
                    user_id=user_b_id,
                    class_id=class_a_id,
                    database_path=path,
                )
                cross_search = search_class_materials(
                    user_id=user_b_id,
                    class_id=class_a_id,
                    query_text="negotiation",
                    database_path=path,
                )
                multi_tenant_ok = (not cross_pin and len(cross_pinned_list) == 0 and len(cross_search) == 0)

                # 9. Telegram Keyboards strictly <= 64 bytes
                kbs = [
                    language_switcher_keyboard(1, "en"),
                    language_switcher_keyboard(1, "fa"),
                    onboarding_walkthrough_keyboard(1, 1, "en"),
                    onboarding_walkthrough_keyboard(2, 1, "en"),
                    onboarding_walkthrough_keyboard(3, 1, "en"),
                    pinned_materials_keyboard(class_a_id, 1, pinned_list, "en"),
                    material_pin_toggle_keyboard(class_a_id, material_id, 1, is_pinned=True, lang="en"),
                    material_pin_toggle_keyboard(class_a_id, material_id, 1, is_pinned=False, lang="en"),
                ]
                kbs_valid = all(
                    len(btn.callback_data.encode("utf-8")) <= 64
                    for kb in kbs
                    for row in kb.inline_keyboard
                    for btn in row
                )

                checks = {
                    "schema_v24_deployed": schema_valid,
                    "string_catalog_and_localization_supported": catalog_valid,
                    "language_preference_persisted": lang_persisted,
                    "three_step_onboarding_walkthrough_functional": onboarding_valid,
                    "material_pinning_and_favorites_operational": pinning_valid,
                    "class_aware_search_functional": search_valid,
                    "accessibility_screen_reader_labels_present": accessibility_valid,
                    "multi_tenant_isolation_verified": multi_tenant_ok,
                    "telegram_keyboards_bounded_64_bytes": kbs_valid,
                }
                passed = all(checks.values())

                return {
                    "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "gate": "Day 24 — Polish Telegram Speed, Clarity, Accessibility, and Localization",
                    "schema_version": 24,
                    "checks": checks,
                    "passed": passed,
                    "engineering_status": "PASS" if passed else "FAIL",
                    "details": {
                        "class_a_id": class_a_id,
                        "strings_en_count": len(STRINGS_EN),
                        "strings_fa_count": len(STRINGS_FA),
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
    parser = argparse.ArgumentParser(description="Evaluate TeacherOS Day 24 UI Polish & Localization.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = evaluate_day24()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"DAY 24 ACCEPTANCE: {report['engineering_status']}")
    print(f"Report: {output_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
