from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from class_service import get_class
from feature_flags import feature_enabled
from keyboards import (
    activity_type_keyboard,
    back_cancel_keyboard,
    level_keyboard,
    quiz_assessment_type_keyboard,
    start_menu_keyboard,
    worksheet_type_keyboard,
)


logger = logging.getLogger(__name__)
_CALLBACK = re.compile(r"^cg\|(?P<kind>ls|ac|ws|as)\|(?P<class_id>[0-9a-z]+)\|(?P<revision>[0-9a-z]+)$")


def class_generation_callback(kind: str, class_id: int, revision: int) -> str:
    return f"cg|{kind}|{class_id:x}|{revision:x}"


async def class_generation_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Start a generator with verified inherited class context."""
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    match = _CALLBACK.fullmatch(query.data or "")
    if match is None or not feature_enabled("continuity"):
        context.user_data.clear()
        await query.edit_message_text(
            "⚠️ Class-aware creation is unavailable. Quick Create is still available.",
            reply_markup=start_menu_keyboard(),
        )
        return
    class_id = int(match.group("class_id"), 16)
    revision = int(match.group("revision"), 16)
    record = get_class(telegram_user_id=user.id, class_id=class_id)
    if record is None or record.get("status") != "active" or int(record["revision"]) != revision:
        context.user_data.clear()
        await query.edit_message_text(
            "⚠️ This class changed or is unavailable. No generation was started.",
            reply_markup=start_menu_keyboard(),
        )
        return

    common = {
        "class_mode": True,
        "class_id": class_id,
        "class_revision": revision,
        "class_name": str(record["display_name"]),
        "inherited_level": record.get("level"),
        "one_time_overrides": [],
    }
    context.user_data.clear()
    context.user_data["active_class"] = {
        "id": class_id,
        "display_name": str(record["display_name"]),
        "revision": revision,
    }
    kind = match.group("kind")
    level = record.get("level")
    duration = record.get("lesson_duration_minutes")
    if kind == "ls":
        flow = {**common, "state": "topic" if level else "level"}
        if level:
            flow["level"] = level
        if duration:
            flow["duration"] = str(duration)
            flow["inherited_duration"] = str(duration)
        context.user_data["lesson"] = flow
        if level:
            await query.edit_message_text(
                f"📚 Lesson Planner · {record['display_name']}\n\n"
                f"Inherited: {level}" + (f" · {duration} minutes" if duration else "") +
                "\n\nType today's lesson topic. Class values can be changed later for this resource only.",
                reply_markup=back_cancel_keyboard("lesson_back_class", "lesson_cancel"),
            )
        else:
            await query.edit_message_text(
                f"📚 Lesson Planner · {record['display_name']}\n\n"
                "The class level is unknown. Choose it for this resource only.",
                reply_markup=level_keyboard("lesson", "lesson_back_class"),
            )
        return

    mapping = {
        "ac": ("activity", activity_type_keyboard(), "🎲 Activity Generator"),
        "ws": ("worksheet", worksheet_type_keyboard(), "📝 Worksheet Generator"),
        "as": ("quiz", quiz_assessment_type_keyboard(), "✅ Assessment Generator"),
    }
    flow_name, markup, title = mapping[kind]
    flow = {**common, "state": "assessment_type" if kind == "as" else "type"}
    if level:
        flow["level"] = level
    context.user_data[flow_name] = flow
    await query.edit_message_text(
        f"{title} · {record['display_name']}\n\n"
        + (f"Inherited CEFR level: {level}. " if level else "Class level is unknown. ")
        + "Choose the resource-specific option. Any later override is ONE-TIME.",
        reply_markup=markup,
    )
