from __future__ import annotations

import logging

from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ContextTypes

from ai_gateway import generate_artifact, generation_provenance
from database import save_generated_material
from home_ui import teacheros_home_text
from ui_service import resolve_lang
from typing_action import typing_heartbeat
from keyboards import (
    ASSESSMENT_TYPE_OPTIONS,
    QUIZ_FORMAT_OPTIONS,
    back_cancel_keyboard,
    generated_material_export_keyboard,
    level_keyboard,
    quiz_assessment_type_keyboard,
    quiz_confirm_keyboard,
    quiz_format_keyboard,
    quiz_question_count_keyboard,
    start_menu_keyboard,
    subscription_limit_keyboard,
)
from subscription_service import (
    generation_access_for_user,
    generation_block_message,
    selected_openrouter_model,
)

logger = logging.getLogger(__name__)

_VALID_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}
_QUICK_QUESTION_COUNTS = {5, 10, 15, 20, 25, 30}
_MIN_QUESTION_COUNT = 1
_MAX_QUESTION_COUNT = 50
_PURPOSES = {
    "Quiz": "A short formative check of current learning",
    "Test": "A classroom progress test covering the selected topic",
    "Exam": "A more comprehensive summative assessment",
    "Homework": "Independent practice and review outside class",
}
_FORMAT_RULES = {
    "Mixed": (
        "Use a balanced combination of Multiple Choice, Fill in the Blank, "
        "Matching, and True/False. Divide the total number of scored items "
        "as evenly as possible across the four formats."
    ),
    "Multiple Choice": (
        "Use only multiple-choice items. Every item must have exactly four "
        "options labelled A, B, C, and D, with one unambiguously correct answer."
    ),
    "Fill in the Blank": (
        "Use only fill-in-the-blank items. Give enough context for one clear "
        "answer. Accept reasonable alternatives in the answer key when needed."
    ),
    "Matching": (
        "Use only matching items. Present two clearly labelled columns and "
        "include plausible distractors where appropriate. Count each match as "
        "one scored item."
    ),
    "True / False": (
        "Use only true/false items. Avoid trivial statements and include a short "
        "correction in the answer key for every false statement."
    ),
}
_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def _quiz_data(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    quiz = context.user_data.get("quiz")
    return quiz if isinstance(quiz, dict) else None


async def assessment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open Quick Create's assessment flow directly from Telegram commands."""
    context.user_data.clear()
    context.user_data["quiz"] = {"state": "assessment_type"}
    if update.message is not None:
        await update.message.reply_text(
            "✅ Assessment Generator\n\nStep 1 of 6\n\nChoose the assessment type.",
            reply_markup=quiz_assessment_type_keyboard(),
        )


def _parse_question_count(value: object) -> int | None:
    normalized = str(value or "").strip().translate(_DIGIT_TRANSLATION)
    if not normalized.isdigit():
        return None
    count = int(normalized)
    if not _MIN_QUESTION_COUNT <= count <= _MAX_QUESTION_COUNT:
        return None
    return count


async def _answer_callback(update: Update) -> None:
    query = update.callback_query
    if query is None:
        return

    try:
        await query.answer()
    except (TimedOut, NetworkError):
        logger.warning("Could not answer Telegram callback query.")


async def _expired_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("quiz", None)
    query = update.callback_query
    if query is not None:
        await query.edit_message_text(
            "⌛ This assessment-generator session expired.\n\nChoose an option below.",
            reply_markup=start_menu_keyboard(),
        )


async def _show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    query = update.callback_query
    if query is None:
        return

    await query.edit_message_text(
        teacheros_home_text(),
        reply_markup=start_menu_keyboard(),
    )


def _prompt_replacements(quiz: dict) -> dict[str, str]:
    assessment_type = str(quiz["assessment_type"])
    question_format = str(quiz["question_format"])
    question_count = int(quiz["question_count"])
    level = str(quiz["level"])
    topic = str(quiz["topic"])

    return {
        "{ASSESSMENT_TYPE}": assessment_type,
        "{QUESTION_FORMAT}": question_format,
        "{LEVEL}": level,
        "{TOPIC}": topic,
        "{NUMBER_OF_QUESTIONS}": str(question_count),
        "{PURPOSE}": _PURPOSES[assessment_type],
        "{FORMAT_RULES}": _FORMAT_RULES[question_format],
        # Legacy placeholders remain supported while prompt files evolve.
        "{QUIZ_TYPE}": assessment_type,
        "{GRAMMAR}": "Automatically select suitable language for the topic and level",
        "{VOCABULARY}": "Automatically select suitable language for the topic and level",
        "{SKILLS}": "Language knowledge and practical comprehension appropriate to the chosen format",
    }

async def quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    await _answer_callback(update)
    data = query.data or ""

    if data == "quiz_start":
        context.user_data.clear()
        context.user_data["quiz"] = {"state": "assessment_type"}
        await query.edit_message_text(
            "✅ Assessment Generator\n\n"
            "Step 1 of 6\n\n"
            "Choose the assessment type.",
            reply_markup=quiz_assessment_type_keyboard(),
        )
        return

    quiz = _quiz_data(context)
    if quiz is None:
        await _expired_session(update, context)
        return

    # ---------- Back navigation ----------
    if data == "quiz_back_main":
        await _show_main_menu(update, context)
        return

    if data == "quiz_back_assessment_type":
        if quiz.get("state") != "question_format":
            await _expired_session(update, context)
            return

        if quiz.get("class_mode"):
            for field in ("assessment_type", "question_format", "question_count", "topic"):
                quiz.pop(field, None)
            quiz["level"] = quiz.get("inherited_level") or quiz.get("level")
            quiz["state"] = "assessment_type"
        else:
            quiz.clear()
            quiz["state"] = "assessment_type"
        await query.edit_message_text(
            "✅ Assessment Generator\n\n"
            "Step 1 of 6\n\n"
            "Choose the assessment type.",
            reply_markup=quiz_assessment_type_keyboard(),
        )
        return

    if data == "quiz_back_question_format":
        if quiz.get("state") not in {"question_count", "question_count_custom"}:
            await _expired_session(update, context)
            return

        quiz.pop("question_format", None)
        quiz.pop("question_count", None)
        if not quiz.get("class_mode"):
            quiz.pop("level", None)
        quiz.pop("topic", None)
        quiz["state"] = "question_format"
        await query.edit_message_text(
            "✅ Assessment Generator\n\n"
            "Step 2 of 6\n\n"
            "Choose the question format.\n\n"
            "Mixed is recommended for most classroom assessments.",
            reply_markup=quiz_format_keyboard(),
        )
        return

    if data == "quiz_back_question_count":
        if quiz.get("state") not in {"level", "question_count_custom"} and not (
            quiz.get("class_mode") and quiz.get("state") == "topic"
        ):
            await _expired_session(update, context)
            return

        quiz.pop("question_count", None)
        if not quiz.get("class_mode"):
            quiz.pop("level", None)
        quiz.pop("topic", None)
        quiz["state"] = "question_count"
        await query.edit_message_text(
            "✅ Assessment Generator\n\n"
            "Step 3 of 6\n\n"
            "How many questions should TeacherOS create?\n\n"
            "Choose a quick option or enter a custom number.",
            reply_markup=quiz_question_count_keyboard(),
        )
        return

    if data == "quiz_back_level":
        if quiz.get("state") != "topic":
            await _expired_session(update, context)
            return

        quiz.pop("level", None)
        quiz.pop("topic", None)
        quiz["state"] = "level"
        await query.edit_message_text(
            "✅ Assessment Generator\n\n"
            "Step 4 of 6\n\n"
            "Choose the CEFR level.",
            reply_markup=level_keyboard("quiz", "quiz_back_question_count"),
        )
        return

    if data == "quiz_back_topic":
        if quiz.get("state") != "confirm":
            await _expired_session(update, context)
            return

        quiz.pop("topic", None)
        quiz["state"] = "topic"
        await query.edit_message_text(
            "✅ Assessment Generator\n\n"
            "Step 5 of 6\n\n"
            "Type the assessment topic or language focus.\n\n"
            "Examples: Travel vocabulary, Present Perfect, Environment, "
            "Reading about technology",
            reply_markup=back_cancel_keyboard(
                "quiz_back_question_count" if quiz.get("class_mode") else "quiz_back_level",
                "quiz_cancel",
            ),
        )
        return

    # ---------- Forward navigation ----------
    if data.startswith("quiz_assessment_"):
        type_code = data.removeprefix("quiz_assessment_")
        assessment_type = ASSESSMENT_TYPE_OPTIONS.get(type_code)
        if assessment_type is None or quiz.get("state") != "assessment_type":
            await _expired_session(update, context)
            return

        quiz["assessment_type"] = assessment_type
        quiz.pop("question_format", None)
        quiz.pop("question_count", None)
        if not quiz.get("class_mode"):
            quiz.pop("level", None)
        quiz.pop("topic", None)
        quiz["state"] = "question_format"
        await query.edit_message_text(
            "✅ Assessment Generator\n\n"
            "Step 2 of 6\n\n"
            "Choose the question format.\n\n"
            "Mixed is recommended for most classroom assessments.",
            reply_markup=quiz_format_keyboard(),
        )
        return

    if data.startswith("quiz_format_"):
        format_code = data.removeprefix("quiz_format_")
        question_format = QUIZ_FORMAT_OPTIONS.get(format_code)
        if question_format is None or quiz.get("state") != "question_format":
            await _expired_session(update, context)
            return

        quiz["question_format"] = question_format
        quiz.pop("question_count", None)
        if not quiz.get("class_mode"):
            quiz.pop("level", None)
        quiz.pop("topic", None)
        quiz["state"] = "question_count"
        await query.edit_message_text(
            "✅ Assessment Generator\n\n"
            "Step 3 of 6\n\n"
            "How many questions should TeacherOS create?\n\n"
            "Choose a quick option or enter a custom number.",
            reply_markup=quiz_question_count_keyboard(),
        )
        return

    if data.startswith("quiz_count_"):
        count_code = data.removeprefix("quiz_count_")
        if quiz.get("state") != "question_count":
            await _expired_session(update, context)
            return

        if count_code == "custom":
            quiz.pop("question_count", None)
            quiz["state"] = "question_count_custom"
            await query.edit_message_text(
                "✅ Assessment Generator\n\n"
                "Step 3 of 6\n\n"
                "Type the exact number of questions you want.\n\n"
                f"You can choose any number from {_MIN_QUESTION_COUNT} to {_MAX_QUESTION_COUNT}.\n"
                "Persian and English numbers are both accepted.",
                reply_markup=back_cancel_keyboard(
                    "quiz_back_question_count",
                    "quiz_cancel",
                ),
            )
            return

        count = _parse_question_count(count_code)
        if count is None or count not in _QUICK_QUESTION_COUNTS:
            await _expired_session(update, context)
            return

        quiz["question_count"] = count
        quiz.pop("topic", None)
        if quiz.get("class_mode") and quiz.get("level"):
            quiz["state"] = "topic"
            await query.edit_message_text(
                f"✅ Assessment Generator · {quiz['class_name']}\n\n"
                f"Inherited level: {quiz['level']}\n\nType the assessment topic or language focus.",
                reply_markup=back_cancel_keyboard("quiz_back_question_count", "quiz_cancel"),
            )
            return
        quiz.pop("level", None)
        quiz["state"] = "level"
        await query.edit_message_text(
            "✅ Assessment Generator\n\n"
            "Step 4 of 6\n\n"
            "Choose the CEFR level.",
            reply_markup=level_keyboard("quiz", "quiz_back_question_count"),
        )
        return

    if data.startswith("quiz_level_"):
        level = data.removeprefix("quiz_level_")
        if level not in _VALID_LEVELS or quiz.get("state") != "level":
            await _expired_session(update, context)
            return

        quiz["level"] = level
        quiz.pop("topic", None)
        quiz["state"] = "topic"
        await query.edit_message_text(
            "✅ Assessment Generator\n\n"
            "Step 5 of 6\n\n"
            "Type the assessment topic or language focus.\n\n"
            "Examples: Travel vocabulary, Present Perfect, Environment, "
            "Reading about technology",
            reply_markup=back_cancel_keyboard("quiz_back_level", "quiz_cancel"),
        )
        return

    if data == "quiz_override" and quiz.get("class_mode"):
        quiz["state"] = "override_level"
        await query.edit_message_text(
            "✏ ONE-TIME level override\n\nChoose a level for this assessment only. The class profile will not change.",
            reply_markup=level_keyboard("quiz_override", "quiz_back_override"),
        )
        return

    if data == "quiz_back_override" and quiz.get("class_mode"):
        quiz["state"] = "confirm"
        await query.edit_message_text(
            "ONE-TIME override cancelled. The class profile is unchanged.",
            reply_markup=quiz_confirm_keyboard(class_mode=True),
        )
        return

    if data.startswith("quiz_override_level_") and quiz.get("state") == "override_level":
        level = data.removeprefix("quiz_override_level_")
        if level not in _VALID_LEVELS:
            await _expired_session(update, context)
            return
        quiz["level"] = level
        quiz["one_time_overrides"] = ["level"]
        quiz["state"] = "confirm"
        await query.edit_message_text(
            f"✏ ONE-TIME level: {level}\n\nThe saved class profile is unchanged.",
            reply_markup=quiz_confirm_keyboard(class_mode=True),
        )
        return

    if data == "quiz_cancel":
        if quiz.get("class_mode"):
            from class_dashboard_keyboards import class_dashboard_keyboard
            class_id = int(quiz["class_id"])
            revision = int(quiz["class_revision"])
            context.user_data.pop("quiz", None)
            await query.edit_message_text(
                "❌ Assessment Generator cancelled. No class data changed.",
                reply_markup=class_dashboard_keyboard(class_id, revision),
            )
            return
        context.user_data.pop("quiz", None)
        await query.edit_message_text(
            "❌ Assessment Generator cancelled.",
            reply_markup=start_menu_keyboard(),
        )
        return

    if data == "quiz_generate":
        await generate_quiz(update, context)
        return

    await _expired_session(update, context)


async def get_quiz_topic(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    quiz = _quiz_data(context)
    if quiz is None or update.message is None:
        return

    state = quiz.get("state")
    if state == "question_count_custom":
        count = _parse_question_count(update.message.text)
        if count is None:
            await update.message.reply_text(
                f"Please enter one number from {_MIN_QUESTION_COUNT} to {_MAX_QUESTION_COUNT}.\n\n"
                "Examples: 12 or ۱۲"
            )
            return

        quiz["question_count"] = count
        if quiz.get("class_mode") and quiz.get("level"):
            quiz["state"] = "topic"
            await update.message.reply_text(
                f"✅ Assessment Generator · {quiz['class_name']}\n\n"
                f"Question count: {count} · inherited level: {quiz['level']}\n\n"
                "Type the assessment topic or language focus.",
                reply_markup=back_cancel_keyboard("quiz_back_question_count", "quiz_cancel"),
            )
            return
        quiz["state"] = "level"
        await update.message.reply_text(
            "✅ Assessment Generator\n\n"
            "Step 4 of 6\n\n"
            f"Question count: {count}\n\n"
            "Choose the CEFR level.",
            reply_markup=level_keyboard("quiz", "quiz_back_question_count"),
        )
        return

    if state != "topic":
        return

    topic = " ".join((update.message.text or "").split())
    if len(topic) < 2:
        await update.message.reply_text(
            "Please type a topic with at least 2 characters."
        )
        return

    if len(topic) > 200:
        await update.message.reply_text(
            "Please keep the topic under 200 characters."
        )
        return

    quiz["topic"] = topic
    quiz["state"] = "confirm"
    question_count = int(quiz["question_count"])
    await update.message.reply_text(
        "✅ Assessment Generator\n\n"
        "Step 6 of 6\n\n"
        "Please review your assessment.\n\n"
        f"📋 Type: {quiz['assessment_type']}\n"
        f"🔢 Questions: {question_count}\n"
        f"🧱 Format: {quiz['question_format']}\n"
        f"📖 Level: {quiz['level']}\n"
        f"📝 Topic: {quiz['topic']}\n\n"
        "Ready to generate?",
        reply_markup=quiz_confirm_keyboard(class_mode=bool(quiz.get("class_mode"))),
    )


async def generate_quiz(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    quiz = _quiz_data(context)

    if query is None or quiz is None or quiz.get("state") != "confirm":
        await _expired_session(update, context)
        return

    required = (
        "assessment_type",
        "question_format",
        "question_count",
        "level",
        "topic",
    )
    if any(not quiz.get(field) for field in required):
        await _expired_session(update, context)
        return

    user = update.effective_user
    if user is None or not isinstance(getattr(user, "id", None), int):
        await _expired_session(update, context)
        return

    access = generation_access_for_user(user.id)
    if not bool(access.get("allowed")):
        context.user_data.pop("quiz", None)
        await query.edit_message_text(
            generation_block_message(access),
            reply_markup=subscription_limit_keyboard(),
        )
        return

    lang = resolve_lang(update, context)
    quiz["state"] = "generating"
    generating_msg = (
        "🧠 در حال ساخت آزمون کلاسی شما...\n\n"
        "TeacherOS در حال آماده‌سازی سوالات، پاسخ‌نامه، راهنمای تصحیح و نکات آموزشی است."
        if lang == "fa"
        else (
            "🧠 Generating your classroom-ready assessment...\n\n"
            "TeacherOS is creating the questions, answer key, scoring guide, and notes."
        )
    )
    await query.edit_message_text(generating_msg)

    try:
        async with typing_heartbeat(
            context.bot,
            update.effective_chat.id if update.effective_chat else None,
        ):
            generation = await generate_artifact(
                feature="assessment",
                telegram_user_id=user.id,
                model=selected_openrouter_model(access),
                current_request=(
                    f"Create a {quiz['assessment_type']} with {quiz['question_count']} "
                    f"{quiz['question_format']} items for {quiz['level']} learners about "
                    f"{quiz['topic']}."
                ),
                prompt_replacements=_prompt_replacements(quiz),
                class_id=int(quiz["class_id"]) if quiz.get("class_mode") else None,
                quality_requirements={"level": str(quiz["level"]), "answer_key": True},
            )
        result = generation.content
    except Exception:
        logger.exception("Assessment generation failed")
        quiz["state"] = "confirm"
        fail_msg = (
            "❌ تولید آزمون در این لحظه انجام نشد.\n\n"
            "انتخاب‌های شما ذخیره شده است. لطفاً وضعیت اینترنت یا تنظیمات را بررسی کرده "
            "و سپس روی «تولید آزمون» بزنید تا دوباره تلاش شود."
            if lang == "fa"
            else (
                "❌ I could not generate the assessment right now.\n\n"
                "Your choices are still saved. Check your connection or OpenRouter settings, "
                "then tap Generate Assessment to retry."
            )
        )
        await query.edit_message_text(
            fail_msg,
            reply_markup=quiz_confirm_keyboard(class_mode=bool(quiz.get("class_mode")), lang=lang),
        )
        return

    question_count = int(quiz["question_count"])
    material_id: int | None = None
    save_message = (
        "✅ آزمون با موفقیت تولید شد و در زیر نمایش داده شده است."
        if lang == "fa"
        else "✅ Assessment generated. It appears below."
    )
    try:
        if update.effective_user is None:
            raise ValueError("Telegram user details are unavailable.")
        material_id = save_generated_material(
            telegram_user=update.effective_user,
            material_type="assessment",
            subtype=str(quiz["assessment_type"]),
            title=f"{quiz['assessment_type']} — {quiz['topic']} ({quiz['level']})",
            level=str(quiz["level"]),
            topic=str(quiz["topic"]),
            content=result,
            metadata={
                "question_format": str(quiz["question_format"]),
                "question_count": question_count,
                "ai_provenance": generation_provenance(generation),
            },
            class_id=int(quiz["class_id"]) if quiz.get("class_mode") else None,
            objective_ids=generation.source_record_ids.get("class_objectives", []),
            ai_provenance=generation_provenance(generation),
            quality_scores=generation.quality_scores,
        )
        save_message = (
            "✅ آزمون تولید و به طور خودکار ذخیره شد.\n"
            f"شناسه کتابخانه: {material_id}\n\n"
            "از دکمه‌های زیر برای دانلود نسخه Word یا PDF استفاده کنید."
            if lang == "fa"
            else (
                "✅ Assessment generated and saved automatically.\n"
                f"Library ID: {material_id}\n\n"
                "Use the buttons below to download Word or PDF immediately."
            )
        )
    except Exception:
        logger.exception("Assessment was generated but could not be saved")
        save_message = (
            "⚠️ آزمون تولید شد اما ذخیره آن ناموفق بود.\n\n"
            "متن آزمون در زیر قابل مشاهده است."
            if lang == "fa"
            else (
                "⚠️ Assessment generated, but TeacherOS could not save it.\n\n"
                "The assessment still appears below, but export buttons are unavailable."
            )
        )

    await query.edit_message_text(
        save_message,
        reply_markup=(
            generated_material_export_keyboard(
                material_id,
                material_type="assessment",
                class_id=int(quiz["class_id"]) if quiz.get("class_mode") else None,
                lang=lang,
            )
            if material_id is not None
            else None
        ),
    )
    if query.message is not None:
        for start in range(0, len(result), 4000):
            await query.message.reply_text(result[start : start + 4000])

    context.user_data.pop("quiz", None)
