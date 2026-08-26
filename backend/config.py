from __future__ import annotations

import os
import uuid
from datetime import timedelta, timezone, tzinfo
from pathlib import Path
from urllib.parse import urlparse

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

# Day 15 database setting. Leave this out of .env to use the default location:
# TeacherOS/database/teacheros.db
_database_path_value = os.getenv(
    "TEACHEROS_DATABASE_PATH",
    str(PROJECT_ROOT / "database" / "teacheros.db"),
).strip()
DATABASE_PATH = Path(_database_path_value).expanduser().resolve()


# Day 24 owner-only admin panel. Leave this unset until you run /myid in Telegram.
_admin_id_value = os.getenv("TEACHEROS_ADMIN_ID", "").strip()


# Day 25 Iranian payment foundation.
# Sandbox is ON by default so no real money is charged during development.
_SANDBOX_UUID = "11111111-1111-4111-8111-111111111111"
_zarinpal_sandbox_value = os.getenv("ZARINPAL_SANDBOX", "true").strip().lower()
ZARINPAL_SANDBOX = _zarinpal_sandbox_value not in {"0", "false", "no", "off"}
ZARINPAL_MERCHANT_ID = os.getenv(
    "ZARINPAL_MERCHANT_ID",
    _SANDBOX_UUID if ZARINPAL_SANDBOX else "",
).strip()
_local_payment_simulator_value = os.getenv(
    "TEACHEROS_LOCAL_PAYMENT_SIMULATOR",
    "true" if ZARINPAL_SANDBOX else "false",
).strip().lower()
LOCAL_PAYMENT_SIMULATOR = (
    ZARINPAL_SANDBOX
    and _local_payment_simulator_value not in {"0", "false", "no", "off"}
)
PAYMENT_CALLBACK_BASE_URL = os.getenv(
    "PAYMENT_CALLBACK_BASE_URL",
    "http://127.0.0.1:8080",
).strip().rstrip("/")
PAYMENT_SERVER_HOST = os.getenv("PAYMENT_SERVER_HOST", "127.0.0.1").strip()
_payment_server_port_value = os.getenv("PAYMENT_SERVER_PORT", "8080").strip()
_payment_test_amount_value = os.getenv("PAYMENT_TEST_AMOUNT_TOMAN", "10000").strip()


def _positive_int(value: str, fallback: int) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return fallback
    return parsed if parsed > 0 else fallback


PAYMENT_SERVER_PORT = _positive_int(_payment_server_port_value, 8080)
PAYMENT_TEST_AMOUNT_TOMAN = _positive_int(_payment_test_amount_value, 10000)
PAYMENT_CURRENCY = "IRT"  # Explicit toman units; avoids rial/toman ambiguity.

# Day 26 subscription plans. These are editable MVP launch defaults.
_free_limit_value = os.getenv("TEACHEROS_FREE_DAILY_LIMIT", "10").strip()
# Backward compatibility: the old shared duration is used as the Pro fallback only.
_legacy_subscription_days_value = os.getenv("TEACHEROS_SUBSCRIPTION_DAYS", "30").strip()
_pro_subscription_days_value = os.getenv(
    "TEACHEROS_PRO_SUBSCRIPTION_DAYS",
    _legacy_subscription_days_value or "30",
).strip()
_premium_subscription_days_value = os.getenv(
    "TEACHEROS_PREMIUM_SUBSCRIPTION_DAYS",
    "90",
).strip()
_pro_price_value = os.getenv("TEACHEROS_PRO_PRICE_TOMAN", "149000").strip()
_premium_price_value = os.getenv("TEACHEROS_PREMIUM_PRICE_TOMAN", "420000").strip()

FREE_DAILY_GENERATION_LIMIT = _positive_int(_free_limit_value, 10)
PRO_SUBSCRIPTION_DAYS = _positive_int(_pro_subscription_days_value, 30)
PREMIUM_SUBSCRIPTION_DAYS = _positive_int(_premium_subscription_days_value, 90)
# Deprecated alias retained so older custom modules do not break.
SUBSCRIPTION_DAYS = PRO_SUBSCRIPTION_DAYS
PRO_PRICE_TOMAN = _positive_int(_pro_price_value, 149000)
PREMIUM_PRICE_TOMAN = _positive_int(_premium_price_value, 420000)
USAGE_TIMEZONE = os.getenv("TEACHEROS_USAGE_TIMEZONE", "Asia/Tehran").strip() or "Asia/Tehran"
PREMIUM_OPENROUTER_MODEL = os.getenv("PREMIUM_OPENROUTER_MODEL", "").strip()

PLAN_NAMES = {"free": "Free", "pro": "Pro", "premium": "Premium"}
PLAN_PRICES_TOMAN = {"pro": PRO_PRICE_TOMAN, "premium": PREMIUM_PRICE_TOMAN}
PLAN_DURATIONS_DAYS = {
    "pro": PRO_SUBSCRIPTION_DAYS,
    "premium": PREMIUM_SUBSCRIPTION_DAYS,
}
PLAN_DAILY_LIMITS: dict[str, int | None] = {
    "free": FREE_DAILY_GENERATION_LIMIT,
    "pro": None,
    "premium": None,
}


def get_usage_timezone() -> tzinfo:
    """Return the configured timezone, with a safe Iran fallback on Windows.

    Some Windows Python installations do not include the IANA timezone database.
    Installing the ``tzdata`` package is preferred. For Asia/Tehran specifically,
    Iran currently uses UTC+03:30 year-round, so this fallback keeps quotas and
    expiry displays working even before tzdata is installed.
    """
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(USAGE_TIMEZONE)
    except Exception:
        if USAGE_TIMEZONE == "Asia/Tehran":
            return timezone(timedelta(hours=3, minutes=30), name="Asia/Tehran")
        raise


def plan_duration_days(plan_code: str) -> int:
    """Return the configured paid-plan duration."""
    try:
        return int(PLAN_DURATIONS_DAYS[plan_code])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Unknown TeacherOS plan.") from exc


def get_admin_telegram_id() -> int | None:
    """Return the configured positive Telegram owner ID, or None when unavailable."""
    if not _admin_id_value:
        return None
    try:
        admin_id = int(_admin_id_value)
    except ValueError:
        return None
    return admin_id if admin_id > 0 else None


def admin_setting_problem() -> str | None:
    """Explain why owner-only admin access is unavailable."""
    if not _admin_id_value:
        return "TEACHEROS_ADMIN_ID is not configured"
    if get_admin_telegram_id() is None:
        return "TEACHEROS_ADMIN_ID must be a positive whole number"
    return None


def is_admin_telegram_user(user_id: object) -> bool:
    """Return True only for the single Telegram account configured as owner."""
    admin_id = get_admin_telegram_id()
    return isinstance(user_id, int) and admin_id is not None and user_id == admin_id


def payment_setting_problem() -> str | None:
    """Return a human-readable payment configuration problem, if one exists."""
    try:
        uuid.UUID(ZARINPAL_MERCHANT_ID)
    except (ValueError, AttributeError):
        return "ZARINPAL_MERCHANT_ID must be a valid 36-character UUID"

    parsed = urlparse(PAYMENT_CALLBACK_BASE_URL)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "PAYMENT_CALLBACK_BASE_URL must be a complete http:// or https:// URL"

    if LOCAL_PAYMENT_SIMULATOR and not ZARINPAL_SANDBOX:
        return "TEACHEROS_LOCAL_PAYMENT_SIMULATOR can only be used in sandbox mode"

    if not ZARINPAL_SANDBOX:
        if ZARINPAL_MERCHANT_ID == _SANDBOX_UUID:
            return "Replace the sandbox merchant ID before enabling live payments"
        if parsed.scheme != "https":
            return "Live ZarinPal payments require an HTTPS callback URL"
        if parsed.hostname in {"127.0.0.1", "localhost"}:
            return "Live payments require a public callback domain, not localhost"

    if not PAYMENT_SERVER_HOST:
        return "PAYMENT_SERVER_HOST cannot be empty"
    if not 1 <= PAYMENT_SERVER_PORT <= 65535:
        return "PAYMENT_SERVER_PORT must be between 1 and 65535"
    if PAYMENT_TEST_AMOUNT_TOMAN < 1000:
        return "PAYMENT_TEST_AMOUNT_TOMAN must be at least 1000 toman"
    if FREE_DAILY_GENERATION_LIMIT < 1 or FREE_DAILY_GENERATION_LIMIT > 1000:
        return "TEACHEROS_FREE_DAILY_LIMIT must be between 1 and 1000"
    if PRO_SUBSCRIPTION_DAYS < 1 or PRO_SUBSCRIPTION_DAYS > 3660:
        return "TEACHEROS_PRO_SUBSCRIPTION_DAYS must be between 1 and 3660"
    if PREMIUM_SUBSCRIPTION_DAYS < 1 or PREMIUM_SUBSCRIPTION_DAYS > 3660:
        return "TEACHEROS_PREMIUM_SUBSCRIPTION_DAYS must be between 1 and 3660"
    if PRO_PRICE_TOMAN < 1000:
        return "TEACHEROS_PRO_PRICE_TOMAN must be at least 1000 toman"
    if PREMIUM_PRICE_TOMAN < 1000:
        return "TEACHEROS_PREMIUM_PRICE_TOMAN must be at least 1000 toman"
    if PREMIUM_PRICE_TOMAN <= PRO_PRICE_TOMAN:
        return "TEACHEROS_PREMIUM_PRICE_TOMAN must be greater than the Pro price"
    try:
        get_usage_timezone()
    except Exception:
        return (
            "TEACHEROS_USAGE_TIMEZONE must be a valid IANA timezone such as Asia/Tehran. "
            "On Windows, install timezone data with: python -m pip install tzdata"
        )
    return None


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

    payment_problem = payment_setting_problem()
    if payment_problem:
        raise RuntimeError(f"Payment configuration error: {payment_problem}")
