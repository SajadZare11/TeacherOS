from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from ai_gateway import generate_artifact, generation_provenance
from database import (
    get_user_material,
    save_beta_feedback,
    save_generated_material,
)
from keyboards import (
    generated_material_export_keyboard,
    lesson_replace_keyboard,
    lesson_schedule_keyboard,
)
from lesson_history_service import schedule_material_lesson
from subscription_service import (
    generation_access_for_user,
    generation_block_message,
    selected_openrouter_model,
)


logger = logging.getLogger(__name__)
_CALLBACK = re.compile(
    r"^ma\|(?P<action>sv|ad|rg|nx|rp|pd|pr|pk)\|"
    r"(?P<material_id>[1-9][0-9]*)(?:\|(?P<option>td|tm|nc|lt|na))?$"
)
_DATE_CODES = {"td": "today", "tm": "tomorrow", "nc": "next_class", "lt": "later"}


def _prompt_replacements(material: dict, change: str) -> dict[str, str]:
    level = str(material.get("level") or "Not specified")
    topic = str(material.get("topic") or "Not specified")
    subtype = str(material.get("subtype") or material["material_type"])
    metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
    feature = str(material["material_type"])
    if feature == "lesson":
        return {
            "{LEVEL}": level, "{TOPIC}": topic,
            "{GRAMMAR}": str(metadata.get("grammar") or "Not specified"),
            "{VOCABULARY}": "Not specified",
            "{DURATION}": str(metadata.get("duration_minutes") or 45),
            "{GOALS}": f"Create a classroom-ready lesson. Requested change: {change}",
        }
    if feature == "activity":
        return {
            "{{activity_type}}": subtype, "{{activity}}": subtype,
            "{{level}}": level, "{{topic}}": topic,
            "{{target_language}}": "Not specified",
            "{{context}}": f"Requested change: {change}",
        }
    if feature == "worksheet":
        return {
            "{WORKSHEET_TYPE}": subtype, "{LEVEL}": level, "{TOPIC}": topic,
            "{LANGUAGE_FOCUS}": f"Suitable content; requested change: {change}",
            "{SKILL_FOCUS}": subtype, "{CONTEXT}": "General English classroom",
            "{CLASS_SIZE}": "Flexible", "{DURATION}": "30–45 minutes",
        }
    return {
        "{ASSESSMENT_TYPE}": subtype,
        "{QUESTION_FORMAT}": str(metadata.get("question_format") or "Mixed"),
        "{LEVEL}": level, "{TOPIC}": topic,
        "{NUMBER_OF_QUESTIONS}": str(metadata.get("question_count") or 10),
        "{PURPOSE}": f"Classroom assessment; requested change: {change}",
        "{FORMAT_RULES}": "Use clear, unambiguous items.",
        "{QUIZ_TYPE}": subtype, "{GRAMMAR}": "Suitable for topic",
        "{VOCABULARY}": topic, "{SKILLS}": "Appropriate language skills",
    }


async def material_action_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    match = _CALLBACK.fullmatch(query.data or "")
    if match is None:
        await query.answer("Invalid material action.", show_alert=True)
        return
    material_id = int(match.group("material_id"))
    material = get_user_material(telegram_user_id=user.id, material_id=material_id)
    if material is None:
        await query.answer("Material unavailable.", show_alert=True)
        return
    action = match.group("action")
    if action == "sv":
        await query.answer("Already saved in your library.", show_alert=True)
        return
    if action == "nx":
        await query.answer()
        if query.message is not None:
            await query.message.reply_text(
                "📅 When should this become the next lesson?\n\n"
                "Choosing a date changes the lesson from Generated to Planned. "
                "Keeping it generated does not add anything to taught history.",
                reply_markup=lesson_schedule_keyboard(material_id),
            )
        return
    if action == "pk":
        await query.answer("No plan changed. The generated resource stays in your library.", show_alert=True)
        return
    if action in {"pd", "pr"}:
        option = match.group("option")
        date_choice = _DATE_CODES.get(str(option or ""))
        if date_choice is None:
            await query.answer("Choose a valid lesson date.", show_alert=True)
            return
        result = schedule_material_lesson(
            telegram_user_id=user.id,
            material_id=material_id,
            date_choice=date_choice,
            replace=action == "pr",
        )
        status = str(result["status"])
        await query.answer()
        if query.message is None:
            return
        if status == "conflict":
            conflict = result.get("conflict") or {}
            await query.message.reply_text(
                "⚠️ A next lesson is already planned: "
                f"{conflict.get('title', 'Current plan')}.\n\n"
                "Replace cancels that plan but keeps its generated resource and audit history.",
                reply_markup=lesson_replace_keyboard(material_id, str(option)),
            )
        elif status in {"planned", "replaced", "already_planned"}:
            lesson = result.get("lesson") or {}
            when = lesson.get("scheduled_for") or "later / date not set"
            prefix = "✅ Replaced the previous plan." if status == "replaced" else "✅ Next lesson planned."
            if status == "already_planned":
                prefix = "✅ This lesson is already the current plan."
            await query.message.reply_text(
                f"{prefix}\n\n{lesson.get('title', material.get('title'))}\nDate: {when}\n"
                "The generated material remains unchanged in the library."
            )
        else:
            await query.message.reply_text(
                "⚠️ This lesson cannot be planned from its current state. No history changed."
            )
        return
    context.user_data["material_action"] = {
        "state": "report" if action == "rp" else "change",
        "action": action,
        "material_id": material_id,
    }
    await query.answer()
    if query.message is not None:
        await query.message.reply_text(
            "Describe the problem (5–2,000 characters). Your material content is not included."
            if action == "rp"
            else "Describe the ONE change you want. The original stays saved and a new version will be created."
        )


async def get_material_action_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    state = context.user_data.get("material_action")
    user = update.effective_user
    if not isinstance(state, dict) or update.message is None or user is None:
        return
    text = " ".join((update.message.text or "").split())
    if len(text) < 5 or len(text) > 1_950:
        await update.message.reply_text("Please enter 5–1,950 characters.")
        return
    material_id = int(state["material_id"])
    material = get_user_material(telegram_user_id=user.id, material_id=material_id)
    if material is None:
        context.user_data.pop("material_action", None)
        context.user_data["material_action_consumed"] = True
        await update.message.reply_text("⚠️ That material is no longer available.")
        return
    if state.get("state") == "report":
        save_beta_feedback(
            telegram_user=user, rating=1, area=str(material["material_type"]),
            message=f"Material #{material_id}: {text}",
        )
        context.user_data.pop("material_action", None)
        context.user_data["material_action_consumed"] = True
        await update.message.reply_text("✅ Problem report saved. Thank you.")
        return

    access = generation_access_for_user(user.id)
    if not bool(access.get("allowed")):
        await update.message.reply_text(generation_block_message(access))
        return
    try:
        metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
        quality = {"level": str(material.get("level") or "")}
        if material["material_type"] == "lesson":
            quality["duration_minutes"] = str(metadata.get("duration_minutes") or "")
        if material["material_type"] in {"worksheet", "assessment"}:
            quality["answer_key"] = True
        generation = await generate_artifact(
            feature=str(material["material_type"]), telegram_user_id=user.id,
            model=selected_openrouter_model(access),
            current_request=f"Adapt material #{material_id}. Requested change: {text}",
            prompt_replacements=_prompt_replacements(material, text),
            class_id=material.get("class_id"), quality_requirements=quality,
        )
        new_metadata = dict(metadata)
        new_metadata.update({
            "adapted_from_material_id": material_id,
            "requested_change": text,
            "ai_provenance": generation_provenance(generation),
        })
        new_id = save_generated_material(
            telegram_user=user, material_type=str(material["material_type"]),
            subtype=material.get("subtype"), title=f"{material['title']} — Adapted",
            level=material.get("level"), topic=material.get("topic"),
            content=generation.content, metadata=new_metadata,
            class_id=material.get("class_id"),
            objective_ids=generation.source_record_ids.get("class_objectives", []),
            ai_provenance=generation_provenance(generation),
            quality_scores=generation.quality_scores,
        )
    except Exception:
        logger.exception("Material adaptation failed")
        await update.message.reply_text(
            "❌ I could not safely regenerate it. Your requested change is still saved here; send it again to retry."
        )
        return
    context.user_data.pop("material_action", None)
    context.user_data["material_action_consumed"] = True
    await update.message.reply_text(
        f"✅ New adapted version saved as Library ID #{new_id}. The original was not changed.",
        reply_markup=generated_material_export_keyboard(
            new_id, material_type=str(material["material_type"]),
            class_id=material.get("class_id"),
        ),
    )
