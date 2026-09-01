"""Regression tests for the Day 29 stability and release gate contracts."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "offline-day29-token")
os.environ.setdefault("OPENROUTER_API_KEY", "offline-day29-key")

from day29_acceptance_check import evaluate_day29
from payment_server import _ReusableThreadingHTTPServer


class Day29StabilityTests(unittest.TestCase):
    def test_day29_acceptance_gate_passes(self) -> None:
        report = evaluate_day29()
        self.assertTrue(report["passed"], report["checks"])
        self.assertEqual(report["engineering_status"], "PASS")
        self.assertEqual(report["details"]["project_check_output"], "✅ Day 29 stability check passed")

    def test_requirements_are_decodable_as_utf8(self) -> None:
        requirements = (PROJECT_ROOT / "requirements.txt").read_bytes().decode("utf-8")
        self.assertNotIn("\x00", requirements)
        self.assertIn("python-telegram-bot", requirements)

    def test_payment_callback_server_allows_restart(self) -> None:
        self.assertTrue(_ReusableThreadingHTTPServer.allow_reuse_address)
        self.assertTrue(_ReusableThreadingHTTPServer.daemon_threads)


if __name__ == "__main__":
    unittest.main()
