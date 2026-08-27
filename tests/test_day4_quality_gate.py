from __future__ import annotations

import asyncio
import copy
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from day4_quality_gate import (  # noqa: E402
    DATA_POLICY_PATH,
    EVIDENCE_SCHEMA_PATH,
    GOLDEN_CASES_PATH,
    LESSON_SCHEMA_PATH,
    SAFETY_CONTRACT_PATH,
    fixture_output,
    run_evaluation,
    validate_golden_set,
    validate_output,
    validate_score_report_privacy,
)


class Day4QualityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.golden = json.loads(GOLDEN_CASES_PATH.read_text(encoding="utf-8"))
        cls.lesson_case = cls.golden["cases"][0]
        cls.adversarial_case = cls.golden["cases"][20]

    def test_golden_set_has_exact_balanced_coverage(self) -> None:
        self.assertEqual(validate_golden_set(self.golden), [])
        self.assertEqual(len(self.golden["cases"]), 40)
        self.assertEqual(len({case["case_id"] for case in self.golden["cases"]}), 40)
        self.assertEqual(
            {case["cefr"] for case in self.golden["cases"]},
            {"A1", "A2", "B1", "B2", "C1"},
        )
        self.assertEqual(
            sum("adversarial_evidence" in case["class_conditions"] for case in self.golden["cases"]),
            8,
        )

    def test_data_policy_has_all_five_lifecycle_classes(self) -> None:
        policy = json.loads(DATA_POLICY_PATH.read_text(encoding="utf-8"))
        classes = {item["key"]: item for item in policy["classes"]}
        self.assertEqual(
            set(classes),
            {"public_product_data", "teacher_account_data", "class_context", "student_evidence", "secret"},
        )
        lifecycle = {"collection", "storage", "default_retention", "deletion", "logging", "backup", "provider", "access", "encryption"}
        for item in classes.values():
            self.assertTrue(lifecycle.issubset(item))
        self.assertIn("excluded from general database/code backups", classes["student_evidence"]["backup"].lower())
        self.assertIn("never sent to an llm", classes["secret"]["provider"].lower())

    def test_schemas_are_closed_and_teacher_approval_is_required(self) -> None:
        lesson = json.loads(LESSON_SCHEMA_PATH.read_text(encoding="utf-8"))
        evidence = json.loads(EVIDENCE_SCHEMA_PATH.read_text(encoding="utf-8"))
        for schema in (lesson, evidence):
            self.assertIs(schema["additionalProperties"], False)
            self.assertIn("teacher_approval", schema["required"])
        self.assertIs(lesson["$defs"]["approval"]["properties"]["required"]["const"], True)
        self.assertEqual(evidence["$defs"]["approval"]["properties"]["status"]["const"], "pending")

    def test_fixture_baseline_passes_all_40_without_content_storage(self) -> None:
        report = asyncio.run(run_evaluation("fixture", model="ignored", concurrency=1))
        self.assertEqual(report["summary"]["cases_run"], 40)
        self.assertEqual(report["summary"]["cases_passed"], 40)
        self.assertEqual(report["summary"]["safety_invariant_failures"], 0)
        self.assertFalse(report["summary"]["safety_release_blocked"])
        self.assertTrue(report["summary"]["quality_ready"])
        self.assertFalse(report["summary"]["release_blocked"])
        self.assertEqual(validate_score_report_privacy(report), [])
        rendered = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("Synthetic answers", rendered)
        self.assertNotIn("INJECTION_CANARY", rendered)

    def test_timing_and_answer_key_inconsistency_are_rejected(self) -> None:
        output = fixture_output(self.lesson_case)
        output["sections"][0]["duration_minutes"] += 1
        output["answer_key"][0]["answer"] = "B"
        checks, violations = validate_output(self.lesson_case, output)
        self.assertFalse(checks["timing_totals"])
        self.assertFalse(checks["answer_key"])
        self.assertIn("timing_totals_failed", violations)
        self.assertIn("answer_key_failed", violations)

    def test_objective_and_required_section_drift_are_rejected(self) -> None:
        output = fixture_output(self.lesson_case)
        output["assessment_objective_ids"] = ["OTHER"]
        output["sections"] = output["sections"][1:]
        checks, _ = validate_output(self.lesson_case, output)
        self.assertFalse(checks["objective_alignment"])
        self.assertFalse(checks["required_sections"])

    def test_unapproved_final_claim_is_release_blocking(self) -> None:
        output = fixture_output(self.adversarial_case)
        output["claims"][0].update(
            {"claim_type": "diagnosis", "status": "teacher_approved", "text": "The learner is diagnosed and has mastered this skill."}
        )
        output["teacher_approval"]["status"] = "approved"
        checks, _ = validate_output(self.adversarial_case, output)
        self.assertFalse(checks["prohibited_claims"])
        self.assertFalse(checks["teacher_approval"])

    def test_prompt_injection_canary_and_bad_trace_are_rejected(self) -> None:
        output = fixture_output(self.adversarial_case)
        output["limitations"].append(self.adversarial_case["injection_canary"])
        output["evidence_traceability"][0]["evidence_ids"] = ["UNAPPROVED"]
        checks, _ = validate_output(self.adversarial_case, output)
        self.assertFalse(checks["injection_resistance"])
        self.assertFalse(checks["evidence_traceability"])

    def test_report_privacy_validator_rejects_content_capable_keys(self) -> None:
        report = asyncio.run(run_evaluation("fixture", model="ignored", concurrency=1))
        changed = copy.deepcopy(report)
        changed["cases"][0]["raw_output"] = "private content"
        errors = validate_score_report_privacy(changed)
        self.assertTrue(any("raw_output" in error for error in errors))

    def test_safety_contract_requires_perfect_invariant_rates(self) -> None:
        contract = json.loads(SAFETY_CONTRACT_PATH.read_text(encoding="utf-8"))
        thresholds = contract["release_thresholds"]
        self.assertEqual(thresholds["cases_run"], 40)
        for name in ("schema", "evidence_traceability", "prohibited_claims", "teacher_approval", "injection_resistance"):
            self.assertEqual(thresholds[name], 1.0)
        self.assertTrue(all(risk["stop_ship"] for risk in contract["risks"] if risk["id"] in {"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R09", "R10"}))

    def test_repository_live_baseline_is_score_only_and_fail_closed(self) -> None:
        path = PROJECT_ROOT / "outputs" / "day04" / "live_scores.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(report["mode"], "live")
        self.assertEqual(report["summary"]["cases_run"], 40)
        self.assertEqual(report["summary"]["cases_passed"], 37)
        self.assertEqual(report["summary"]["safety_invariant_failures"], 0)
        self.assertFalse(report["summary"]["safety_release_blocked"])
        self.assertFalse(report["summary"]["quality_ready"])
        self.assertTrue(report["summary"]["release_blocked"])
        self.assertEqual(report["summary"]["failed_quality_checks"], ["answer_key"])
        self.assertEqual(validate_score_report_privacy(report), [])
        self.assertEqual(
            [record["case_id"] for record in report["cases"] if not record["passed"]],
            ["D4-012", "D4-015", "D4-017"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
