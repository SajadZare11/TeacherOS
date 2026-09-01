"""TeacherOS Day 25 Acceptance Check.

Validates commercial value packaging, centralized entitlements, and upgrade telemetry:
- Schema v25 deployed with entitlement_events table.
- Centralized tier capabilities (Free, Pro, Premium) across all recurring workflows.
- Contextual upgrade prompts focused on teaching outcomes (never 'tokens').
- Commercial funnel instrumentation (viewed, checkout_started, paid, etc.).
- Idempotent payment verification and subscription activation.
- Free teaching loop guarantee (1 complete genuine teaching loop supported).
- Multi-tenant isolation and ZarinPal sandbox readiness.
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
from entitlement_service import (
    TIER_LIMITS,
    can_complete_teaching_loop,
    check_feature_access,
    get_contextual_upgrade_prompt,
    record_entitlement_event,
)
from feature_flags import FEATURE_ENV_VARS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "day25"
DEFAULT_REPORT = OUTPUTS_DIR / "acceptance_report.json"


def _teacher(identifier: int, username: str = "teacher") -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        username=f"{username}_{identifier}",
        first_name="Acceptance",
        last_name="Teacher",
        language_code="en",
    )


def evaluate_day25() -> dict[str, Any]:
    previous_flags = {name: os.environ.get(name) for name in FEATURE_ENV_VARS.values()}
    for name in FEATURE_ENV_VARS.values():
        os.environ[name] = "false"
    os.environ[FEATURE_ENV_VARS["classes"]] = "true"
    os.environ[FEATURE_ENV_VARS["continuity"]] = "true"
    os.environ[FEATURE_ENV_VARS["entitlements"]] = "true"

    try:
        with tempfile.TemporaryDirectory(prefix="teacheros-day25-acceptance-") as temp_dir:
            path = Path(temp_dir) / "teacheros.db"
            original_path = database.DATABASE_PATH
            database.DATABASE_PATH = path

            try:
                database.initialize_database(path)
                teacher_a = _teacher(250_001, "teacher_a")
                teacher_b = _teacher(250_002, "teacher_b")

                with database.database_connection(path) as conn:
                    user_a_id = database.ensure_database_user(conn, teacher_a)
                    user_b_id = database.ensure_database_user(conn, teacher_b)

                # 1. Schema v25 verification
                with database.database_connection(path) as conn:
                    schema_ver = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
                    t1 = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='entitlement_events'"
                    ).fetchone()
                    schema_valid = (schema_ver >= 25 and t1 is not None)

                # 2. Centralized tier limits
                tier_valid = (
                    TIER_LIMITS["free"]["active_classes"] == 1
                    and TIER_LIMITS["pro"]["active_classes"] == 10
                    and TIER_LIMITS["premium"]["active_classes"] is None
                    and TIER_LIMITS["free"]["daily_generations"] == 10
                    and TIER_LIMITS["pro"]["daily_generations"] == 50
                    and TIER_LIMITS["premium"]["daily_generations"] is None
                    and TIER_LIMITS["free"]["progress_reports_export"] is False
                    and TIER_LIMITS["pro"]["progress_reports_export"] is True
                )

                # 3. Feature access checks
                access_free_cls = check_feature_access(teacher_a.id, "active_classes", database_path=path)
                access_free_exp = check_feature_access(teacher_a.id, "progress_reports_export", database_path=path)
                feature_checks_valid = (
                    access_free_cls["allowed"] is True
                    and access_free_exp["allowed"] is False
                    and access_free_exp["upgrade_prompt"] is not None
                )

                # 4. Contextual outcome-oriented upgrade prompts (never 'token')
                prompt_cls = get_contextual_upgrade_prompt("active_classes", "en")
                prompt_rep = get_contextual_upgrade_prompt("progress_reports_export", "en")
                no_tokens_in_prompts = (
                    "token" not in prompt_cls.lower()
                    and "token" not in prompt_rep.lower()
                    and "class" in prompt_cls.lower()
                    and "report" in prompt_rep.lower()
                )

                # 5. Commercial funnel telemetry & events
                evt1 = record_entitlement_event(
                    user_id=user_a_id,
                    event_type="viewed",
                    plan_code="pro",
                    feature_key="active_classes",
                    metadata={"source": "class_limit_modal"},
                    database_path=path,
                )
                evt2 = record_entitlement_event(
                    user_id=user_a_id,
                    event_type="checkout_started",
                    plan_code="pro",
                    feature_key="active_classes",
                    database_path=path,
                )
                telemetry_valid = (
                    evt1.get("event_type") == "viewed"
                    and evt2.get("event_type") == "checkout_started"
                    and evt1.get("user_id") == user_a_id
                )

                # 6. Idempotent payment verification & subscription activation
                order = database.create_payment_order(
                    telegram_user=teacher_a,
                    purpose="Pro Subscription",
                    amount=149_000,
                    currency="IRT",
                    callback_token_hash="a" * 64,
                    is_sandbox=True,
                    product_code="pro",
                    subscription_days=30,
                )
                payment_id = int(order["id"])
                database.set_payment_pending(
                    payment_id=payment_id,
                    authority="AUTH_12345",
                    payment_url="https://sandbox.zarinpal.com/pg/StartPay/AUTH_12345",
                )

                # First activation
                p1 = database.mark_payment_paid(
                    payment_id=payment_id,
                    authority="AUTH_12345",
                    ref_id="REF_12345",
                    card_pan=None,
                    card_hash=None,
                    provider_code=100,
                    provider_message="Success",
                )
                # Duplicate activation retry (idempotent)
                p2 = database.mark_payment_paid(
                    payment_id=payment_id,
                    authority="AUTH_12345",
                    ref_id="REF_12345",
                    card_pan=None,
                    card_hash=None,
                    provider_code=100,
                    provider_message="Success",
                )
                with database.database_connection(path) as conn:
                    sub_count = conn.execute(
                        "SELECT COUNT(*) FROM subscriptions WHERE source_payment_id = ?",
                        (payment_id,),
                    ).fetchone()[0]
                idempotent_valid = (sub_count == 1 and p1["status"] == "paid" and p2["status"] == "paid")

                # Verify upgraded tier reflection
                access_pro_cls = check_feature_access(teacher_a.id, "active_classes", database_path=path)
                access_pro_exp = check_feature_access(teacher_a.id, "progress_reports_export", database_path=path)
                pro_reflected = (
                    access_pro_cls["plan_code"] == "pro"
                    and access_pro_cls["limit"] == 10
                    and access_pro_exp["allowed"] is True
                )

                # 7. Free teaching loop guarantee
                loop_guaranteed = can_complete_teaching_loop(teacher_b.id, database_path=path)

                # 8. Multi-tenant isolation
                with database.database_connection(path) as conn:
                    b_events = conn.execute(
                        "SELECT COUNT(*) FROM entitlement_events WHERE user_id = ?",
                        (user_b_id,),
                    ).fetchone()[0]
                isolation_valid = (b_events == 0)

                checks = {
                    "schema_v25_deployed": schema_valid,
                    "tier_capabilities_centralized": tier_valid,
                    "feature_access_checks_operational": feature_checks_valid,
                    "contextual_upgrade_prompts_outcome_oriented": no_tokens_in_prompts,
                    "commercial_funnel_telemetry_instrumented": telemetry_valid,
                    "idempotent_subscription_activation": idempotent_valid,
                    "pro_tier_reflected": pro_reflected,
                    "free_teaching_loop_guarantee_verified": loop_guaranteed,
                    "multi_tenant_isolation_verified": isolation_valid,
                }
                passed = all(checks.values())

                return {
                    "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "gate": "Day 25 — Package Paid Value Around Recurring Outcomes",
                    "schema_version": 25,
                    "checks": checks,
                    "passed": passed,
                    "engineering_status": "PASS" if passed else "FAIL",
                    "details": {
                        "user_a_id": user_a_id,
                        "payment_id": payment_id,
                        "pro_plan_classes_limit": access_pro_cls["limit"],
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
    parser = argparse.ArgumentParser(description="Evaluate TeacherOS Day 25 Entitlements.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = evaluate_day25()
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"DAY 25 ACCEPTANCE: {report['engineering_status']}")
    print(f"Report: {output_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
