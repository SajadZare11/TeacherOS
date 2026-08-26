from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from day2_research_gate import DEFAULT_WORKBOOK, evaluate_workbook


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCT_CONTRACT_PATH = PROJECT_ROOT / "contracts" / "day03" / "product_contract.json"
SCREENS_PATH = PROJECT_ROOT / "contracts" / "day03" / "screens.json"
PRD_PATH = PROJECT_ROOT / "docs" / "day03" / "TeacherOS_Product_Contract.md"
WIREFLOW_PATH = PROJECT_ROOT / "docs" / "day03" / "Telegram_Wireflow.md"

FROZEN_PROMISE = (
    "TeacherOS remembers each class, turns evidence into the next best teaching action, "
    "and produces classroom-ready English materials in minutes—under teacher control."
)
REQUIRED_FUNNEL = [
    "class_created",
    "class_resource_generated",
    "lesson_marked_taught",
    "outcome_saved",
    "evidence_approved",
    "followup_accepted",
    "loop_completed",
]
REQUIRED_FLAGS = {
    "classes_v1",
    "class_planning_v1",
    "teach_outcome_v1",
    "evidence_review_v1",
    "diagnosis_approval_v1",
    "followup_v1",
    "loop_analytics_v1",
    "class_entitlements_v1",
}
REQUIRED_DELETION_OBJECTS = {
    "generated resource",
    "raw evidence",
    "approved evidence summary",
    "class",
    "account",
    "analytics identity",
}
REQUIRED_GATES = {
    "G1_RESEARCH",
    "G2_COMPREHENSION",
    "G3_NAVIGATION",
    "G4_ANALYTICS",
    "G5_TRUST",
    "G6_VALUE",
    "G7_ROLLBACK",
}
REQUIRED_SCREEN_FIELDS = {
    "id",
    "title",
    "stage",
    "primary",
    "back",
    "empty",
    "retry",
    "confirmation",
    "recovery",
    "callbacks",
}
REQUIRED_STAGES = {
    "entry",
    "class setup",
    "plan",
    "teach",
    "outcome",
    "evidence",
    "approved diagnosis",
    "follow-up",
    "next lesson",
    "deletion",
    "recovery",
}


@dataclass(frozen=True)
class ContractResult:
    structural_status: str
    approval_status: str
    metrics: dict[str, int | str]
    errors: list[str]
    blockers: list[str]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    return value


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_contract_data(
    contract: dict[str, Any],
    screen_contract: dict[str, Any],
) -> list[str]:
    errors: list[str] = []

    if contract.get("product_promise") != FROZEN_PROMISE:
        errors.append("Product promise does not match the frozen Day 3 promise exactly.")

    privacy_classes = contract.get("privacy_classes")
    if not isinstance(privacy_classes, dict) or not privacy_classes:
        errors.append("privacy_classes must be a non-empty object.")
        privacy_names: set[str] = set()
    else:
        privacy_names = set(privacy_classes)
        for name, definition in privacy_classes.items():
            if not _nonempty(name) or not _nonempty(definition):
                errors.append("Every privacy class needs a non-empty name and definition.")

    analytics_rules = contract.get("analytics_rules")
    if not isinstance(analytics_rules, dict):
        errors.append("analytics_rules must be an object.")
        prohibited: set[str] = set()
    else:
        prohibited_raw = analytics_rules.get("prohibited_properties", [])
        prohibited = set(prohibited_raw) if isinstance(prohibited_raw, list) else set()
        for field in ("timestamp_standard", "identity", "retention", "late_or_duplicate_policy"):
            if not _nonempty(analytics_rules.get(field)):
                errors.append(f"analytics_rules.{field} is required.")
        if len(prohibited) < 8:
            errors.append("Analytics prohibited_properties must explicitly cover private content and identifiers.")

    events = contract.get("events")
    if not isinstance(events, list):
        errors.append("events must be a list.")
        events = []
    event_names = [event.get("name") for event in events if isinstance(event, dict)]
    if len(event_names) != len(set(event_names)):
        errors.append("Analytics event names must be unique.")
    missing_events = [name for name in REQUIRED_FUNNEL if name not in event_names]
    if missing_events:
        errors.append("Missing required funnel events: " + ", ".join(missing_events))
    if contract.get("activation_funnel") != REQUIRED_FUNNEL:
        errors.append("activation_funnel must preserve the frozen seven-event order.")
    for event in events:
        if not isinstance(event, dict):
            errors.append("Every event must be an object.")
            continue
        name = str(event.get("name") or "unnamed event")
        for field in ("definition", "timestamp", "owner", "privacy_class"):
            if not _nonempty(event.get(field)):
                errors.append(f"{name} is missing {field}.")
        if "UTC" not in str(event.get("timestamp") or ""):
            errors.append(f"{name} timestamp must explicitly identify UTC.")
        if event.get("privacy_class") not in privacy_names:
            errors.append(f"{name} uses an undefined privacy class.")
        required = event.get("required_properties")
        allowed = event.get("allowed_properties")
        if not isinstance(required, list) or not required:
            errors.append(f"{name} needs required_properties.")
            required = []
        if not isinstance(allowed, list):
            errors.append(f"{name} needs allowed_properties, even when empty.")
            allowed = []
        missing_common = {"event_id", "user_id", "occurred_at"} - set(required)
        if missing_common:
            errors.append(f"{name} is missing common required properties: {', '.join(sorted(missing_common))}.")
        leaked = prohibited.intersection(set(required) | set(allowed))
        if leaked:
            errors.append(f"{name} permits prohibited analytics properties: {', '.join(sorted(leaked))}.")

    north_star = contract.get("north_star")
    if not isinstance(north_star, dict):
        errors.append("north_star must be an object.")
    else:
        if north_star.get("metric") != "weekly_completed_teaching_loops":
            errors.append("North-star metric must be weekly_completed_teaching_loops.")
        if north_star.get("event") != "loop_completed":
            errors.append("North-star event must be loop_completed.")
        for field in ("definition", "unit", "deduplication_key", "reporting_timezone", "owner", "privacy_class"):
            if not _nonempty(north_star.get(field)):
                errors.append(f"north_star.{field} is required.")

    callback_contract = contract.get("callback_contract")
    callback_regex: re.Pattern[str] | None = None
    callback_limit = 64
    if not isinstance(callback_contract, dict):
        errors.append("callback_contract must be an object.")
    else:
        callback_limit = callback_contract.get("transport_limit_bytes", 0)
        if callback_limit != 64:
            errors.append("Telegram callback transport limit must be 64 bytes.")
        try:
            callback_regex = re.compile(str(callback_contract.get("regex") or ""))
        except re.error as exc:
            errors.append(f"Callback regex is invalid: {exc}")
        navigation = callback_contract.get("navigation")
        for field in ("back_rule", "stale_rule", "security_rule", "idempotency_rule"):
            if not isinstance(navigation, dict) or not _nonempty(navigation.get(field)):
                errors.append(f"callback_contract.navigation.{field} is required.")
        examples = callback_contract.get("examples", [])
        if not isinstance(examples, list) or not examples:
            errors.append("callback_contract.examples must not be empty.")
        else:
            for value in examples:
                _validate_callback(value, callback_regex, callback_limit, "callback example", errors)

    screens = screen_contract.get("screens")
    if not isinstance(screens, list):
        errors.append("screens must be a list.")
        screens = []
    screen_ids: list[str] = []
    stages: set[str] = set()
    for screen in screens:
        if not isinstance(screen, dict):
            errors.append("Every screen must be an object.")
            continue
        screen_id = str(screen.get("id") or "unnamed screen")
        screen_ids.append(screen_id)
        stages.add(str(screen.get("stage") or ""))
        missing_fields = REQUIRED_SCREEN_FIELDS - set(screen)
        if missing_fields:
            errors.append(f"{screen_id} is missing fields: {', '.join(sorted(missing_fields))}.")
        for field in REQUIRED_SCREEN_FIELDS - {"callbacks"}:
            if field in screen and not _nonempty(screen.get(field)):
                errors.append(f"{screen_id}.{field} must be non-empty.")
        back_text = str(screen.get("back") or "").lower()
        recovery_text = str(screen.get("recovery") or "").lower()
        if "/start" in back_text:
            errors.append(f"{screen_id} requires /start as its Back path.")
        if "type /start" in recovery_text:
            errors.append(f"{screen_id} requires /start for recovery.")
        callbacks = screen.get("callbacks")
        if not isinstance(callbacks, list) or not callbacks:
            errors.append(f"{screen_id} must define at least one callback.")
        else:
            for value in callbacks:
                _validate_callback(value, callback_regex, callback_limit, screen_id, errors)
    if len(screen_ids) != len(set(screen_ids)):
        errors.append("Screen IDs must be unique.")
    if len(screens) < 30:
        errors.append("The flagship screen catalog must contain at least 30 explicit states.")
    missing_stages = REQUIRED_STAGES - stages
    if missing_stages:
        errors.append("Screen catalog is missing stages: " + ", ".join(sorted(missing_stages)))

    flags = contract.get("feature_flags")
    if not isinstance(flags, list):
        errors.append("feature_flags must be a list.")
        flags = []
    flag_keys = {str(flag.get("key")) for flag in flags if isinstance(flag, dict)}
    if flag_keys != REQUIRED_FLAGS:
        errors.append("Feature flag set does not match the required class-intelligence flags.")
    for flag in flags:
        if not isinstance(flag, dict):
            errors.append("Every feature flag must be an object.")
            continue
        key = str(flag.get("key") or "unnamed flag")
        if flag.get("default") is not False:
            errors.append(f"{key} must default to false.")
        for field in ("owner", "rollout", "rollback"):
            if not _nonempty(flag.get(field)):
                errors.append(f"{key} is missing {field}.")
        dependencies = flag.get("depends_on")
        if not isinstance(dependencies, list):
            errors.append(f"{key}.depends_on must be a list.")
        else:
            unknown = set(dependencies) - flag_keys
            if unknown:
                errors.append(f"{key} has unknown dependencies: {', '.join(sorted(unknown))}.")

    entitlements = contract.get("entitlements")
    if not isinstance(entitlements, dict):
        errors.append("entitlements must be an object.")
    else:
        if entitlements.get("status") != "pricing_hypothesis_not_validated":
            errors.append("Class entitlements must remain labeled as an unvalidated pricing hypothesis.")
        if "10" not in str(entitlements.get("baseline_preserved") or ""):
            errors.append("Entitlements must preserve the current Free 10-generation baseline.")
        if not isinstance(entitlements.get("rules"), list) or len(entitlements["rules"]) < 4:
            errors.append("Entitlements must define enforcement, downgrade, quota, and sandbox rules.")

    deletion = contract.get("deletion")
    if not isinstance(deletion, list):
        errors.append("deletion must be a list.")
        deletion = []
    deletion_objects = {str(rule.get("object")) for rule in deletion if isinstance(rule, dict)}
    missing_deletions = REQUIRED_DELETION_OBJECTS - deletion_objects
    if missing_deletions:
        errors.append("Deletion matrix is missing: " + ", ".join(sorted(missing_deletions)))
    for rule in deletion:
        if not isinstance(rule, dict):
            errors.append("Every deletion rule must be an object.")
            continue
        name = str(rule.get("object") or "unnamed deletion object")
        for field in ("actor", "confirmation", "effect", "recovery", "sla"):
            if not _nonempty(rule.get(field)):
                errors.append(f"Deletion rule {name} is missing {field}.")

    gates = contract.get("release_gates")
    if not isinstance(gates, list):
        errors.append("release_gates must be a list.")
        gates = []
    gate_ids = {str(gate.get("id")) for gate in gates if isinstance(gate, dict)}
    if gate_ids != REQUIRED_GATES:
        errors.append("Release gate set does not match the required seven gates.")
    for gate in gates:
        if not isinstance(gate, dict):
            errors.append("Every release gate must be an object.")
            continue
        gate_id = str(gate.get("id") or "unnamed gate")
        for field in ("owner", "status", "criterion", "evidence"):
            if not _nonempty(gate.get(field)):
                errors.append(f"{gate_id} is missing {field}.")

    measures = contract.get("governing_measures")
    expected_measures = {
        "activation",
        "weekly_completed_teaching_loops",
        "verified_time_saved",
        "trust",
        "retention",
        "paid_conversion",
    }
    if not isinstance(measures, list) or set(measures) != expected_measures:
        errors.append("governing_measures must contain exactly the six Day 3 approval measures.")
    return errors


def _validate_callback(
    value: object,
    pattern: re.Pattern[str] | None,
    byte_limit: int,
    source: str,
    errors: list[str],
) -> None:
    if not isinstance(value, str):
        errors.append(f"{source} has a non-string callback.")
        return
    if len(value.encode("utf-8")) > byte_limit:
        errors.append(f"{source} callback exceeds {byte_limit} bytes: {value}")
    if pattern is not None and pattern.fullmatch(value) is None:
        errors.append(f"{source} callback does not match the compact contract: {value}")


def evaluate_contract(
    product_path: Path = PRODUCT_CONTRACT_PATH,
    screens_path: Path = SCREENS_PATH,
) -> ContractResult:
    errors: list[str] = []
    blockers: list[str] = []
    try:
        contract = _load_json(product_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return ContractResult("INVALID", "BLOCKED", {}, [str(exc)], ["Structural contract is invalid."])
    try:
        screen_contract = _load_json(screens_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return ContractResult("INVALID", "BLOCKED", {}, [str(exc)], ["Structural contract is invalid."])

    errors.extend(validate_contract_data(contract, screen_contract))
    for path in (PRD_PATH, WIREFLOW_PATH):
        if not path.is_file() or path.stat().st_size < 1000:
            errors.append(f"Required Day 3 document is missing or incomplete: {path.relative_to(PROJECT_ROOT)}")

    try:
        day2 = evaluate_workbook(DEFAULT_WORKBOOK)
    except Exception as exc:  # gate must fail closed on unreadable evidence
        day2_status = "ERROR"
        blockers.append(f"Day 2 evidence could not be evaluated: {exc}")
    else:
        day2_status = day2.status
        if day2.status != "OPEN":
            blockers.append(
                "G1_RESEARCH: Day 2 gate is CLOSED; target segment, jobs, and product mappings are not validated."
            )

    gates = contract.get("release_gates", [])
    gate_statuses = {
        str(gate.get("id")): str(gate.get("status"))
        for gate in gates
        if isinstance(gate, dict)
    }
    if gate_statuses.get("G2_COMPREHENSION") != "passed":
        blockers.append(
            "G2_COMPREHENSION: no de-identified record shows an eligible teacher passed the unaided wireflow test."
        )

    metrics: dict[str, int | str] = {
        "events": len(contract.get("events", [])),
        "funnel_events": len(contract.get("activation_funnel", [])),
        "screens": len(screen_contract.get("screens", [])),
        "feature_flags": len(contract.get("feature_flags", [])),
        "deletion_rules": len(contract.get("deletion", [])),
        "release_gates": len(gates),
        "day2_status": day2_status,
    }
    structural_status = "VALID" if not errors else "INVALID"
    approval_status = "READY" if not errors and not blockers else "BLOCKED"
    if errors:
        blockers.insert(0, "Structural contract errors must be fixed before approval.")
    return ContractResult(structural_status, approval_status, metrics, errors, blockers)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the TeacherOS Day 3 product contract.")
    parser.add_argument("--product", type=Path, default=PRODUCT_CONTRACT_PATH)
    parser.add_argument("--screens", type=Path, default=SCREENS_PATH)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--require-approval",
        action="store_true",
        help="Exit nonzero while research or teacher-comprehension gates remain blocked.",
    )
    args = parser.parse_args()
    result = evaluate_contract(args.product.resolve(), args.screens.resolve())
    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        print(f"DAY 3 CONTRACT: {result.structural_status}")
        print(f"DAY 3 APPROVAL: {result.approval_status}")
        for name, value in result.metrics.items():
            print(f"- {name}: {value}")
        if result.errors:
            print("\nStructural errors:")
            for error in result.errors:
                print(f"- {error}")
        if result.blockers:
            print("\nApproval blockers:")
            for blocker in result.blockers:
                print(f"- {blocker}")

    exit_code = 0
    if result.structural_status != "VALID":
        exit_code = 1
    elif args.require_approval and result.approval_status != "READY":
        exit_code = 1
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
