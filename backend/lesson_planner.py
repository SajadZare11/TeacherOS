from __future__ import annotations

import logging

from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ContextTypes

from database import save_generated_material

from keyboards import (
    GRAMMAR_OPTIONS,
    back_cancel_keyboard,
    generated_material_export_keyboard,
    duration_keyboard,
    grammar_keyboard,
    lesson_confirm_keyboard,
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


def _lesson_data(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    lesson = context.user_data.get("lesson")
    return lesson if isinstance(lesson, dict) else None


async def _answer_callback(update: Update) -> None:
    query = update.callback_query
    if query is None:
        return

    try:
        await query.answer()
    except (TimedOut, NetworkError):
        logger.warning("Could not answer Telegram callback query.")


async def _expired_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("lesson", None)
    query = update.callback_query
    if query is not None:
        await query.edit_message_text(
            "⌛ This lesson-planner session expired.\n\nChoose an option below.",
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


async def lesson_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    await _answer_callback(update)
    data = query.data or ""

    if data == "lesson":
        context.user_data.clear()
        context.user_data["lesson"] = {"state": "level"}
        await query.edit_message_text(
            "📚 Lesson Planner\n\n"
            "Step 1 of 5\n\n"
            "Choose your CEFR level.",
            reply_markup=level_keyboard("lesson", "lesson_back_main"),
        )
        return

    lesson = _lesson_data(context)
    if lesson is None:
        await _expired_session(update, context)
        return

    # ---------- Back navigation ----------
    if data == "lesson_back_main":
        await _show_main_menu(update, context)
        return

    if data == "lesson_back_level":
        lesson.clear()
        lesson["state"] = "level"
        await query.edit_message_text(
            "📚 Lesson Planner\n\n"
            "Step 1 of 5\n\n"
            "Choose your CEFR level.",
            reply_markup=level_keyboard("lesson", "lesson_back_main"),
        )
        return

    if data == "lesson_back_topic":
        if lesson.get("state") != "grammar":
            await _expired_session(update, context)
            return

        lesson.pop("topic", None)
        lesson.pop("grammar", None)
        lesson.pop("duration", None)
        lesson["state"] = "topic"
        await query.edit_message_text(
            "📚 Lesson Planner\n\n"
            "Step 2 of 5\n\n"
            "✏️ Type today's lesson topic.\n\n"
            "Examples: Travel, Food, Technology, Shopping, Health",
            reply_markup=back_cancel_keyboard("lesson_back_level", "lesson_cancel"),
        )
        return

    if data == "lesson_back_grammar":
        if lesson.get("state") != "duration":
            await _expired_session(update, context)
            return

        lesson.pop("grammar", None)
        lesson.pop("duration", None)
        lesson["state"] = "grammar"
        await query.edit_message_text(
            "📚 Lesson Planner\n\n"
            "Step 3 of 5\n\n"
            "Choose the grammar focus.",
            reply_markup=grammar_keyboard(),
        )
        return

    if data == "lesson_back_duration":
        if lesson.get("state") != "confirm":
            await _expired_session(update, context)
            return

        lesson.pop("duration", None)
        lesson["state"] = "duration"
        await query.edit_message_text(
            "📚 Lesson Planner\n\n"
            "Step 4 of 5\n\n"
            "Choose the lesson duration.",
            reply_markup=duration_keyboard(),
        )
        return

    # ---------- Forward navigation ----------
    if data.startswith("lesson_level_"):
        level = data.removeprefix("lesson_level_")
        if level not in {"A1", "A2", "B1", "B2", "C1", "C2"}:
            await _expired_session(update, context)
            return

        lesson["level"] = level
        lesson.pop("topic", None)
        lesson.pop("grammar", None)
        lesson.pop("duration", None)
        lesson["state"] = "topic"
        await query.edit_message_text(
            "📚 Lesson Planner\n\n"
            "Step 2 of 5\n\n"
            "✏️ Type today's lesson topic.\n\n"
            "Examples: Travel, Food, Technology, Shopping, Health",
            reply_markup=back_cancel_keyboard("lesson_back_level", "lesson_cancel"),
        )
        return

    if data.startswith("lesson_grammar_"):
        grammar_code = data.removeprefix("lesson_grammar_")
        grammar = GRAMMAR_OPTIONS.get(grammar_code)
        if grammar is None or lesson.get("state") != "grammar":
            await _expired_session(update, context)
            return

        lesson["grammar"] = grammar
        lesson.pop("duration", None)
        lesson["state"] = "duration"
        await query.edit_message_text(
            "📚 Lesson Planner\n\n"
            "Step 4 of 5\n\n"
            "Choose the lesson duration.",
            reply_markup=duration_keyboard(),
        )
        return

    if data.startswith("lesson_duration_"):
        duration = data.removeprefix("lesson_duration_")
        if duration not in {"30", "45", "60", "90"} or lesson.get("state") != "duration":
            await _expired_session(update, context)
            return

        required = ("level", "topic", "grammar")
        if any(not lesson.get(field) for field in required):
            await _expired_session(update, context)
            return

        lesson["duration"] = duration
        lesson["state"] = "confirm"
        await query.edit_message_text(
            "📚 Lesson Planner\n\n"
            "Step 5 of 5\n\n"
            "Please review your lesson.\n\n"
            f"📖 Level: {lesson['level']}\n"
            f"📝 Topic: {lesson['topic']}\n"
            f"📚 Grammar: {lesson['grammar']}\n"
            f"⏰ Duration: {lesson['duration']} minutes",
            reply_markup=lesson_confirm_keyboard(),
        )
        return

    if data == "lesson_cancel":
        context.user_data.pop("lesson", None)
        await query.edit_message_text(
            "❌ Lesson Planner cancelled.",
            reply_markup=start_menu_keyboard(),
        )
        return

    if data == "lesson_generate":
        await generate_lesson(update, context)
        return

    await _expired_session(update, context)


async def get_lesson_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lesson = _lesson_data(context)
    if lesson is None or lesson.get("state") != "topic" or update.message is None:
        return

    topic = " ".join((update.message.text or "").split())
    if len(topic) < 2:
        await update.message.reply_text("Please type a topic with at least 2 characters.")
        return

    if len(topic) > 200:
        await update.message.reply_text("Please keep the topic under 200 characters.")
        return

    lesson["topic"] = topic
    lesson["state"] = "grammar"
    await update.message.reply_text(
        "📚 Lesson Planner\n\n"
        "Step 3 of 5\n\n"
        "Choose the grammar focus.",
        reply_markup=grammar_keyboard(),
    )


async def generate_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    lesson = _lesson_data(context)

    if query is None or lesson is None or lesson.get("state") != "confirm":
        await _expired_session(update, context)
        return

    required = ("level", "topic", "grammar", "duration")
    if any(not lesson.get(field) for field in required):
        await _expired_session(update, context)
        return

    user = update.effective_user
    if user is None or not isinstance(getattr(user, "id", None), int):
        await _expired_session(update, context)
        return

    access = generation_access_for_user(user.id)
    if not bool(access.get("allowed")):
        context.user_data.pop("lesson", None)
        await query.edit_message_text(
            generation_block_message(access),
            reply_markup=subscription_limit_keyboard(),
        )
        return

    # Prevent repeated Generate taps from creating duplicate API calls or records.
    lesson["state"] = "generating"
    await query.edit_message_text(
        "🧠 Generating your lesson plan...\n\n"
        "TeacherOS is preparing the complete classroom-ready lesson."
    )

    try:
        prompt = load_feature_prompt("lesson_planner", "lesson_template")

        replacements = {
            "{LEVEL}": str(lesson["level"]),
            "{TOPIC}": str(lesson["topic"]),
            "{GRAMMAR}": str(lesson["grammar"]),
            "{VOCABULARY}": "Not specified",
            "{DURATION}": str(lesson["duration"]),
            "{GOALS}": "Create a complete classroom-ready lesson for the stated topic and language focus.",
        }
        for placeholder, value in replacements.items():
            prompt = prompt.replace(placeholder, value)

        result = await generate_text(
            [{"role": "user", "content": prompt}],
            model=selected_openrouter_model(access),
        )
    except Exception:
        logger.exception("Lesson generation failed")
        lesson["state"] = "confirm"
        await query.edit_message_text(
            "❌ I could not generate the lesson right now.\n\n"
            "Your choices are still saved. Check your connection or OpenRouter settings, "
            "then tap Generate Lesson to retry.",
            reply_markup=lesson_confirm_keyboard(),
        )
        return

    material_id: int | None = None
    save_message = "✅ Lesson generated. It appears below."
    try:
        if update.effective_user is None:
            raise ValueError("Telegram user details are unavailable.")
        material_id = save_generated_material(
            telegram_user=update.effective_user,
            material_type="lesson",
            subtype="Lesson Plan",
            title=f"{lesson['topic']} Lesson Plan ({lesson['level']})",
            level=str(lesson["level"]),
            topic=str(lesson["topic"]),
            content=result,
            metadata={
                "grammar": str(lesson["grammar"]),
                "duration_minutes": int(str(lesson["duration"])),
            },
        )
        save_message = (
            "✅ Lesson generated and saved automatically.\n"
            f"Library ID: {material_id}\n\n"
            "Use the buttons below to download Word or PDF immediately."
        )
    except Exception:
        logger.exception("Lesson was generated but could not be saved")
        save_message = (
            "⚠️ Lesson generated, but TeacherOS could not save it.\n\n"
            "The lesson still appears below, but export buttons are unavailable."
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

    context.user_data.pop("lesson", None)
