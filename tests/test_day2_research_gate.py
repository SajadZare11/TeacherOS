from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from day2_research_gate import DEFAULT_WORKBOOK, _contains_private_locator, evaluate_workbook  # noqa: E402


class Day2ResearchGateTests(unittest.TestCase):
    def test_repository_workbook_is_complete_but_gate_is_honestly_closed(self) -> None:
        result = evaluate_workbook(DEFAULT_WORKBOOK)
        self.assertEqual(result.status, "CLOSED")
        self.assertEqual(result.metrics["feature_total"], 90)
        self.assertEqual(result.metrics["completed_eligible_interviews"], 0)
        self.assertEqual(result.metrics["confirmed_pilot_recruits"], 0)
        self.assertEqual(result.metrics["approved_or_deferred_features"], 57)
        self.assertTrue(any("at least 5" in blocker for blocker in result.blockers))
        self.assertTrue(any("10-15" in blocker for blocker in result.blockers))

    def test_private_locator_detection_catches_contact_data(self) -> None:
        self.assertTrue(_contains_private_locator("https://t.me/example_teacher"))
        self.assertTrue(_contains_private_locator("teacher@example.com"))
        self.assertTrue(_contains_private_locator("09123456789"))
        self.assertFalse(_contains_private_locator("P01 discussed weekly lesson planning."))


if __name__ == "__main__":
    unittest.main(verbosity=2)
