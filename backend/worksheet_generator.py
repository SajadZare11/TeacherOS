from __future__ import annotations

import logging

from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ContextTypes

from ai_gateway import generate_artifact, generation_provenance
from database import save_generated_material
from home_ui import teacheros_home_text

from keyboards import (
    WORKSHEET_TYPE_OPTIONS,
    back_cancel_keyboard,
    generated_material_export_keyboard,
    level_keyboard,
    start_menu_keyboard,
    subscription_limit_keyboard,
    worksheet_confirm_keyboard,
    worksheet_type_keyboard,
)
from subscription_service import (
    generation_access_for_user,
    generation_block_message,
    selected_openrouter_model,
)

logger = logging.getLogger(__name__)

_VALID_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}


def _worksheet_data(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    worksheet = context.user_data.get("worksheet")
    return worksheet if isinstance(worksheet, dict) else None


async def _answer_callback(update: Update) -> None:
    query = update.callback_query
    if query is None:
        return

    try:
        await query.answer()
    except (TimedOut, NetworkError):
        logger.warning("Could not answer Telegram callback query.")


async def _expired_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("worksheet", None)
    query = update.callback_query
    if query is not None:
        await query.edit_message_text(
            "⌛ This worksheet-generator session expired.\n\nChoose an option below.",
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


def _prompt_replacements(worksheet: dict) -> dict[str, str]:
    worksheet_type = str(worksheet["type"])
    level = str(worksheet["level"])
    topic = str(worksheet["topic"])

    return {
        "{WORKSHEET_TYPE}": worksheet_type,
        "{LEVEL}": level,
        "{TOPIC}": topic,
        # These legacy placeholders remain supported while the prompt files evolve.
        "{LANGUAGE_FOCUS}": f"Automatically select suitable {worksheet_type.lower()} content for {topic}",
        "{SKILL_FOCUS}": worksheet_type,
        "{CONTEXT}": "General English classroom; printable and technology-free",
        "{CLASS_SIZE}": "Flexible for individual, pair, or group use",
        "{DURATION}": "Approximately 30–45 minutes",
    }

async def worksheet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    await _answer_callback(update)
    data = query.data or ""

    if data == "worksheet_start":
        context.user_data.clear()
        context.user_data["worksheet"] = {"state": "type"}
        await query.edit_message_text(
            "📝 Worksheet Generator\n\n"
            "Step 1 of 4\n\n"
            "Choose the worksheet type.",
            reply_markup=worksheet_type_keyboard(),
        )
        return

    worksheet = _worksheet_data(context)
    if worksheet is None:
        await _expired_session(update, context)
        return

    # ---------- Back navigation ----------
    if data == "worksheet_back_main":
        await _show_main_menu(update, context)
        return

    if data == "worksheet_back_type":
        if worksheet.get("state") != "level" and not (
            worksheet.get("class_mode") and worksheet.get("state") == "topic"
        ):
            await _expired_session(update, context)
            return

        if worksheet.get("class_mode"):
            worksheet.pop("type", None)
            worksheet.pop("topic", None)
            worksheet["level"] = worksheet.get("inherited_level") or worksheet.get("level")
            worksheet["state"] = "type"
        else:
            worksheet.clear()
            worksheet["state"] = "type"
        await query.edit_message_text(
            "📝 Worksheet Generator\n\n"
            "Step 1 of 4\n\n"
            "Choose the worksheet type.",
            reply_markup=worksheet_type_keyboard(),
        )
        return

    if data == "worksheet_back_level":
        if worksheet.get("state") != "topic":
            await _expired_session(update, context)
            return

        worksheet.pop("level", None)
        worksheet.pop("topic", None)
        worksheet["state"] = "level"
        await query.edit_message_text(
            "📝 Worksheet Generator\n\n"
            "Step 2 of 4\n\n"
            "Choose the CEFR level.",
            reply_markup=level_keyboard("worksheet", "worksheet_back_type"),
        )
        return

    if data == "worksheet_back_topic":
        if worksheet.get("state") != "confirm":
            await _expired_session(update, context)
            return

        worksheet.pop("topic", None)
        worksheet["state"] = "topic"
        await query.edit_message_text(
            "📝 Worksheet Generator\n\n"
            "Step 3 of 4\n\n"
            "Type the worksheet topic.\n\n"
            "Examples: Travel, Food, Technology, Jobs, Environment",
            reply_markup=back_cancel_keyboard(
                "worksheet_back_type" if worksheet.get("class_mode") else "worksheet_back_level",
                "worksheet_cancel",
            ),
        )
        return

    # ---------- Forward navigation ----------
    if data.startswith("worksheet_type_"):
        type_code = data.removeprefix("worksheet_type_")
        worksheet_type = WORKSHEET_TYPE_OPTIONS.get(type_code)
        if worksheet_type is None or worksheet.get("state") != "type":
            await _expired_session(update, context)
            return

        worksheet["type"] = worksheet_type
        worksheet.pop("topic", None)
        if worksheet.get("class_mode") and worksheet.get("level"):
            worksheet["state"] = "topic"
            await query.edit_message_text(
                f"📝 Worksheet Generator · {worksheet['class_name']}\n\n"
                f"Inherited level: {worksheet['level']}\n\nType the worksheet topic.",
                reply_markup=back_cancel_keyboard("worksheet_back_type", "worksheet_cancel"),
            )
            return
        worksheet.pop("level", None)
        worksheet["state"] = "level"
        await query.edit_message_text(
            "📝 Worksheet Generator\n\n"
            "Step 2 of 4\n\n"
            "Choose the CEFR level.",
            reply_markup=level_keyboard("worksheet", "worksheet_back_type"),
        )
        return

    if data.startswith("worksheet_level_"):
        level = data.removeprefix("worksheet_level_")
        if level not in _VALID_LEVELS or worksheet.get("state") != "level":
            await _expired_session(update, context)
            return

        worksheet["level"] = level
        worksheet.pop("topic", None)
        worksheet["state"] = "topic"
        await query.edit_message_text(
            "📝 Worksheet Generator\n\n"
            "Step 3 of 4\n\n"
            "Type the worksheet topic.\n\n"
            "Examples: Travel, Food, Technology, Jobs, Environment",
            reply_markup=back_cancel_keyboard(
                "worksheet_back_level",
                "worksheet_cancel",
            ),
        )
        return

    if data == "worksheet_override" and worksheet.get("class_mode"):
        worksheet["state"] = "override_level"
        await query.edit_message_text(
            "✏ ONE-TIME level override\n\nChoose a level for this worksheet only. The class profile will not change.",
            reply_markup=level_keyboard("worksheet_override", "worksheet_back_override"),
        )
        return

    if data == "worksheet_back_override" and worksheet.get("class_mode"):
        worksheet["state"] = "confirm"
        await query.edit_message_text(
            "ONE-TIME override cancelled. The class profile is unchanged.",
            reply_markup=worksheet_confirm_keyboard(class_mode=True),
        )
        return

    if data.startswith("worksheet_override_level_") and worksheet.get("state") == "override_level":
        level = data.removeprefix("worksheet_override_level_")
        if level not in _VALID_LEVELS:
            await _expired_session(update, context)
            return
        worksheet["level"] = level
        worksheet["one_time_overrides"] = ["level"]
        worksheet["state"] = "confirm"
        await query.edit_message_text(
            f"✏ ONE-TIME level: {level}\n\nThe saved class profile is unchanged.",
            reply_markup=worksheet_confirm_keyboard(class_mode=True),
        )
        return

    if data == "worksheet_cancel":
        if worksheet.get("class_mode"):
            from class_dashboard_keyboards import class_dashboard_keyboard
            class_id = int(worksheet["class_id"])
            revision = int(worksheet["class_revision"])
            context.user_data.pop("worksheet", None)
            await query.edit_message_text(
                "❌ Worksheet Generator cancelled. No class data changed.",
                reply_markup=class_dashboard_keyboard(class_id, revision),
            )
            return
        context.user_data.pop("worksheet", None)
        await query.edit_message_text(
            "❌ Worksheet Generator cancelled.",
            reply_markup=start_menu_keyboard(),
        )
        return

    if data == "worksheet_generate":
        await generate_worksheet(update, context)
        return

    await _expired_session(update, context)


async def get_worksheet_topic(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    worksheet = _worksheet_data(context)
    if worksheet is None or worksheet.get("state") != "topic" or update.message is None:
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

    worksheet["topic"] = topic
    worksheet["state"] = "confirm"
    await update.message.reply_text(
        "📝 Worksheet Generator\n\n"
        "Step 4 of 4\n\n"
        "Please review your worksheet.\n\n"
        f"📄 Type: {worksheet['type']}\n"
        f"📖 Level: {worksheet['level']}\n"
        f"📝 Topic: {worksheet['topic']}\n\n"
        "Ready to generate?",
        reply_markup=worksheet_confirm_keyboard(class_mode=bool(worksheet.get("class_mode"))),
    )


async def generate_worksheet(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    worksheet = _worksheet_data(context)

    if query is None or worksheet is None or worksheet.get("state") != "confirm":
        await _expired_session(update, context)
        return

    required = ("type", "level", "topic")
    if any(not worksheet.get(field) for field in required):
        await _expired_session(update, context)
        return

    user = update.effective_user
    if user is None or not isinstance(getattr(user, "id", None), int):
        await _expired_session(update, context)
        return

    access = generation_access_for_user(user.id)
    if not bool(access.get("allowed")):
        context.user_data.pop("worksheet", None)
        await query.edit_message_text(
            generation_block_message(access),
            reply_markup=subscription_limit_keyboard(),
        )
        return

    worksheet["state"] = "generating"
    await query.edit_message_text(
        "🧠 Generating your classroom-ready worksheet...\n\n"
        "TeacherOS is creating the exercises, extension, answer key, and notes."
    )

    try:
        generation = await generate_artifact(
            feature="worksheet",
            telegram_user_id=user.id,
            model=selected_openrouter_model(access),
            current_request=(
                f"Create a {worksheet['type']} worksheet for {worksheet['level']} learners "
                f"about {worksheet['topic']}."
            ),
            prompt_replacements=_prompt_replacements(worksheet),
            class_id=int(worksheet["class_id"]) if worksheet.get("class_mode") else None,
            quality_requirements={"level": str(worksheet["level"]), "answer_key": True},
        )
        result = generation.content
    except Exception:
        logger.exception("Worksheet generation failed")
        worksheet["state"] = "confirm"
        await query.edit_message_text(
            "❌ I could not generate the worksheet right now.\n\n"
            "Your choices are still saved. Check your connection or OpenRouter settings, "
            "then tap Generate Worksheet to retry.",
            reply_markup=worksheet_confirm_keyboard(class_mode=bool(worksheet.get("class_mode"))),
        )
        return

    material_id: int | None = None
    save_message = "✅ Worksheet generated. It appears below."
    try:
        if update.effective_user is None:
            raise ValueError("Telegram user details are unavailable.")
        material_id = save_generated_material(
            telegram_user=update.effective_user,
            material_type="worksheet",
            subtype=str(worksheet["type"]),
            title=f"{worksheet['type']} Worksheet — {worksheet['topic']} ({worksheet['level']})",
            level=str(worksheet["level"]),
            topic=str(worksheet["topic"]),
            content=result,
            metadata={"ai_provenance": generation_provenance(generation)},
            class_id=int(worksheet["class_id"]) if worksheet.get("class_mode") else None,
            objective_ids=generation.source_record_ids.get("class_objectives", []),
            ai_provenance=generation_provenance(generation),
            quality_scores=generation.quality_scores,
        )
        save_message = (
            "✅ Worksheet generated and saved automatically.\n"
            f"Library ID: {material_id}\n\n"
            "Use the buttons below to download Word or PDF immediately."
        )
    except Exception:
        logger.exception("Worksheet was generated but could not be saved")
        save_message = (
            "⚠️ Worksheet generated, but TeacherOS could not save it.\n\n"
            "The worksheet still appears below, but export buttons are unavailable."
        )

    await query.edit_message_text(
        save_message,
        reply_markup=(
            generated_material_export_keyboard(
                material_id,
                material_type="worksheet",
                class_id=int(worksheet["class_id"]) if worksheet.get("class_mode") else None,
            )
            if material_id is not None
            else None
        ),
    )
    if query.message is not None:
        for start in range(0, len(result), 4000):
            await query.message.reply_text(result[start : start + 4000])

    context.user_data.pop("worksheet", None)
