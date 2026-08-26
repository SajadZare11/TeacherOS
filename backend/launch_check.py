from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path
from urllib.parse import urlparse

from check_project import (
    PROJECT_ROOT,
    _callback_length_errors,
    _validate_python_sources,
    _validate_requirements_file,
    _validate_website_config,
    package_version,
)
from config import (
    LOCAL_PAYMENT_SIMULATOR,
    PAYMENT_CALLBACK_BASE_URL,
    PREMIUM_PRICE_TOMAN,
    PREMIUM_SUBSCRIPTION_DAYS,
    PRO_PRICE_TOMAN,
    PRO_SUBSCRIPTION_DAYS,
    ZARINPAL_SANDBOX,
    admin_setting_problem,
    missing_settings,
    payment_setting_problem,
)
from database import database_healthcheck
from prompt_loader import validate_prompt_files

WEBSITE_DIR = PROJECT_ROOT / "website"
BACKUP_DIR = PROJECT_ROOT / "backups"
PUBLIC_SCAN_DIRS = (WEBSITE_DIR, PROJECT_ROOT / "docs", PROJECT_ROOT / "deploy")
REQUIRED_PUBLIC_FILES = (
    WEBSITE_DIR / "privacy.html",
    WEBSITE_DIR / "terms.html",
    PROJECT_ROOT / "backend" / "launch_info.py",
)
TOKEN_PATTERNS = (
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]{20,}\b", re.IGNORECASE),
)


def _website_number(name: str) -> int | None:
    config_path = WEBSITE_DIR / "site-config.js"
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(rf"\b{re.escape(name)}\s*:\s*(\d+)", text)
    return int(match.group(1)) if match else None


def _secret_scan() -> list[str]:
    problems: list[str] = []
    for directory in PUBLIC_SCAN_DIRS:
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".html", ".js", ".css", ".md", ".txt", ".conf", ".template"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if any(pattern.search(text) for pattern in TOKEN_PATTERNS):
                problems.append(f"Possible secret found in public file: {path.relative_to(PROJECT_ROOT)}")
    return problems


def _handler_checks() -> list[str]:
    path = PROJECT_ROOT / "backend" / "main.py"
    try:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"Could not inspect backend/main.py: {exc}"]

    required_fragments = (
        'CommandHandler("privacy", privacy_command)',
        'CommandHandler("terms", terms_command)',
        'CallbackQueryHandler(launch_info_callback, pattern=r"^info_")',
        ".post_init(post_init)",
    )
    return [f"Launch handler missing from backend/main.py: {fragment}" for fragment in required_fragments if fragment not in source]


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether TeacherOS is ready to launch.")
    parser.add_argument(
        "--mode",
        choices=("beta", "paid"),
        default="beta",
        help="beta allows sandbox payments; paid requires live ZarinPal and public HTTPS",
    )
    args = parser.parse_args()

    blockers: list[str] = []
    warnings: list[str] = []

    print(f"TeacherOS Day 30 launch check — {args.mode.upper()} mode\n")

    packages = ("python-telegram-bot", "openai", "python-dotenv", "python-docx", "reportlab", "tzdata")
    missing_packages = [name for name in packages if package_version(name) == "NOT INSTALLED"]
    if missing_packages:
        blockers.append("Missing Python packages: " + ", ".join(missing_packages))
    else:
        print("✅ Required Python packages are installed")

    blockers.extend(_validate_requirements_file())
    source_count, source_errors = _validate_python_sources()
    blockers.extend(source_errors)
    if not source_errors:
        print(f"✅ Python syntax passed ({source_count} files)")

    blockers.extend(_callback_length_errors())
    blockers.extend(_validate_website_config())
    blockers.extend(_handler_checks())

    for path in REQUIRED_PUBLIC_FILES:
        if not path.is_file() or path.stat().st_size == 0:
            blockers.append(f"Required launch file is missing or empty: {path.relative_to(PROJECT_ROOT)}")
    if not any("Required launch file" in problem for problem in blockers):
        print("✅ Privacy, terms, and launch-information files are present")

    settings = missing_settings()
    if settings:
        blockers.append("Missing .env values: " + ", ".join(settings))
    if admin_setting_problem():
        blockers.append("Admin owner is not configured: " + str(admin_setting_problem()))

    payment_problem = payment_setting_problem()
    if payment_problem:
        blockers.append("Payment configuration: " + payment_problem)

    if args.mode == "paid":
        parsed_callback = urlparse(PAYMENT_CALLBACK_BASE_URL)
        if ZARINPAL_SANDBOX:
            blockers.append("Paid launch requires ZARINPAL_SANDBOX=false")
        if LOCAL_PAYMENT_SIMULATOR:
            blockers.append("Paid launch requires TEACHEROS_LOCAL_PAYMENT_SIMULATOR=false")
        if parsed_callback.scheme != "https" or parsed_callback.hostname in {"127.0.0.1", "localhost", None}:
            blockers.append("Paid launch requires a public HTTPS PAYMENT_CALLBACK_BASE_URL")
    elif ZARINPAL_SANDBOX:
        warnings.append("Payments are still in sandbox. Beta users must not be told that a real charge will occur.")

    expected_site_values = {
        "proPriceToman": PRO_PRICE_TOMAN,
        "proDays": PRO_SUBSCRIPTION_DAYS,
        "premiumPriceToman": PREMIUM_PRICE_TOMAN,
        "premiumDays": PREMIUM_SUBSCRIPTION_DAYS,
    }
    for name, expected in expected_site_values.items():
        actual = _website_number(name)
        if actual != expected:
            blockers.append(f"Website {name} is {actual!r}; backend configuration is {expected}")
    if not any("Website " in problem for problem in blockers):
        print("✅ Website pricing matches backend subscription configuration")

    try:
        validate_prompt_files()
        print("✅ Prompt system is complete")
    except Exception as exc:
        blockers.append(str(exc))

    try:
        status = database_healthcheck()
        print(
            "✅ Database health passed "
            f"(users: {status['users']}, materials: {status['materials']}, feedback: {status['feedback']})"
        )
    except Exception as exc:
        blockers.append(f"Database health check failed: {exc}")

    backups = sorted(BACKUP_DIR.glob("teacheros_*.db"), key=lambda path: path.stat().st_mtime, reverse=True) if BACKUP_DIR.is_dir() else []
    if not backups:
        blockers.append("No launch backup found. Run: python backend/backup_teacheros.py --label prelaunch")
    else:
        print(f"✅ Launch backup found: {backups[0].name}")

    blockers.extend(_secret_scan())
    if not any("secret" in problem.lower() for problem in blockers):
        print("✅ No Telegram/OpenRouter secret pattern found in public launch files")

    for warning in warnings:
        print(f"⚠️ {warning}")

    if blockers:
        print("\n❌ Launch blockers:")
        for blocker in blockers:
            print(f"- {blocker}")
        raise SystemExit(1)

    print("\n✅ TeacherOS is ready for this launch mode")
    if args.mode == "beta":
        print("Launch status: FREE/BETA — do not collect real payments while sandbox is enabled.")
    else:
        print("Launch status: PAID — live payment prerequisites passed.")


if __name__ == "__main__":
    main()
