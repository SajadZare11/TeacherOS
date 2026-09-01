from __future__ import annotations

import json
import logging
import re
from typing import Any

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from class_service import ClassFeatureDisabledError, get_class, list_classes
from class_dashboard_panel import DASHBOARD_ACTIONS, handle_dashboard_callback
from class_setup_panel import CHOICE_LABELS, SETUP_ACTIONS, handle_setup_callback
from class_setup_service import get_setup_draft
from feature_flags import feature_enabled
from home_ui import teacheros_home_text
from database import register_telegram_user
from ui_service import set_active_class
from keyboards import (
    analyze_picker_keyboard,
    class_detail_keyboard,
    class_intro_keyboard,
    class_linked_back_keyboard,
    class_list_keyboard,
    class_recovery_keyboard,
    quick_create_keyboard,
    start_menu_keyboard,
)


logger = logging.getLogger(__name__)

_CLASS_CALLBACK = re.compile(
    r"^v1\|(?P<domain>cl|rc)\|(?P<action>[a-z0-9]{1,8})\|"
    r"(?P<object_id>[0-9a-z]{1,13})\|(?P<revision>[0-9a-z]{1,6})$"
)


async def _safe_edit(query: Any, text: str, *, reply_markup: Any) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


def _decode_base36(value: str) -> int:
    decoded = int(value, 36)
    if decoded < 1:
        raise ValueError("Expected a positive callback identifier.")
    return decoded


def _profile_lines(class_record: dict[str, Any]) -> list[str]:
    try:
        setup_profile = json.loads(str(class_record.get("setup_profile_json") or "{}"))
    except json.JSONDecodeError:
        setup_profile = {}
    if not isinstance(setup_profile, dict):
        setup_profile = {}
    level = class_record.get("level") or setup_profile.get("level_choice")
    age_group = class_record.get("age_group") or setup_profile.get("age_group_choice")
    class_size = class_record.get("learner_count_band") or setup_profile.get(
        "learner_count_band_choice"
    )
    duration = class_record.get("lesson_duration_minutes")
    if isinstance(duration, int):
        duration = f"{duration} minutes"
    coursebook = class_record.get("coursebook")
    if coursebook and class_record.get("coursebook_unit"):
        coursebook = f"{coursebook} · {class_record['coursebook_unit']}"
    elif not coursebook:
        coursebook = setup_profile.get("coursebook_state")

    def choice_text(field: str) -> str:
        choices = setup_profile.get(field)
        if not isinstance(choices, list):
            return ""
        labels = CHOICE_LABELS[field]
        return ", ".join(
            labels.get(str(choice), str(choice).replace("_", " ").title())
            for choice in choices
        )

    values = (
        ("Level", level),
        ("Age group", age_group),
        ("Class size", class_size),
        ("Cadence", class_record.get("cadence")),
        ("Goal", class_record.get("goal")),
        ("Usual duration", duration),
        ("Weak areas", choice_text("weak_areas")),
        ("Coursebook", coursebook),
        ("Equipment", choice_text("equipment")),
        ("Teaching preference", choice_text("teaching_preferences")),
    )
    return [
        f"{label}: {str(value).replace('_', ' ').title()}"
        for label, value in values
        if value
    ]


async def _recover(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await _safe_edit(
        query,
        "⚠️ This class view changed, expired, or is no longer available.\n\n"
        "No change was made. Refresh your own class list or return home.",
        reply_markup=class_recovery_keyboard(),
    )


async def _show_class_list(
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    telegram_user_id: int,
    archived: bool,
) -> None:
    context.user_data.pop("active_class", None)
    status = "archived" if archived else "active"
    records = list_classes(telegram_user_id=telegram_user_id, status=status, limit=50)
    draft = None if archived else get_setup_draft(telegram_user_id=telegram_user_id)
    if archived:
        text = (
            "🗃 Archived Classes\n\n"
            "Archived classes are kept out of your active workspace. "
            "Open one to review its saved context."
        )
        if not records:
            text += "\n\nYou do not have any archived classes."
    else:
        text = (
            "🏫 My Classes\n\n"
            "A class remembers the level, goals, and teaching history for a recurring "
            "group, so future work can continue from shared context."
        )
        if records:
            text += "\n\nChoose an active class."
        else:
            text += (
                "\n\nYou have no active classes yet. Create one for recurring work, "
                "or use Quick Create when you only need a one-off resource."
            )
    await _safe_edit(
        query,
        text,
        reply_markup=class_list_keyboard(
            records,
            archived=archived,
            has_draft=draft is not None,
        ),
    )


async def home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open a class-aware home utility while keeping legacy generator routes intact."""
    query = update.callback_query
    user = update.effective_user
    if query is None:
        return
    await query.answer()
    context.user_data.clear()

    if not feature_enabled("classes"):
        await _safe_edit(
            query,
            "TeacherOS Quick Create is ready. Choose a tool below.",
            reply_markup=start_menu_keyboard(),
        )
        return

    data = query.data or ""
    if data == "home_quick":
        await _safe_edit(
            query,
            "⚡ Quick Create\n\n"
            "Create a one-off resource without setting up a class. "
            "Your four existing tools work exactly as before.",
            reply_markup=quick_create_keyboard(),
        )
        return

    if data == "home_analyze" and user is not None and isinstance(user.id, int):
        try:
            records = list_classes(
                telegram_user_id=user.id,
                status="active",
                limit=50,
            )
        except Exception:
            logger.exception("Could not load classes for Analyze Work")
            await _recover(query, context)
            return
        text = (
            "🔬 Analyze Work\n\n"
            "Analysis belongs to a class so TeacherOS never guesses which learners or "
            "teaching history you mean. Choose an active class first."
        )
        if not records:
            text += (
                "\n\nYou have no active classes yet. My Classes explains what a class "
                "remembers; Quick Create remains available for one-off work."
            )
        await _safe_edit(query, text, reply_markup=analyze_picker_keyboard(records))
        return

    await _recover(query, context)


async def class_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render owner-scoped class navigation and safe stale-callback recovery."""
    query = update.callback_query
    user = update.effective_user
    if query is None:
        return
    await query.answer()
    if user is None or not isinstance(getattr(user, "id", None), int):
        await _recover(query, context)
        return
    if not feature_enabled("classes"):
        context.user_data.clear()
        await _safe_edit(
            query,
            "My Classes is not enabled. Quick Create is still available.",
            reply_markup=start_menu_keyboard(),
        )
        return

    match = _CLASS_CALLBACK.fullmatch(query.data or "")
    if match is None:
        await _recover(query, context)
        return
    domain = match.group("domain")
    action = match.group("action")

    try:
        if domain == "cl" and action in SETUP_ACTIONS:
            await handle_setup_callback(
                update,
                context,
                action=action,
                object_id=match.group("object_id"),
                revision_text=match.group("revision"),
            )
            return
        if domain == "cl" and action in DASHBOARD_ACTIONS:
            await handle_dashboard_callback(
                update,
                context,
                action=action,
                object_id=match.group("object_id"),
                revision_text=match.group("revision"),
            )
            return
        if domain == "rc" and action == "home":
            context.user_data.clear()
            await _safe_edit(
                query,
                teacheros_home_text(),
                reply_markup=start_menu_keyboard(),
            )
            return
        if domain == "cl" and action == "home":
            context.user_data.clear()
            await _safe_edit(
                query,
                teacheros_home_text(),
                reply_markup=start_menu_keyboard(),
            )
            return
        if domain == "cl" and action == "list":
            await _show_class_list(
                query,
                context,
                telegram_user_id=user.id,
                archived=False,
            )
            return
        if domain == "cl" and action == "archive":
            await _show_class_list(
                query,
                context,
                telegram_user_id=user.id,
                archived=True,
            )
            return
        if domain == "cl" and action == "why":
            context.user_data.pop("active_class", None)
            lead = (
                "💡 Why Use My Classes?"
            )
            await _safe_edit(
                query,
                f"{lead}\n\n"
                "Use a class for recurring teaching: TeacherOS can remember the class "
                "label, level, goals, and lesson history. This makes later planning and "
                "work analysis continuous instead of starting from zero.\n\n"
                "Use Quick Create when the work is one-off. Class setup will ask only for "
                "short teaching context—never student names.",
                reply_markup=class_intro_keyboard(),
            )
            return
        if domain == "rc" and action == "class":
            object_id = _decode_base36(match.group("object_id"))
            class_record = get_class(telegram_user_id=user.id, class_id=object_id)
            if class_record is None:
                await _recover(query, context)
                return
        elif domain == "cl" and action in {"open", "analyze"}:
            object_id = _decode_base36(match.group("object_id"))
            expected_revision = _decode_base36(match.group("revision"))
            class_record = get_class(telegram_user_id=user.id, class_id=object_id)
            if class_record is None or int(class_record["revision"]) != expected_revision:
                await _recover(query, context)
                return
        else:
            await _recover(query, context)
            return

        context.user_data.clear()
        context.user_data["active_class"] = {
            "id": int(class_record["id"]),
            "display_name": str(class_record["display_name"]),
            "revision": int(class_record["revision"]),
        }
        # Persist the verified active class for class-aware tools (favorites,
        # search, and quick return). Never trust a callback ID without the
        # ownership check already performed by get_class above.
        if class_record["status"] == "active":
            try:
                set_active_class(
                    register_telegram_user(user),
                    int(class_record["id"]),
                )
            except Exception:
                logger.exception("Could not persist active class preference")
        class_name = str(class_record["display_name"])
        if action == "analyze":
            await _safe_edit(
                query,
                "🔬 Analyze Work\n"
                f"🏫 Active class: {class_name}\n\n"
                "The class context is explicit and verified. The evidence-analysis workflow "
                "is controlled by its own rollout flag and is not enabled on this screen yet.",
                reply_markup=class_linked_back_keyboard(
                    int(class_record["id"]),
                    int(class_record["revision"]),
                ),
            )
            return

        context_label = (
            "Archived class" if class_record["status"] == "archived" else "Active class"
        )
        lines = [
            f"🏫 {context_label}: {class_name}",
            "",
            "This screen is linked to the class named above.",
        ]
        profile = _profile_lines(class_record)
        if profile:
            lines.extend(["", *profile])
        if class_record["status"] == "archived":
            lines.extend(["", "Status: Archived (read-only context)"])
        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=class_detail_keyboard(
                int(class_record["id"]),
                int(class_record["revision"]),
                archived=class_record["status"] == "archived",
            ),
        )
    except (ClassFeatureDisabledError, ValueError):
        await _recover(query, context)
    except Exception:
        logger.exception("Could not render TeacherOS class navigation")
        await _recover(query, context)
