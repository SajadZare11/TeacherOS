from __future__ import annotations

import logging
import math
from typing import Any

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from database import (
    count_user_materials,
    delete_user_material,
    get_user_material,
    list_user_materials,
    register_telegram_user,
)
from keyboards import (
    library_delete_keyboard,
    library_list_keyboard,
    library_material_keyboard,
    start_menu_keyboard,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 6
VALID_FILTERS = {"all", "lesson", "activity", "worksheet", "assessment"}

TYPE_LABELS = {
    "lesson": "Lesson Plan",
    "activity": "Activity",
    "worksheet": "Worksheet",
    "assessment": "Assessment",
}

TYPE_ICONS = {
    "lesson": "📚",
    "activity": "🎲",
    "worksheet": "📝",
    "assessment": "✅",
}


def _normalize_filter(value: str) -> str:
    normalized = value.strip().lower()
    return normalized if normalized in VALID_FILTERS else "all"


def _material_type_for_database(selected_filter: str) -> str | None:
    return None if selected_filter == "all" else selected_filter


def _format_created_at(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "Unknown"
    # SQLite CURRENT_TIMESTAMP is stored as UTC in YYYY-MM-DD HH:MM:SS format.
    return f"{text[:16]} UTC"


def _library_heading(selected_filter: str) -> str:
    labels = {
        "all": "All Materials",
        "lesson": "Lesson Plans",
        "activity": "Activities",
        "worksheet": "Worksheets",
        "assessment": "Assessments",
    }
    return labels[selected_filter]


def _format_library_page(
    *,
    selected_filter: str,
    total: int,
    page: int,
    total_pages: int,
    notice: str | None = None,
) -> str:
    lines = ["📁 My TeacherOS Library", ""]
    if notice:
        lines.extend([notice, ""])

    lines.append(f"Filter: {_library_heading(selected_filter)}")
    lines.append(f"Saved materials: {total}")

    if total:
        lines.extend(
            [
                f"Page: {page + 1} of {total_pages}",
                "",
                "Choose a material to open it.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "No materials are saved in this section yet.",
                "Generate a new classroom resource and TeacherOS will save it automatically.",
            ]
        )

    return "\n".join(lines)


def _format_material_summary(material: dict[str, Any]) -> str:
    material_type = str(material.get("material_type") or "")
    icon = TYPE_ICONS.get(material_type, "📄")
    type_label = TYPE_LABELS.get(material_type, "Material")

    lines = [
        f"{icon} {material.get('title') or 'Untitled Material'}",
        "",
        f"Library ID: {material.get('id')}",
        f"Type: {type_label}",
    ]

    subtype = str(material.get("subtype") or "").strip()
    level = str(material.get("level") or "").strip()
    topic = str(material.get("topic") or "").strip()

    if subtype and subtype.lower() != type_label.lower():
        lines.append(f"Subtype: {subtype}")
    if level:
        lines.append(f"CEFR level: {level}")
    if topic:
        lines.append(f"Topic: {topic}")

    metadata = material.get("metadata")
    if isinstance(metadata, dict):
        grammar = str(metadata.get("grammar") or "").strip()
        duration = metadata.get("duration_minutes")
        question_format = str(metadata.get("question_format") or "").strip()
        question_count = metadata.get("question_count")

        if grammar:
            lines.append(f"Grammar: {grammar}")
        if isinstance(duration, int):
            lines.append(f"Duration: {duration} minutes")
        if question_format:
            lines.append(f"Question format: {question_format}")
        if isinstance(question_count, int):
            lines.append(f"Questions: {question_count}")

    lines.append(f"Saved: {_format_created_at(material.get('created_at'))}")
    return "\n".join(lines)


async def _safe_edit(query: Any, text: str, *, reply_markup: Any = None) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _show_library_page(
    update: Update,
    *,
    selected_filter: str = "all",
    page: int = 0,
    notice: str | None = None,
) -> None:
    user = update.effective_user
    if user is None or not isinstance(getattr(user, "id", None), int):
        if update.effective_message is not None:
            await update.effective_message.reply_text(
                "❌ TeacherOS could not identify your Telegram account. Send /start and try again."
            )
        return

    selected_filter = _normalize_filter(selected_filter)
    database_filter = _material_type_for_database(selected_filter)
    total = count_user_materials(
        telegram_user_id=user.id,
        material_type=database_filter,
    )
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(max(page, 0), total_pages - 1)
    materials = list_user_materials(
        telegram_user_id=user.id,
        material_type=database_filter,
        limit=PAGE_SIZE,
        offset=page * PAGE_SIZE,
    )

    text = _format_library_page(
        selected_filter=selected_filter,
        total=total,
        page=page,
        total_pages=total_pages,
        notice=notice,
    )
    keyboard = library_list_keyboard(
        materials,
        selected_filter=selected_filter,
        page=page,
        total_pages=total_pages,
    )

    if update.callback_query is not None:
        await _safe_edit(update.callback_query, text, reply_markup=keyboard)
    elif update.message is not None:
        await update.message.reply_text(text, reply_markup=keyboard)


async def library_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open the current teacher's private saved-material library."""
    context.user_data.clear()
    if update.effective_user is not None:
        try:
            register_telegram_user(update.effective_user)
        except Exception:
            logger.exception("Could not register user before opening the library")

    try:
        await _show_library_page(update)
    except Exception:
        logger.exception("Could not open TeacherOS library")
        if update.effective_message is not None:
            await update.effective_message.reply_text(
                "❌ TeacherOS could not open your library.\n\n"
                "Run python backend/check_project.py, then send /library again."
            )


async def _open_material(
    update: Update,
    *,
    material_id: int,
    selected_filter: str,
    page: int,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return

    material = get_user_material(
        telegram_user_id=user.id,
        material_id=material_id,
    )
    if material is None:
        await _show_library_page(
            update,
            selected_filter=selected_filter,
            page=page,
            notice="⚠️ That material no longer exists or does not belong to your account.",
        )
        return

    await _safe_edit(
        query,
        _format_material_summary(material)
        + "\n\n📄 The complete classroom material appears below.",
    )

    content = str(material.get("content") or "").strip()
    if not content:
        content = "This saved material has no readable content."
    chunks = [content[start : start + 3800] for start in range(0, len(content), 3800)]

    if query.message is None:
        return

    for index, chunk in enumerate(chunks):
        keyboard = None
        if index == len(chunks) - 1:
            keyboard = library_material_keyboard(
                material_id,
                selected_filter=selected_filter,
                page=page,
            )
        await query.message.reply_text(chunk, reply_markup=keyboard)


async def _request_delete(
    update: Update,
    *,
    material_id: int,
    selected_filter: str,
    page: int,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return

    material = get_user_material(
        telegram_user_id=user.id,
        material_id=material_id,
    )
    if material is None:
        await _show_library_page(
            update,
            selected_filter=selected_filter,
            page=page,
            notice="⚠️ That material no longer exists.",
        )
        return

    if query.message is not None:
        await query.message.reply_text(
            "🗑 Delete this material permanently?\n\n"
            f"#{material_id} — {material.get('title') or 'Untitled Material'}\n\n"
            "This cannot be undone.",
            reply_markup=library_delete_keyboard(
                material_id,
                selected_filter=selected_filter,
                page=page,
            ),
        )


async def _confirm_delete(
    update: Update,
    *,
    material_id: int,
    selected_filter: str,
    page: int,
) -> None:
    user = update.effective_user
    if user is None:
        return

    deleted = delete_user_material(
        telegram_user_id=user.id,
        material_id=material_id,
    )
    notice = (
        f"✅ Library item #{material_id} was deleted."
        if deleted
        else "⚠️ That material no longer exists or does not belong to your account."
    )
    await _show_library_page(
        update,
        selected_filter=selected_filter,
        page=page,
        notice=notice,
    )


async def library_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    await query.answer()
    data = query.data or ""

    try:
        if data == "library_start":
            context.user_data.clear()
            await _show_library_page(update)
            return

        if data == "library_main":
            context.user_data.clear()
            await _safe_edit(
                query,
                "👋 TeacherOS Main Menu\n\nChoose what you'd like to create today.",
                reply_markup=start_menu_keyboard(),
            )
            return

        parts = data.split("_")

        if len(parts) == 4 and parts[:2] == ["library", "filter"]:
            selected_filter = _normalize_filter(parts[2])
            page = int(parts[3])
            await _show_library_page(
                update,
                selected_filter=selected_filter,
                page=page,
            )
            return

        if len(parts) == 4 and parts[:2] == ["library", "page"]:
            selected_filter = _normalize_filter(parts[2])
            page = int(parts[3])
            await _show_library_page(
                update,
                selected_filter=selected_filter,
                page=page,
            )
            return

        if len(parts) == 5 and parts[:2] == ["library", "item"]:
            await _open_material(
                update,
                material_id=int(parts[2]),
                selected_filter=_normalize_filter(parts[3]),
                page=int(parts[4]),
            )
            return

        if len(parts) == 5 and parts[:2] == ["library", "delete"]:
            await _request_delete(
                update,
                material_id=int(parts[2]),
                selected_filter=_normalize_filter(parts[3]),
                page=int(parts[4]),
            )
            return

        if len(parts) == 6 and parts[:3] == ["library", "delete", "yes"]:
            await _confirm_delete(
                update,
                material_id=int(parts[3]),
                selected_filter=_normalize_filter(parts[4]),
                page=int(parts[5]),
            )
            return

        if len(parts) == 6 and parts[:3] == ["library", "delete", "no"]:
            material_id = int(parts[3])
            selected_filter = _normalize_filter(parts[4])
            page = int(parts[5])
            await _safe_edit(
                query,
                "✅ Deletion cancelled. Your material is still saved.",
                reply_markup=library_material_keyboard(
                    material_id,
                    selected_filter=selected_filter,
                    page=page,
                ),
            )
            return

        await _show_library_page(
            update,
            notice="⚠️ That library action expired. Please choose again.",
        )
    except (TypeError, ValueError):
        await _show_library_page(
            update,
            notice="⚠️ That library action was invalid. Please choose again.",
        )
    except Exception:
        logger.exception("TeacherOS library callback failed")
        await _safe_edit(
            query,
            "❌ TeacherOS could not complete that library action.\n\n"
            "Send /library and try again.",
        )
