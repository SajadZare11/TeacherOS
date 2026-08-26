from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from day3_contract_check import (  # noqa: E402
    PRODUCT_CONTRACT_PATH,
    REQUIRED_FUNNEL,
    SCREENS_PATH,
    evaluate_contract,
    validate_contract_data,
)


class Day3ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(PRODUCT_CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.screens = json.loads(SCREENS_PATH.read_text(encoding="utf-8"))

    def test_repository_contract_is_structurally_valid_but_honestly_blocked(self) -> None:
        result = evaluate_contract()
        self.assertEqual(result.structural_status, "VALID", result.errors)
        self.assertEqual(result.approval_status, "BLOCKED")
        self.assertEqual(result.metrics["day2_status"], "CLOSED")
        self.assertGreaterEqual(result.metrics["screens"], 30)
        self.assertTrue(any("G1_RESEARCH" in blocker for blocker in result.blockers))
        self.assertTrue(any("G2_COMPREHENSION" in blocker for blocker in result.blockers))

    def test_funnel_order_and_north_star_are_frozen(self) -> None:
        self.assertEqual(self.contract["activation_funnel"], REQUIRED_FUNNEL)
        self.assertEqual(self.contract["north_star"]["event"], "loop_completed")
        self.assertEqual(self.contract["north_star"]["deduplication_key"], "loop_id")

    def test_every_screen_has_escape_and_compact_callbacks(self) -> None:
        pattern = self.contract["callback_contract"]["regex"]
        import re

        compiled = re.compile(pattern)
        for screen in self.screens["screens"]:
            self.assertNotIn("/start", screen["back"].lower(), screen["id"])
            self.assertNotIn("type /start", screen["recovery"].lower(), screen["id"])
            self.assertTrue(screen["callbacks"], screen["id"])
            for callback in screen["callbacks"]:
                self.assertLessEqual(len(callback.encode("utf-8")), 64, callback)
                self.assertIsNotNone(compiled.fullmatch(callback), callback)

    def test_validator_rejects_event_without_privacy_class(self) -> None:
        changed = copy.deepcopy(self.contract)
        del changed["events"][0]["privacy_class"]
        errors = validate_contract_data(changed, self.screens)
        self.assertTrue(any("class_created is missing privacy_class" in error for error in errors))

    def test_all_class_intelligence_flags_default_off(self) -> None:
        self.assertTrue(self.contract["feature_flags"])
        self.assertTrue(all(flag["default"] is False for flag in self.contract["feature_flags"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
