from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from config import (
    USAGE_TIMEZONE,
    admin_setting_problem,
    get_usage_timezone,
    is_admin_telegram_user,
)
from database import (
    get_admin_dashboard_summary,
    get_admin_feedback_summary,
    get_admin_payment_summary,
    get_admin_subscription_summary,
    grant_manual_subscription,
    revoke_user_subscriptions,
    update_feedback_status,
)
from home_ui import teacheros_home_text
from keyboards import admin_feedback_keyboard, admin_keyboard, start_menu_keyboard

logger = logging.getLogger(__name__)


def _updated_label() -> str:
    local_now = datetime.now(get_usage_timezone())
    return f"{local_now:%Y-%m-%d %H:%M} ({USAGE_TIMEZONE})"


def _overview_message(summary: dict[str, Any]) -> str:
    users = summary["users"]
    today = summary["today"]
    all_time = summary["all_time"]
    return (
        "🛡 TeacherOS Admin\n\n"
        f"Updated: {_updated_label()}\n\n"
        "Platform snapshot\n"
        f"👥 Registered users: {users['total']}\n"
        f"🟢 Active users today: {users['active_today']}\n"
        f"📁 Currently saved: {summary['saved_materials']}\n\n"
        f"Today ({USAGE_TIMEZONE})\n"
        f"🧠 Generations: {today['generations']}\n"
        f"📄 Word exports: {today['word_exports']}\n"
        f"🧾 PDF exports: {today['pdf_exports']}\n\n"
        "All time\n"
        f"🧠 Generations: {all_time['generations']}\n"
        f"📤 Total exports: {all_time['word_exports'] + all_time['pdf_exports']}"
    )


def _users_message(summary: dict[str, Any]) -> str:
    users = summary["users"]
    return (
        "👥 Admin — Users\n\n"
        f"Updated: {_updated_label()}\n\n"
        f"Total registered: {users['total']}\n\n"
        "New registrations\n"
        f"Today: {users['new_today']}\n"
        f"Last 7 days: {users['new_7_days']}\n"
        f"Last 30 days: {users['new_30_days']}\n\n"
        "Active users\n"
        f"Today: {users['active_today']}\n"
        f"Last 7 days: {users['active_7_days']}\n"
        f"Last 30 days: {users['active_30_days']}\n\n"
        "ℹ️ Active means the user opened or used a tracked TeacherOS feature."
    )


def _content_message(summary: dict[str, Any]) -> str:
    today = summary["today"]
    all_time = summary["all_time"]
    generated = summary["generation_breakdown"]
    saved = summary["saved_breakdown"]
    return (
        "📊 Admin — Product Usage\n\n"
        f"Updated: {_updated_label()}\n\n"
        f"Today ({USAGE_TIMEZONE})\n"
        f"🧠 Generations: {today['generations']}\n"
        f"📄 Word exports: {today['word_exports']}\n"
        f"🧾 PDF exports: {today['pdf_exports']}\n\n"
        "All-time generations\n"
        f"📚 Lessons: {generated['lesson']}\n"
        f"🎲 Activities: {generated['activity']}\n"
        f"📝 Worksheets: {generated['worksheet']}\n"
        f"✅ Assessments: {generated['assessment']}\n"
        f"Total: {all_time['generations']}\n\n"
        "All-time exports\n"
        f"📄 Word: {all_time['word_exports']}\n"
        f"🧾 PDF: {all_time['pdf_exports']}\n\n"
        "Currently saved\n"
        f"📚 Lessons: {saved['lesson']}\n"
        f"🎲 Activities: {saved['activity']}\n"
        f"📝 Worksheets: {saved['worksheet']}\n"
        f"✅ Assessments: {saved['assessment']}\n"
        f"Total: {summary['saved_materials']}"
    )


def _revenue_message(summary: dict[str, Any]) -> str:
    live = summary["live"]
    sandbox = summary["sandbox"]
    return (
        "💳 Admin — Payments\n\n"
        f"Updated: {_updated_label()}\n\n"
        "LIVE VERIFIED PAYMENTS\n"
        f"Paid today: {live['paid_today']}\n"
        f"Revenue today: {live['paid_amount_today']:,} تومان\n"
        f"Paid all time: {live['paid']}\n"
        f"Revenue all time: {live['paid_amount']:,} تومان\n"
        f"Pending: {live['pending']}\n"
        f"Failed/cancelled: {live['failed'] + live['cancelled']}\n\n"
        "SANDBOX TESTS\n"
        f"Verified tests: {sandbox['paid']}\n"
        f"Pending tests: {sandbox['pending']}\n"
        f"Failed/cancelled tests: {sandbox['failed'] + sandbox['cancelled']}\n\n"
        "Only server-verified live payments count as revenue. Sandbox amounts are never revenue. "
        "Verified plan payments activate subscriptions automatically."
    )


def _feedback_message(summary: dict[str, Any]) -> str:
    average = summary["average_rating"]
    average_text = "No ratings yet" if not summary["total"] else f"{average:.2f}/5"
    area_labels = {
        "lesson": "Lesson",
        "activity": "Activity",
        "worksheet": "Worksheet",
        "assessment": "Assessment",
        "library": "Library",
        "search": "Search",
        "account": "Account",
        "website": "Website",
        "other": "Overall",
    }

    lines = [
        "🧪 Admin — Beta Feedback",
        "",
        f"Updated: {_updated_label()}",
        "",
        f"Total reports: {summary['total']}",
        f"Average rating: {average_text}",
        f"New in last 7 days: {summary['last_7_days']}",
        f"Open: {summary['open']} · Reviewed: {summary['reviewed']} · Resolved: {summary['resolved']}",
    ]

    area_breakdown = summary.get("area_breakdown") or {}
    if area_breakdown:
        lines.extend(["", "Reports by area"] )
        for area, count in area_breakdown.items():
            lines.append(f"• {area_labels.get(area, str(area).title())}: {count}")

    recent = summary.get("recent") or []
    lines.extend(["", "Latest reports"] )
    if not recent:
        lines.append("No beta feedback has been submitted yet.")
        return "\n".join(lines)

    for item in recent:
        username = str(item.get("username") or "").strip()
        first_name = str(item.get("first_name") or "").strip()
        teacher = f"@{username}" if username else (first_name or f"Telegram {item['telegram_user_id']}")
        message = " ".join(str(item.get("message") or "").split())
        if not message:
            message = "Quick rating — no written comment."
        elif len(message) > 180:
            message = message[:177].rstrip() + "..."
        status_icon = {"open": "🔴", "reviewed": "👀", "resolved": "✅"}.get(
            str(item.get("status") or "open"), "•"
        )
        lines.extend(
            [
                "",
                f"{status_icon} #{item['id']} · {item['rating']}/5 · {area_labels.get(str(item['area']), str(item['area']).title())}",
                f"From: {teacher}",
                message,
            ]
        )

    return "\n".join(lines)


def _plans_message(summary: dict[str, Any]) -> str:
    active = summary["active"]
    live = summary["live"]
    sandbox = summary["sandbox"]
    manual = summary["manual"]
    return (
        "💎 Admin — Subscriptions\n\n"
        f"Updated: {_updated_label()}\n\n"
        "Effective user plans\n"
        f"Free: {active['free']}\n"
        f"Pro: {active['pro']}\n"
        f"Premium: {active['premium']}\n\n"
        "Live paid\n"
        f"Pro: {live['pro']} · Premium: {live['premium']}\n\n"
        "Sandbox tests\n"
        f"Pro: {sandbox['pro']} · Premium: {sandbox['premium']}\n\n"
        "Manual owner grants\n"
        f"Pro: {manual['pro']} · Premium: {manual['premium']}\n\n"
        f"Expiring in 7 days: {summary['expiring_7_days']}\n"
        f"All activations: {summary['total_activations']}\n"
        f"Revoked records: {summary['revoked']}\n\n"
        "Owner commands\n"
        "/admin_grant TELEGRAM_ID pro 30\n"
        "/admin_grant TELEGRAM_ID premium 30\n"
        "/admin_revoke TELEGRAM_ID"
    )


def _authorized(update: Update) -> bool:
    user = update.effective_user
    return user is not None and is_admin_telegram_user(getattr(user, "id", None))


async def _deny_access(update: Update) -> None:
    problem = admin_setting_problem()
    if problem:
        text = (
            "🔒 Admin panel is not configured yet.\n\n"
            "Send /myid, copy your Telegram user ID, add it to TeacherOS/.env as:\n\n"
            "TEACHEROS_ADMIN_ID=YOUR_NUMBER\n\n"
            "Then restart the bot."
        )
    else:
        text = "🔒 This admin panel is restricted to the TeacherOS owner."

    if update.callback_query is not None:
        await update.callback_query.answer(text, show_alert=True)
    elif update.message is not None:
        await update.message.reply_text(text)


async def _safe_edit(query: Any, text: str, *, reply_markup: Any) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _show_section(
    update: Update,
    *,
    section: str,
) -> None:
    if not _authorized(update):
        await _deny_access(update)
        return

    feedback_summary: dict[str, Any] = {"recent": []}
    try:
        if section == "revenue":
            text = _revenue_message(get_admin_payment_summary())
        elif section == "plans":
            text = _plans_message(get_admin_subscription_summary())
        elif section == "feedback":
            feedback_summary = get_admin_feedback_summary()
            text = _feedback_message(feedback_summary)
        else:
            summary = get_admin_dashboard_summary()
            if section == "users":
                text = _users_message(summary)
            elif section == "content":
                text = _content_message(summary)
            else:
                section = "overview"
                text = _overview_message(summary)
    except Exception:
        logger.exception("Could not load admin dashboard")
        text = (
            "❌ TeacherOS could not load admin statistics.\n\n"
            "Run python backend/check_project.py and restart the bot."
        )

    if section == "feedback":
        keyboard = admin_feedback_keyboard(feedback_summary.get("recent", []))
    else:
        keyboard = admin_keyboard(section)
    if update.callback_query is not None:
        await _safe_edit(update.callback_query, text, reply_markup=keyboard)
    elif update.message is not None:
        await update.message.reply_text(text, reply_markup=keyboard)


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the current Telegram account ID without exposing any other account."""
    context.user_data.clear()
    user = update.effective_user
    if user is None or not isinstance(getattr(user, "id", None), int):
        if update.message is not None:
            await update.message.reply_text("❌ TeacherOS could not read your Telegram user ID.")
        return

    if update.message is not None:
        await update.message.reply_text(
            "🪪 Your Telegram User ID\n\n"
            f"{user.id}\n\n"
            "For Day 24, add this exact line to TeacherOS/.env:\n\n"
            f"TEACHEROS_ADMIN_ID={user.id}\n\n"
            "Do not use your username. Use the number shown above."
        )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await _show_section(update, section="overview")


async def admin_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await _show_section(update, section="users")


async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await _show_section(update, section="content")


async def admin_revenue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await _show_section(update, section="revenue")


async def admin_plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await _show_section(update, section="plans")


async def admin_feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await _show_section(update, section="feedback")


async def admin_grant_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    if not _authorized(update):
        await _deny_access(update)
        return
    if update.message is None:
        return
    args = list(context.args or [])
    if len(args) not in {2, 3}:
        await update.message.reply_text(
            "Usage:\n/admin_grant TELEGRAM_ID pro 30\n"
            "/admin_grant TELEGRAM_ID premium 30"
        )
        return
    try:
        target_id = int(args[0])
        plan_code = args[1].strip().lower()
        days = int(args[2]) if len(args) == 3 else 30
        admin_id = int(update.effective_user.id)
        subscription = grant_manual_subscription(
            telegram_user_id=target_id,
            plan_code=plan_code,
            days=days,
            granted_by_telegram_id=admin_id,
        )
    except Exception as exc:
        await update.message.reply_text(f"❌ Plan grant failed: {exc}")
        return
    await update.message.reply_text(
        "✅ Manual plan granted\n\n"
        f"Telegram ID: {target_id}\n"
        f"Plan: {str(subscription['plan_code']).title()}\n"
        f"Valid until: {subscription['expires_at']} UTC"
    )


async def admin_revoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    if not _authorized(update):
        await _deny_access(update)
        return
    if update.message is None:
        return
    args = list(context.args or [])
    if len(args) != 1:
        await update.message.reply_text("Usage: /admin_revoke TELEGRAM_ID")
        return
    try:
        target_id = int(args[0])
        revoked = revoke_user_subscriptions(telegram_user_id=target_id)
    except Exception as exc:
        await update.message.reply_text(f"❌ Revoke failed: {exc}")
        return
    await update.message.reply_text(
        f"✅ Revoked {revoked} active subscription record(s) for Telegram ID {target_id}."
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    data = query.data or ""
    if not _authorized(update):
        await _deny_access(update)
        return

    context.user_data.clear()

    if data in {"admin_overview", "admin_refresh"}:
        await query.answer()
        await _show_section(update, section="overview")
        return
    if data == "admin_users":
        await query.answer()
        await _show_section(update, section="users")
        return
    if data == "admin_content":
        await query.answer()
        await _show_section(update, section="content")
        return
    if data == "admin_revenue":
        await query.answer()
        await _show_section(update, section="revenue")
        return
    if data == "admin_plans":
        await query.answer()
        await _show_section(update, section="plans")
        return
    if data == "admin_feedback":
        await query.answer()
        await _show_section(update, section="feedback")
        return
    if data.startswith("admin_feedback_reviewed_") or data.startswith("admin_feedback_resolved_"):
        parts = data.rsplit("_", 1)
        try:
            feedback_id = int(parts[1])
            status = "reviewed" if "_reviewed_" in data else "resolved"
            changed = update_feedback_status(feedback_id=feedback_id, status=status)
        except Exception:
            logger.exception("Could not update beta feedback status")
            await query.answer("Could not update that report.", show_alert=True)
            return
        await query.answer(
            f"Feedback #{feedback_id} marked {status}." if changed else "Feedback report not found.",
            show_alert=not changed,
        )
        await _show_section(update, section="feedback")
        return
    if data == "admin_main":
        await query.answer()
        await _safe_edit(
            query,
            teacheros_home_text(),
            reply_markup=start_menu_keyboard(show_admin=True),
        )
        return

    await query.answer("That admin button is no longer valid.", show_alert=True)
