from __future__ import annotations

import ast
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from config import (
    FREE_DAILY_GENERATION_LIMIT,
    LOCAL_PAYMENT_SIMULATOR,
    PAYMENT_CALLBACK_BASE_URL,
    PAYMENT_SERVER_HOST,
    PAYMENT_SERVER_PORT,
    PREMIUM_OPENROUTER_MODEL,
    PREMIUM_PRICE_TOMAN,
    PREMIUM_SUBSCRIPTION_DAYS,
    PRO_PRICE_TOMAN,
    PRO_SUBSCRIPTION_DAYS,
    USAGE_TIMEZONE,
    ZARINPAL_SANDBOX,
    admin_setting_problem,
    missing_settings,
    payment_setting_problem,
)
from database import database_healthcheck
from prompt_loader import validate_prompt_files

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
WEBSITE_DIR = PROJECT_ROOT / "website"
REQUIREMENTS_PATH = PROJECT_ROOT / "requirements.txt"

_REQUIRED_REQUIREMENTS = {
    "python-telegram-bot",
    "openai",
    "python-dotenv",
    "python-docx",
    "reportlab",
    "tzdata",
    "openpyxl",
}


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "NOT INSTALLED"


def _validate_requirements_file() -> list[str]:
    errors: list[str] = []
    if not REQUIREMENTS_PATH.is_file():
        return ["requirements.txt is missing from the project root"]

    raw = REQUIREMENTS_PATH.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [
            "requirements.txt is not UTF-8. Replace it with the Day 29 version before running pip."
        ]

    if "\x00" in text:
        errors.append(
            "requirements.txt contains UTF-16 null bytes. Replace it with the Day 29 UTF-8 version."
        )
        return errors

    declared: set[str] = set()
    for line in text.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        name = re.split(r"[<>=!~\[]", clean, maxsplit=1)[0].strip().lower()
        if name:
            declared.add(name)

    missing = sorted(_REQUIRED_REQUIREMENTS - declared)
    if missing:
        errors.append("requirements.txt is missing: " + ", ".join(missing))
    return errors


def _validate_python_sources() -> tuple[int, list[str]]:
    files = sorted(BACKEND_DIR.glob("*.py")) + sorted(WEBSITE_DIR.glob("*.py"))
    errors: list[str] = []
    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append(f"Python source check failed for {path.relative_to(PROJECT_ROOT)}: {exc}")
    return len(files), errors


def _callback_length_errors() -> list[str]:
    """Check Telegram callback payloads without importing telegram."""
    path = BACKEND_DIR / "keyboards.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"Could not inspect Telegram callback data: {exc}"]

    errors: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callback_node: ast.AST | None = None
        for keyword in node.keywords:
            if keyword.arg == "callback_data":
                callback_node = keyword.value
                break
        if callback_node is None:
            continue

        estimated: str | None = None
        if isinstance(callback_node, ast.Constant) and isinstance(callback_node.value, str):
            estimated = callback_node.value
        elif isinstance(callback_node, ast.JoinedStr):
            pieces: list[str] = []
            for value in callback_node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    pieces.append(value.value)
                else:
                    names = {
                        child.id
                        for child in ast.walk(value)
                        if isinstance(child, ast.Name)
                    }
                    if any(name.endswith("_id") or name == "material_id" for name in names):
                        estimate = 19  # signed 64-bit SQLite / Telegram identifier
                    elif "page" in names or "index" in names:
                        estimate = 10
                    elif "selected_filter" in names:
                        estimate = 10  # "assessment" is the longest current filter
                    else:
                        estimate = 20
                    pieces.append("9" * estimate)
            estimated = "".join(pieces)

        if estimated is not None and len(estimated.encode("utf-8")) > 64:
            errors.append(
                f"Telegram callback_data may exceed 64 bytes near keyboards.py line {node.lineno}"
            )
    return errors


def _validate_website_config() -> list[str]:
    config_path = WEBSITE_DIR / "site-config.js"
    if not config_path.is_file():
        return ["website/site-config.js is missing"]
    try:
        text = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"Could not read website/site-config.js: {exc}"]

    match = re.search(r'telegramBotUrl\s*:\s*["\']([^"\']+)["\']', text)
    if match is None:
        return ["website/site-config.js does not define telegramBotUrl"]
    url = match.group(1).strip()
    username_match = re.fullmatch(r"https://t\.me/([A-Za-z0-9_]{5,32})/?", url)
    if username_match is None:
        return ["website Telegram URL must look like https://t.me/Teacheros1_bot"]
    if not username_match.group(1).lower().endswith("bot"):
        return ["website Telegram username must end with bot"]
    return []


def main() -> None:
    # Windows terminals commonly default to cp1252 while diagnostics include
    # intentional check-mark and warning symbols.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("TeacherOS project check\n")
    packages = {
        "python-telegram-bot": package_version("python-telegram-bot"),
        "openai": package_version("openai"),
        "python-dotenv": package_version("python-dotenv"),
        "python-docx": package_version("python-docx"),
        "reportlab": package_version("reportlab"),
        "tzdata": package_version("tzdata"),
        "openpyxl": package_version("openpyxl"),
    }

    for name, installed_version in packages.items():
        print(f"{name}: {installed_version}")
    print()

    errors: list[str] = []
    for name, installed_version in packages.items():
        if installed_version == "NOT INSTALLED":
            errors.append(
                f"Python package not installed: {name}. "
                "Run: python -m pip install -r requirements.txt"
            )

    requirement_errors = _validate_requirements_file()
    if requirement_errors:
        errors.extend(requirement_errors)
    else:
        print("✅ requirements.txt is valid UTF-8 and contains all required packages")

    source_count, source_errors = _validate_python_sources()
    if source_errors:
        errors.extend(source_errors)
    else:
        print(f"✅ Python syntax check passed ({source_count} files)")

    callback_errors = _callback_length_errors()
    if callback_errors:
        errors.extend(callback_errors)
    else:
        print("✅ Telegram callback payloads are within the 64-byte limit")

    website_errors = _validate_website_config()
    if website_errors:
        errors.extend(website_errors)
    else:
        print("✅ Website Telegram link is configured")

    missing = missing_settings()
    if missing:
        errors.append("Missing .env values: " + ", ".join(missing))
    else:
        print("✅ .env settings found")

    admin_problem = admin_setting_problem()
    if admin_problem:
        print(f"⚠️ Admin panel locked: {admin_problem}")
        print("   Start the bot, send /myid, then add TEACHEROS_ADMIN_ID to .env.")
    else:
        print("✅ Admin owner ID configured")

    payment_problem = payment_setting_problem()
    if payment_problem:
        errors.append(f"Payment configuration: {payment_problem}")
    else:
        mode = "SANDBOX (no real charge)" if ZARINPAL_SANDBOX else "LIVE"
        print(f"✅ ZarinPal payment foundation configured: {mode}")
        print(f"   Callback URL: {PAYMENT_CALLBACK_BASE_URL}")
        print(f"   Local server: {PAYMENT_SERVER_HOST}:{PAYMENT_SERVER_PORT}")
        if ZARINPAL_SANDBOX and LOCAL_PAYMENT_SIMULATOR:
            print("   Sandbox checkout: TeacherOS local simulator (recommended for development)")
        elif ZARINPAL_SANDBOX:
            print("   Sandbox checkout: ZarinPal external sandbox")
        print(
            "✅ Subscription plans configured "
            f"(Free: {FREE_DAILY_GENERATION_LIMIT}/day, "
            f"Pro: {PRO_PRICE_TOMAN:,} toman / {PRO_SUBSCRIPTION_DAYS} days, "
            f"Premium: {PREMIUM_PRICE_TOMAN:,} toman / {PREMIUM_SUBSCRIPTION_DAYS} days)"
        )
        print(f"   Usage timezone: {USAGE_TIMEZONE}")
        if PREMIUM_OPENROUTER_MODEL:
            print(f"   Premium model routing: {PREMIUM_OPENROUTER_MODEL}")
        else:
            print("   Premium model routing: entitlement only (optional model not configured)")

    try:
        validate_prompt_files()
        print("✅ Required prompt files found")
    except Exception as exc:
        errors.append(str(exc))

    try:
        status = database_healthcheck()
        print(
            "✅ Database ready "
            f"(schema v{status['schema_version']}, "
            f"users: {status['users']}, materials: {status['materials']}, "
            f"usage events: {status['usage_events']}, payments: {status['payments']}, "
            f"subscriptions: {status['subscriptions']}, feedback: {status['feedback']})"
        )
        print(f"   {status['path']}")
    except Exception as exc:
        errors.append(f"Database check failed: {exc}")

    if errors:
        print("\n❌ Problems found:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print("\n✅ TeacherOS project check passed")


if __name__ == "__main__":
    main()
