from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import OPENROUTER_MODEL, PREMIUM_OPENROUTER_MODEL, USAGE_TIMEZONE, get_usage_timezone
from database import get_user_entitlement
from feature_flags import feature_enabled


CLASS_PLAN_LIMITS: dict[str, int | None] = {
    "free": 1,
    "pro": 10,
    "premium": None,
}


def generation_access_for_user(telegram_user_id: int) -> dict[str, Any]:
    """Return the current plan/quota decision used before every OpenRouter call."""
    return get_user_entitlement(telegram_user_id=telegram_user_id)


def class_creation_access_for_user(
    telegram_user_id: int,
    database_path: "Path | None" = None,
) -> dict[str, Any]:
    """Return the one central class-limit decision used by every setup surface."""
    from entitlement_service import check_feature_access

    result = check_feature_access(telegram_user_id, "active_classes", database_path=database_path)
    return {
        "allowed": result["allowed"],
        "enforced": result["enforced"],
        "plan_code": result["plan_code"],
        "plan_name": result["plan_name"],
        "active_classes": result["current"],
        "class_limit": result["limit"],
        "upgrade_prompt": result["upgrade_prompt"],
    }


def generation_block_message(access: dict[str, Any]) -> str:
    """پیام ساده و فارسی برای پایان سهمیه روزانه پلن رایگان."""
    plan_name = {"Free": "رایگان", "Pro": "Pro", "Premium": "Premium"}.get(
        str(access.get("plan_name") or "Free"),
        str(access.get("plan_name") or "رایگان"),
    )
    limit = access.get("daily_limit")
    timezone_name = str(access.get("usage_timezone") or "Asia/Tehran")
    return (
        "⛔ سهمیه تولید امروز شما تمام شده است\n\n"
        f"پلن فعلی: {plan_name}\n"
        f"مصرف امروز: {int(access.get('used_today') or 0)} از {limit}\n\n"
        f"سهمیه رایگان در نیمه‌شب منطقه زمانی {timezone_name} دوباره فعال می‌شود. "
        "برای تولید نامحدود می‌توانید پلن Pro یا Premium را فعال کنید."
    )


def selected_openrouter_model(access: dict[str, Any]) -> str:
    """Route Premium users to an optional priority model when configured."""
    if bool(access.get("priority")) and PREMIUM_OPENROUTER_MODEL:
        return PREMIUM_OPENROUTER_MODEL
    return OPENROUTER_MODEL


def format_subscription_expiry(value: object) -> str:
    """Render stored UTC subscription timestamps in the user's Iran-first timezone."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    local = parsed.astimezone(get_usage_timezone())
    return local.strftime("%Y-%m-%d %H:%M") + f" ({USAGE_TIMEZONE})"
