"""Regression tests for the Day 30 progressive launch gate."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day30-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day30-key")

from day30_acceptance_check import evaluate_day30


class Day30LaunchTests(unittest.TestCase):
    def test_day30_acceptance_gate_passes(self) -> None:
        report = evaluate_day30()
        self.assertTrue(report["passed"], report["checks"])
        self.assertEqual(report["engineering_status"], "PASS")
        self.assertIsNotNone(report["details"]["backup"])

    def test_launch_check_has_unicode_safe_console_output(self) -> None:
        source = (BACKEND_DIR / "launch_check.py").read_text(encoding="utf-8")
        self.assertIn('sys.stdout.reconfigure(encoding="utf-8", errors="replace")', source)

    def test_day30_feature_flags_are_explicit_in_production_template(self) -> None:
        env_text = (PROJECT_ROOT / "deploy" / "env.production.example.txt").read_text(encoding="utf-8")
        for name in (
            "TEACHEROS_FEATURE_CLASSES",
            "TEACHEROS_FEATURE_CONTINUITY",
            "TEACHEROS_FEATURE_EVIDENCE",
            "TEACHEROS_FEATURE_DIFFERENTIATION",
            "TEACHEROS_FEATURE_REPORTS",
            "TEACHEROS_FEATURE_ENTITLEMENTS",
        ):
            self.assertIn(f"{name}=true", env_text)

    def test_public_policy_pages_exist_and_are_linked(self) -> None:
        index = (PROJECT_ROOT / "website" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="privacy.html"', index)
        self.assertIn('href="terms.html"', index)
        self.assertTrue((PROJECT_ROOT / "website" / "privacy.html").is_file())
        self.assertTrue((PROJECT_ROOT / "website" / "terms.html").is_file())


if __name__ == "__main__":
    unittest.main()
