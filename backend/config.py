from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

# Prefer a project-root .env file, but also support backend/.env while you migrate.
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env", override=False)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "nvidia/nemotron-3-super-120b-a12b:free",
).strip()


def missing_settings() -> list[str]:
    missing: list[str] = []

    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")

    if not OPENROUTER_API_KEY:
        missing.append("OPENROUTER_API_KEY")

    if not OPENROUTER_MODEL:
        missing.append("OPENROUTER_MODEL")

    return missing


def validate_settings() -> None:
    missing = missing_settings()
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"Missing environment setting(s): {names}. "
            "Create TeacherOS/.env and add the missing values."
        )

