from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from database import get_user_entitlement, get_user_usage_summary, register_telegram_user
from home_ui import teacheros_home_text
from keyboards import start_menu_keyboard, usage_keyboard
from subscription_service import format_subscription_expiry

logger = logging.getLogger(__name__)


def _usage_message(summary: dict[str, Any], entitlement: dict[str, Any]) -> str:
    today = summary["today"]
    all_time = summary["all_time"]
    breakdown = summary["generation_breakdown"]
    limit = entitlement.get("daily_limit")
    if limit is None:
        limit_text = "Unlimited"
        remaining_text = "Unlimited"
    else:
        limit_text = str(limit)
        remaining_text = str(entitlement.get("remaining", 0))

    expiry_lines = ""
    if entitlement.get("expires_at"):
        mode = " · SANDBOX TEST" if entitlement.get("is_sandbox") else ""
        expiry_lines = f"\nValid until: {format_subscription_expiry(entitlement['expires_at'])}{mode}"

    return (
        "📊 My TeacherOS Usage\n\n"
        "Subscription\n"
        f"Plan: {entitlement['plan_name']}\n"
        f"Daily generation limit: {limit_text}\n"
        f"Remaining today: {remaining_text}"
        f"{expiry_lines}\n\n"
        f"Today ({entitlement['usage_timezone']})\n"
        f"🧠 Generations: {today['generations']}\n"
        f"📄 Word exports: {today['word_exports']}\n"
        f"🧾 PDF exports: {today['pdf_exports']}\n\n"
        "All time\n"
        f"🧠 Generations: {all_time['generations']}\n"
        f"📄 Word exports: {all_time['word_exports']}\n"
        f"🧾 PDF exports: {all_time['pdf_exports']}\n"
        f"📁 Currently saved: {summary['saved_materials']}\n"
        f"📅 Active days: {summary['active_days']}\n\n"
        "Generation breakdown\n"
        f"📚 Lessons: {breakdown['lesson']}\n"
        f"🎲 Activities: {breakdown['activity']}\n"
        f"📝 Worksheets: {breakdown['worksheet']}\n"
        f"✅ Assessments: {breakdown['assessment']}"
    )


async def _show_usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    try:
        register_telegram_user(user)
        summary = get_user_usage_summary(telegram_user_id=user.id)
        entitlement = get_user_entitlement(telegram_user_id=user.id)
        text = _usage_message(summary, entitlement)
    except Exception:
        logger.exception("Could not load user usage")
        text = (
            "❌ TeacherOS could not load your usage right now.\n\n"
            "Restart the bot and try /usage again."
        )

    if update.callback_query is not None:
        await update.callback_query.edit_message_text(text, reply_markup=usage_keyboard())
    elif update.message is not None:
        await update.message.reply_text(text, reply_markup=usage_keyboard())


async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the current user's private usage and subscription summary."""
    context.user_data.clear()
    await _show_usage(update, context)


async def usage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open, refresh, or leave the usage summary."""
    query = update.callback_query
    if query is None:
        return

    data = query.data or ""

    if data in {"usage_show", "usage_refresh"}:
        await query.answer()
        context.user_data.clear()
        await _show_usage(update, context)
        return

    if data == "usage_main":
        await query.answer()
        context.user_data.clear()
        await query.edit_message_text(
            teacheros_home_text(),
            reply_markup=start_menu_keyboard(),
        )
        return

    await query.answer("That usage button is no longer valid.", show_alert=True)
