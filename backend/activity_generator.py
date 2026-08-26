from __future__ import annotations

import logging

from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ContextTypes

from database import save_generated_material

from keyboards import (
    ACTIVITY_TYPE_OPTIONS,
    activity_confirm_keyboard,
    activity_type_keyboard,
    back_cancel_keyboard,
    generated_material_export_keyboard,
    level_keyboard,
    start_menu_keyboard,
    subscription_limit_keyboard,
)
from openrouter_client import generate_text
from prompt_loader import load_feature_prompt
from subscription_service import (
    generation_access_for_user,
    generation_block_message,
    selected_openrouter_model,
)

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
            "⌛ This activity-generator session expired.\n\nChoose an option below.",
            reply_markup=start_menu_keyboard(),
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
            "❌ Activity Generator cancelled.",
            reply_markup=start_menu_keyboard(),
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

    topic = " ".join((update.message.text or "").split())
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

    user = update.effective_user
    if user is None or not isinstance(getattr(user, "id", None), int):
        await _expired_session(update, context)
        return

    access = generation_access_for_user(user.id)
    if not bool(access.get("allowed")):
        context.user_data.pop("activity", None)
        await query.edit_message_text(
            generation_block_message(access),
            reply_markup=subscription_limit_keyboard(),
        )
        return

    # Prevent repeated Generate taps from creating duplicate API calls or records.
    activity["state"] = "generating"
    await query.edit_message_text(
        "🧠 Generating your activity...\n\n"
        "TeacherOS is preparing the classroom instructions and materials."
    )

    try:
        prompt = load_feature_prompt("activity_generator", "activity_template")

        replacements = {
            "{{activity_type}}": str(activity["type"]),
            "{{activity}}": str(activity["type"]),
            "{{level}}": str(activity["level"]),
            "{{topic}}": str(activity["topic"]),
            "{{target_language}}": "Not specified",
            "{{context}}": "General English class",
        }
        for placeholder, value in replacements.items():
            prompt = prompt.replace(placeholder, value)

        result = await generate_text(
            [{"role": "user", "content": prompt}],
            model=selected_openrouter_model(access),
        )
    except Exception:
        logger.exception("Activity generation failed")
        activity["state"] = "confirm"
        await query.edit_message_text(
            "❌ I could not generate the activity right now.\n\n"
            "Your choices are still saved. Check your connection or OpenRouter settings, "
            "then tap Generate Activity to retry.",
            reply_markup=activity_confirm_keyboard(),
        )
        return

    material_id: int | None = None
    save_message = "✅ Activity generated. It appears below."
    try:
        if update.effective_user is None:
            raise ValueError("Telegram user details are unavailable.")
        material_id = save_generated_material(
            telegram_user=update.effective_user,
            material_type="activity",
            subtype=str(activity["type"]),
            title=f"{activity['type']} — {activity['topic']} ({activity['level']})",
            level=str(activity["level"]),
            topic=str(activity["topic"]),
            content=result,
            metadata={},
        )
        save_message = (
            "✅ Activity generated and saved automatically.\n"
            f"Library ID: {material_id}\n\n"
            "Use the buttons below to download Word or PDF immediately."
        )
    except Exception:
        logger.exception("Activity was generated but could not be saved")
        save_message = (
            "⚠️ Activity generated, but TeacherOS could not save it.\n\n"
            "The activity still appears below, but export buttons are unavailable."
        )

    await query.edit_message_text(
        save_message,
        reply_markup=(
            generated_material_export_keyboard(material_id)
            if material_id is not None
            else None
        ),
    )
    if query.message is not None:
        for start in range(0, len(result), 4000):
            await query.message.reply_text(result[start : start + 4000])

    context.user_data.pop("activity", None)
