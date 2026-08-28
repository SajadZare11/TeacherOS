from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import is_admin_telegram_user
from database import get_user_entitlement, register_telegram_user
from home_ui import teacheros_home_text
from keyboards import account_home_keyboard, account_plan_keyboard, start_menu_keyboard
from subscription_service import format_subscription_expiry

logger = logging.getLogger(__name__)


def _plan_name_fa(value: object) -> str:
    return {"Free": "رایگان", "Pro": "Pro", "Premium": "Premium"}.get(
        str(value or "Free"),
        str(value or "رایگان"),
    )


def _account_home_text(entitlement: dict[str, Any]) -> str:
    remaining = entitlement.get("remaining")
    remaining_text = "نامحدود" if remaining is None else str(remaining)
    return (
        "👤 حساب کاربری TeacherOS\n\n"
        f"پلن فعلی: {_plan_name_fa(entitlement['plan_name'])}\n"
        f"تعداد تولید باقی‌مانده امروز: {remaining_text}\n\n"
        "از این بخش می‌توانید مصرف، پلن، کتابخانه و تنظیمات حساب خود را مدیریت کنید."
    )


def _plan_text(entitlement: dict[str, Any]) -> str:
    daily_limit = entitlement.get("daily_limit")
    limit_text = "نامحدود" if daily_limit is None else str(daily_limit)
    remaining = entitlement.get("remaining")
    remaining_text = "نامحدود" if remaining is None else str(remaining)

    lines = [
        "🪪 پلن من",
        "",
        f"پلن: {_plan_name_fa(entitlement['plan_name'])}",
        f"سقف تولید روزانه: {limit_text}",
        f"مصرف امروز: {int(entitlement.get('used_today') or 0)}",
        f"باقی‌مانده امروز: {remaining_text}",
    ]

    if entitlement.get("expires_at"):
        mode = " · آزمایشی" if entitlement.get("is_sandbox") else ""
        lines.append(
            f"اعتبار تا: {format_subscription_expiry(entitlement['expires_at'])}{mode}"
        )
    else:
        lines.append("اشتراک پولی فعالی ندارید.")

    if entitlement.get("priority"):
        lines.append("دسترسی اولویت‌دار: فعال")

    return "\n".join(lines)


async def _safe_edit(query: Any, text: str, *, reply_markup: Any) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _load_entitlement(update: Update) -> dict[str, Any] | None:
    user = update.effective_user
    if user is None or not isinstance(getattr(user, "id", None), int):
        return None
    register_telegram_user(user)
    return get_user_entitlement(telegram_user_id=user.id)


async def account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open the Account hub, current-plan page, or compact main menu."""
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or not isinstance(getattr(user, "id", None), int):
        return

    data = query.data or ""
    await query.answer()
    context.user_data.clear()

    try:
        if data == "account_home":
            entitlement = await _load_entitlement(update)
            if entitlement is None:
                return
            await _safe_edit(
                query,
                _account_home_text(entitlement),
                reply_markup=account_home_keyboard(
                    show_admin=is_admin_telegram_user(user.id)
                ),
            )
            return

        if data == "account_plan":
            entitlement = await _load_entitlement(update)
            if entitlement is None:
                return
            await _safe_edit(
                query,
                _plan_text(entitlement),
                reply_markup=account_plan_keyboard(),
            )
            return

        if data == "account_main":
            await _safe_edit(
                query,
                teacheros_home_text(),
                reply_markup=start_menu_keyboard(),
            )
            return
    except Exception:
        logger.exception("Could not open TeacherOS account panel")
        await _safe_edit(
            query,
            "❌ حساب کاربری در حال حاضر بارگذاری نشد.\n\n"
            "لطفاً ربات را دوباره راه‌اندازی و مجدداً تلاش کنید.",
            reply_markup=start_menu_keyboard(),
        )
        return

    await _safe_edit(
        query,
        "⚠️ این گزینه حساب کاربری دیگر در دسترس نیست.",
        reply_markup=account_home_keyboard(
            show_admin=is_admin_telegram_user(user.id)
        ),
    )
