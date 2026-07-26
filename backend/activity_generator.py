from __future__ import annotations

import logging

from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ContextTypes

from keyboards import (
    ACTIVITY_TYPE_OPTIONS,
    activity_confirm_keyboard,
    activity_type_keyboard,
    back_cancel_keyboard,
    level_keyboard,
    start_menu_keyboard,
)
from openrouter_client import generate_text
from prompt_loader import load_feature_prompt

logger = logging.getLogger(__name__)


def _activity_data(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    activity = context.user_data.get("activity")
    return activity if isinstance(activity, dict) else None


async def _answer_callback(update: Update) -> None:
    query = update.callback_query
    if query is None:
        return

    try:
        await query.answer()
    except (TimedOut, NetworkError):
        logger.warning("Could not answer Telegram callback query.")


async def _expired_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("activity", None)
    query = update.callback_query
    if query is not None:
        await query.edit_message_text(
            "⌛ This activity-generator session expired.\n\nSend /start and begin again."
        )


async def _show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    query = update.callback_query
    if query is None:
        return

    await query.edit_message_text(
        "👋 Welcome to TeacherOS\n\n"
        "Your AI assistant for English teachers.\n\n"
        "Choose what you'd like to create today.",
        reply_markup=start_menu_keyboard(),
    )


async def activity_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    await _answer_callback(update)
    data = query.data or ""

    if data == "activity_start":
        context.user_data.clear()
        context.user_data["activity"] = {"state": "type"}
        await query.edit_message_text(
            "🎲 Activity Generator\n\n"
            "Step 1 of 4\n\n"
            "Choose an activity type.",
            reply_markup=activity_type_keyboard(),
        )
        return

    activity = _activity_data(context)
    if activity is None:
        await _expired_session(update, context)
        return

    # ---------- Back navigation ----------
    if data == "activity_back_main":
        await _show_main_menu(update, context)
        return

    if data == "activity_back_type":
        if activity.get("state") != "level":
            await _expired_session(update, context)
            return

        activity.clear()
        activity["state"] = "type"
        await query.edit_message_text(
            "🎲 Activity Generator\n\n"
            "Step 1 of 4\n\n"
            "Choose an activity type.",
            reply_markup=activity_type_keyboard(),
        )
        return

    if data == "activity_back_level":
        if activity.get("state") != "topic":
            await _expired_session(update, context)
            return

        activity.pop("level", None)
        activity.pop("topic", None)
        activity["state"] = "level"
        await query.edit_message_text(
            "🎲 Activity Generator\n\n"
            "Step 2 of 4\n\n"
            "Choose the CEFR level.",
            reply_markup=level_keyboard("activity", "activity_back_type"),
        )
        return

    if data == "activity_back_topic":
        if activity.get("state") != "confirm":
            await _expired_session(update, context)
            return

        activity.pop("topic", None)
        activity["state"] = "topic"
        await query.edit_message_text(
            "🎲 Activity Generator\n\n"
            "Step 3 of 4\n\n"
            "Type the lesson topic.",
            reply_markup=back_cancel_keyboard("activity_back_level", "activity_cancel"),
        )
        return

    # ---------- Forward navigation ----------
    if data.startswith("activity_type_"):
        type_code = data.removeprefix("activity_type_")
        activity_type = ACTIVITY_TYPE_OPTIONS.get(type_code)
        if activity_type is None or activity.get("state") != "type":
            await _expired_session(update, context)
            return

        activity["type"] = activity_type
        activity.pop("level", None)
        activity.pop("topic", None)
        activity["state"] = "level"
        await query.edit_message_text(
            "🎲 Activity Generator\n\n"
            "Step 2 of 4\n\n"
            "Choose the CEFR level.",
            reply_markup=level_keyboard("activity", "activity_back_type"),
        )
        return

    if data.startswith("activity_level_"):
        level = data.removeprefix("activity_level_")
        if level not in {"A1", "A2", "B1", "B2", "C1", "C2"} or activity.get("state") != "level":
            await _expired_session(update, context)
            return

        activity["level"] = level
        activity.pop("topic", None)
        activity["state"] = "topic"
        await query.edit_message_text(
            "🎲 Activity Generator\n\n"
            "Step 3 of 4\n\n"
            "Type the lesson topic.",
            reply_markup=back_cancel_keyboard("activity_back_level", "activity_cancel"),
        )
        return

    if data == "activity_cancel":
        context.user_data.pop("activity", None)
        await query.edit_message_text(
            "❌ Activity Generator cancelled.\n\nSend /start to return to the main menu."
        )
        return

    if data == "activity_generate":
        await generate_activity(update, context)
        return

    await _expired_session(update, context)


async def get_activity_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    activity = _activity_data(context)
    if activity is None or activity.get("state") != "topic" or update.message is None:
        return

    topic = (update.message.text or "").strip()
    if len(topic) < 2:
        await update.message.reply_text("Please type a topic with at least 2 characters.")
        return

    if len(topic) > 200:
        await update.message.reply_text("Please keep the topic under 200 characters.")
        return

    activity["topic"] = topic
    activity["state"] = "confirm"
    await update.message.reply_text(
        "🎲 Activity Generator\n\n"
        "Step 4 of 4\n\n"
        f"🎯 Type: {activity['type']}\n"
        f"📖 Level: {activity['level']}\n"
        f"📝 Topic: {activity['topic']}\n\n"
        "Ready to generate?",
        reply_markup=activity_confirm_keyboard(),
    )


async def generate_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    activity = _activity_data(context)

    if query is None or activity is None or activity.get("state") != "confirm":
        await _expired_session(update, context)
        return

    required = ("type", "level", "topic")
    if any(not activity.get(field) for field in required):
        await _expired_session(update, context)
        return

    await query.edit_message_text(
        "🧠 Generating your activity...\n\n"
        "This usually takes 10–20 seconds.\n\n"
        "Please don't close Telegram."
    )

    try:
        prompt = load_feature_prompt("activity_generator", "activity_template")
        prompt = (
            prompt.replace("{{activity}}", str(activity["type"]))
            .replace("{{level}}", str(activity["level"]))
            .replace("{{topic}}", str(activity["topic"]))
        )

        result = await generate_text([{"role": "user", "content": prompt}])
    except Exception:
        logger.exception("Activity generation failed")
        context.user_data.pop("activity", None)
        await query.edit_message_text(
            "❌ I could not generate the activity.\n\n"
            "Check your internet connection, OpenRouter key, model availability, and prompt files. "
            "Then send /start and try again."
        )
        return

    await query.edit_message_text("✅ Activity generated. It appears below.")
    for start in range(0, len(result), 4000):
        await query.message.reply_text(result[start : start + 4000])

    context.user_data.pop("activity", None)

