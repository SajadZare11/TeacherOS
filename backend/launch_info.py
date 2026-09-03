from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import is_admin_telegram_user
from keyboards import account_home_keyboard, launch_info_keyboard

logger = logging.getLogger(__name__)

ABOUT_TEXT = (
    "🍎 About TeacherOS\n\n"
    "TeacherOS was created out of deep respect for educators, with one clear purpose: to make a teacher's daily life easier.\n\n"
    "TeacherOS is your AI co-pilot, designed to handle the time-consuming groundwork so you can teach with clarity and joy.\n\n"
    "At your fingertips:\n"
    "• Smart lesson plans & engaging classroom activities\n"
    "• CEFR-aligned worksheets and quizzes (A1–C2)\n"
    "• Effortless auto-saving & one-click Word/PDF export\n\n"
    "Built to reduce preparation hours while honoring your professional judgment—because the heart of the classroom will always be you. 🌟\n\n"
    "🍎 Made by @SajadZare11"
)

PRIVACY_TEXT = (
    "🔐 TeacherOS Privacy Notice\n"
    "Effective: July 27, 2026\n\n"
    "TeacherOS stores the information needed to provide the service, including your Telegram user "
    "ID and basic profile details, generated teaching materials, usage records, subscription and "
    "payment status, and feedback you choose to submit.\n\n"
    "Your generation requests are sent to OpenRouter and the selected AI model so TeacherOS can "
    "create a response. Payment requests are handled through ZarinPal. TeacherOS does not need or "
    "store your card password, CVV, or full card number; it may store transaction references and "
    "masked payment details returned by the provider.\n\n"
    "Do not submit confidential student records, passwords, financial information, or other highly "
    "sensitive personal data.\n\n"
    "Use /feedback to request help or ask about your stored TeacherOS data."
)

TERMS_TEXT = (
    "📄 TeacherOS Terms of Use\n"
    "Effective: July 27, 2026\n\n"
    "• TeacherOS generates draft teaching materials using AI. Review every output before using it "
    "with students. AI responses may contain mistakes, omissions, or unsuitable content.\n"
    "• You are responsible for the material you submit and how you use generated content. Do not "
    "submit unlawful content or confidential student information.\n"
    "• Free-plan limits reset according to the configured TeacherOS usage day. Paid plans remain "
    "active for the period shown before purchase.\n"
    "• A plan is activated only after payment verification. Sandbox payments are tests and do not "
    "represent a real purchase.\n"
    "• TeacherOS may change, suspend, or improve features during the launch period.\n"
    "• By continuing to use TeacherOS, you agree to these terms and the Privacy Notice."
)

INFO_HOME_TEXT = (
    "ℹ️ TeacherOS Help & Policies\n\n"
    "Learn what TeacherOS does and how your information is handled."
)


async def _safe_edit(query: Any, text: str, *, reply_markup: Any) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


def _show_admin(update: Update) -> bool:
    user_id = getattr(update.effective_user, "id", None)
    return is_admin_telegram_user(user_id)


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.message is not None:
        await update.message.reply_text(ABOUT_TEXT)


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.message is not None:
        await update.message.reply_text(PRIVACY_TEXT)


async def terms_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.message is not None:
        await update.message.reply_text(TERMS_TEXT)


async def launch_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    await query.answer()
    context.user_data.clear()
    data = query.data or ""

    try:
        if data == "info_home":
            await _safe_edit(query, INFO_HOME_TEXT, reply_markup=launch_info_keyboard())
            return
        if data == "info_about":
            await _safe_edit(query, ABOUT_TEXT, reply_markup=launch_info_keyboard(compact=True))
            return
        if data == "info_privacy":
            await _safe_edit(query, PRIVACY_TEXT, reply_markup=launch_info_keyboard(compact=True))
            return
        if data == "info_terms":
            await _safe_edit(query, TERMS_TEXT, reply_markup=launch_info_keyboard(compact=True))
            return
        if data == "info_account":
            await _safe_edit(
                query,
                "👤 TeacherOS Account\n\nChoose an account option below.",
                reply_markup=account_home_keyboard(show_admin=_show_admin(update)),
            )
            return
    except Exception:
        logger.exception("Could not open TeacherOS launch information")

    await _safe_edit(query, INFO_HOME_TEXT, reply_markup=launch_info_keyboard())
