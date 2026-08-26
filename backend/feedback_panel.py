from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ApplicationHandlerStop, ContextTypes

from config import is_admin_telegram_user
from database import (
    register_telegram_user,
    save_beta_feedback,
    update_beta_feedback_message,
)
from keyboards import (
    account_home_keyboard,
    feedback_done_keyboard,
    feedback_optional_text_keyboard,
    feedback_rating_keyboard,
    feedback_required_text_keyboard,
)

logger = logging.getLogger(__name__)

_RATING_LABELS: dict[int, str] = {
    1: "Very frustrating",
    2: "Frustrating",
    3: "Okay",
    4: "Good",
    5: "Excellent",
}


def _flow(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    flow = context.user_data.get("feedback")
    if not isinstance(flow, dict):
        flow = {}
        context.user_data["feedback"] = flow
    return flow


def _clear_flow(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("feedback", None)


def _account_keyboard(update: Update):
    """Return the correct Account keyboard, including Admin for the owner."""
    user_id = getattr(update.effective_user, "id", None)
    return account_home_keyboard(show_admin=is_admin_telegram_user(user_id))


def _rating_prompt() -> str:
    return (
        "⭐ Rate TeacherOS\n\n"
        "One quick tap—how was your experience today?\n\n"
        "Most ratings are submitted instantly."
    )


async def _safe_edit(query: Any, text: str, *, reply_markup: Any) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start the fast, one-tap beta-feedback flow from /feedback."""
    context.user_data.clear()
    if update.message is None:
        return

    _flow(context)["state"] = "rating"
    await update.message.reply_text(
        _rating_prompt(),
        reply_markup=feedback_rating_keyboard(),
    )


async def feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save ordinary ratings immediately and request text only for rating 1."""
    query = update.callback_query
    if query is None:
        return

    data = query.data or ""

    if data == "feedback_start":
        await query.answer()
        _clear_flow(context)
        _flow(context)["state"] = "rating"
        await _safe_edit(
            query,
            _rating_prompt(),
            reply_markup=feedback_rating_keyboard(),
        )
        return

    if data == "feedback_cancel":
        await query.answer()
        _clear_flow(context)
        await _safe_edit(
            query,
            "No problem—nothing was submitted.",
            reply_markup=_account_keyboard(update),
        )
        return

    if data == "feedback_back_rating":
        await query.answer()
        flow = _flow(context)
        flow.clear()
        flow["state"] = "rating"
        await _safe_edit(
            query,
            _rating_prompt(),
            reply_markup=feedback_rating_keyboard(),
        )
        return

    if data == "feedback_finish":
        await query.answer()
        _clear_flow(context)
        await _safe_edit(
            query,
            "✅ Thank you for helping improve TeacherOS.",
            reply_markup=_account_keyboard(update),
        )
        return

    if data == "feedback_add_comment":
        flow = _flow(context)
        feedback_id = flow.get("feedback_id")
        rating = flow.get("rating")
        if not isinstance(feedback_id, int) or rating not in {2, 3, 4, 5}:
            _clear_flow(context)
            await query.answer(
                "That feedback session expired. Your rating may already be saved.",
                show_alert=True,
            )
            await _safe_edit(
                query,
                _rating_prompt(),
                reply_markup=feedback_rating_keyboard(),
            )
            return

        await query.answer()
        flow["state"] = "optional_message"
        await _safe_edit(
            query,
            "💬 Optional comment\n\n"
            "Your rating is already saved. Add a short comment only if you want to.\n\n"
            "You can also tap Done—no explanation is required.",
            reply_markup=feedback_optional_text_keyboard(),
        )
        return

    if data.startswith("feedback_rating_"):
        try:
            rating = int(data.rsplit("_", 1)[1])
        except (TypeError, ValueError):
            await query.answer("That rating is invalid.", show_alert=True)
            return
        if rating not in {1, 2, 3, 4, 5}:
            await query.answer("Please choose one of the five ratings.", show_alert=True)
            return

        user = update.effective_user
        if user is None:
            await query.answer("TeacherOS could not identify your account.", show_alert=True)
            return

        await query.answer()
        if rating == 1:
            flow = _flow(context)
            flow.clear()
            flow.update({"state": "required_message", "rating": rating})
            await _safe_edit(
                query,
                "😣 Sorry about that\n\n"
                "What went wrong? Please send a few words so I can fix it.\n\n"
                "Example: Search could not find my worksheet.",
                reply_markup=feedback_required_text_keyboard(),
            )
            return

        try:
            register_telegram_user(user)
            feedback_id = save_beta_feedback(
                telegram_user=user,
                rating=rating,
                area="other",
                message="",
            )
        except Exception:
            logger.exception("Could not save a quick TeacherOS rating")
            _clear_flow(context)
            await _safe_edit(
                query,
                "❌ TeacherOS could not save your rating right now. Please try once more.",
                reply_markup=feedback_rating_keyboard(),
            )
            return

        # Keep the ID for the optional-comment button, but omit state so normal chat
        # messages are not blocked after the rating has already been submitted.
        flow = _flow(context)
        flow.clear()
        flow.update({"feedback_id": feedback_id, "rating": rating})
        await _safe_edit(
            query,
            "✅ Rating sent—thank you!\n\n"
            f"{_RATING_LABELS[rating]} · {rating}/5\n\n"
            "You’re finished. Adding a comment is completely optional.",
            reply_markup=feedback_done_keyboard(allow_comment=True),
        )
        return

    # Old Day 28 buttons may remain in previous Telegram messages after an update.
    if data.startswith("feedback_area_") or data == "feedback_back_area":
        _clear_flow(context)
        await query.answer("The feedback form is now faster. Please rate again.", show_alert=True)
        await _safe_edit(
            query,
            _rating_prompt(),
            reply_markup=feedback_rating_keyboard(),
        )
        return

    await query.answer("That feedback button is no longer available.", show_alert=True)


async def get_feedback_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save required or optional feedback text while the matching flow is active."""
    if update.message is None:
        return

    flow = context.user_data.get("feedback")
    if not isinstance(flow, dict):
        return

    state = flow.get("state")
    if state not in {"required_message", "optional_message"}:
        return

    message = " ".join((update.message.text or "").split())
    minimum = 5 if state == "required_message" else 1
    if len(message) < minimum:
        if state == "required_message":
            await update.message.reply_text(
                "Please write at least a few words so I know what to fix.",
                reply_markup=feedback_required_text_keyboard(),
            )
        else:
            await update.message.reply_text(
                "Send a short comment, or tap Done to finish without one.",
                reply_markup=feedback_optional_text_keyboard(),
            )
        raise ApplicationHandlerStop

    if len(message) > 2000:
        keyboard = (
            feedback_required_text_keyboard()
            if state == "required_message"
            else feedback_optional_text_keyboard()
        )
        await update.message.reply_text(
            "Please shorten the comment to 2,000 characters or fewer.",
            reply_markup=keyboard,
        )
        raise ApplicationHandlerStop

    user = update.effective_user
    if user is None or not isinstance(getattr(user, "id", None), int):
        _clear_flow(context)
        await update.message.reply_text(
            "Your feedback session expired. Use /feedback to start again."
        )
        raise ApplicationHandlerStop

    try:
        register_telegram_user(user)
        if state == "required_message":
            feedback_id = save_beta_feedback(
                telegram_user=user,
                rating=1,
                area="other",
                message=message,
            )
            confirmation = (
                "✅ Thank you—this helps me understand what needs fixing.\n\n"
                f"Feedback ID: #{feedback_id}"
            )
        else:
            feedback_id = flow.get("feedback_id")
            if not isinstance(feedback_id, int):
                raise ValueError("Your feedback session expired.")
            changed = update_beta_feedback_message(
                feedback_id=feedback_id,
                telegram_user_id=user.id,
                message=message,
            )
            if not changed:
                raise ValueError("Your saved rating could not be found.")
            confirmation = "✅ Thank you—your optional comment was added."
    except ValueError as exc:
        await update.message.reply_text(
            f"⚠️ {exc}",
            reply_markup=(
                feedback_required_text_keyboard()
                if state == "required_message"
                else feedback_optional_text_keyboard()
            ),
        )
        raise ApplicationHandlerStop
    except Exception:
        logger.exception("Could not save TeacherOS feedback text")
        await update.message.reply_text(
            "❌ TeacherOS could not save your feedback right now. Please try again later.",
            reply_markup=(
                feedback_required_text_keyboard()
                if state == "required_message"
                else feedback_optional_text_keyboard()
            ),
        )
        raise ApplicationHandlerStop

    _clear_flow(context)
    await update.message.reply_text(
        confirmation,
        reply_markup=feedback_done_keyboard(allow_comment=False),
    )
    raise ApplicationHandlerStop
