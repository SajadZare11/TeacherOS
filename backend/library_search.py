from __future__ import annotations

import logging
import math
from typing import Any

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from database import (
    count_user_search_results,
    delete_user_material,
    get_user_material,
    register_telegram_user,
    search_user_materials,
)
from home_ui import teacheros_home_text
from keyboards import (
    search_delete_keyboard,
    search_material_keyboard,
    search_prompt_keyboard,
    search_results_keyboard,
    start_menu_keyboard,
)

logger = logging.getLogger(__name__)

SEARCH_PAGE_SIZE = 6
SEARCH_STATE_KEY = "library_search"

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


def _search_session(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    value = context.user_data.get(SEARCH_STATE_KEY)
    return value if isinstance(value, dict) else None


def _clean_query(value: object) -> str:
    return " ".join(str(value or "").split())


def _validate_query(value: object) -> str:
    query = _clean_query(value)
    if len(query) < 2:
        raise ValueError("Please type at least 2 characters.")
    if len(query) > 80:
        raise ValueError("Please keep your search to 80 characters or fewer.")
    return query


def _format_created_at(value: object) -> str:
    text = str(value or "").strip()
    return f"{text[:16]} UTC" if text else "Unknown"


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


def _format_search_page(
    *,
    query: str,
    total: int,
    page: int,
    total_pages: int,
    notice: str | None = None,
) -> str:
    lines = ["🔎 Search My Library", ""]
    if notice:
        lines.extend([notice, ""])

    lines.extend([f'Search: "{query}"', f"Matches: {total}"])
    if total:
        lines.extend(
            [
                f"Page: {page + 1} of {total_pages}",
                "",
                "Choose a matching material to open it.",
                "You can also type another phrase to search again.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "No matching materials were found.",
                "Try a shorter phrase, a topic, a CEFR level, or a word from the generated content.",
            ]
        )
    return "\n".join(lines)


async def _safe_edit(query: Any, text: str, *, reply_markup: Any = None) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _show_search_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data[SEARCH_STATE_KEY] = {"state": "waiting_query"}
    text = (
        "🔎 Search My Library\n\n"
        "Type a topic, title, CEFR level, resource type, or any word inside a saved material.\n\n"
        "Examples:\n"
        "• travel\n"
        "• present perfect\n"
        "• B1 speaking\n"
        "• environment worksheet"
    )
    keyboard = search_prompt_keyboard()

    if update.callback_query is not None:
        await _safe_edit(update.callback_query, text, reply_markup=keyboard)
    elif update.message is not None:
        await update.message.reply_text(text, reply_markup=keyboard)


async def _show_search_results(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    page: int = 0,
    notice: str | None = None,
) -> None:
    user = update.effective_user
    session = _search_session(context)
    if user is None or session is None:
        await _show_search_prompt(update, context)
        return

    query_text = _validate_query(session.get("query"))
    total = count_user_search_results(
        telegram_user_id=user.id,
        query=query_text,
    )
    total_pages = max(1, math.ceil(total / SEARCH_PAGE_SIZE))
    page = min(max(page, 0), total_pages - 1)
    materials = search_user_materials(
        telegram_user_id=user.id,
        query=query_text,
        limit=SEARCH_PAGE_SIZE,
        offset=page * SEARCH_PAGE_SIZE,
    )

    session.update({"state": "results", "query": query_text, "page": page})
    text = _format_search_page(
        query=query_text,
        total=total,
        page=page,
        total_pages=total_pages,
        notice=notice,
    )
    keyboard = search_results_keyboard(
        materials,
        page=page,
        total_pages=total_pages,
    )

    if update.callback_query is not None:
        await _safe_edit(update.callback_query, text, reply_markup=keyboard)
    elif update.message is not None:
        await update.message.reply_text(text, reply_markup=keyboard)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start search, or execute `/search words here` immediately."""
    context.user_data.clear()
    if update.effective_user is not None:
        try:
            register_telegram_user(update.effective_user)
        except Exception:
            logger.exception("Could not register user before library search")

    supplied_query = _clean_query(" ".join(getattr(context, "args", []) or []))
    if not supplied_query:
        await _show_search_prompt(update, context)
        return

    try:
        query_text = _validate_query(supplied_query)
        context.user_data[SEARCH_STATE_KEY] = {
            "state": "results",
            "query": query_text,
            "page": 0,
        }
        await _show_search_results(update, context)
    except ValueError as exc:
        context.user_data[SEARCH_STATE_KEY] = {"state": "waiting_query"}
        if update.message is not None:
            await update.message.reply_text(
                f"⚠️ {exc}\n\nType a different search phrase.",
                reply_markup=search_prompt_keyboard(),
            )
    except Exception:
        logger.exception("Could not search TeacherOS library")
        if update.effective_message is not None:
            await update.effective_message.reply_text(
                "❌ TeacherOS could not search your library.\n\n"
                "Run python backend/check_project.py, then try /search again."
            )


async def get_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process typed search text while a library-search session is active."""
    session = _search_session(context)
    if session is None or session.get("state") not in {"waiting_query", "results"}:
        return
    if update.message is None:
        return

    try:
        query_text = _validate_query(update.message.text)
    except ValueError as exc:
        await update.message.reply_text(
            f"⚠️ {exc}\n\nTry again.",
            reply_markup=search_prompt_keyboard(),
        )
        return

    session.update({"state": "results", "query": query_text, "page": 0})
    try:
        await _show_search_results(update, context)
    except Exception:
        logger.exception("Typed library search failed")
        await update.message.reply_text(
            "❌ TeacherOS could not search your library. Send /search and try again."
        )


async def _open_search_material(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    material_id: int,
    page: int,
) -> None:
    query = update.callback_query
    user = update.effective_user
    session = _search_session(context)
    if query is None or user is None or session is None:
        await _show_search_prompt(update, context)
        return

    material = get_user_material(
        telegram_user_id=user.id,
        material_id=material_id,
    )
    if material is None:
        await _show_search_results(
            update,
            context,
            page=page,
            notice="⚠️ That material no longer exists or does not belong to your account.",
        )
        return

    await _safe_edit(
        query,
        _format_material_summary(material)
        + "\n\n📄 The complete matching material appears below.",
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
            keyboard = search_material_keyboard(material_id, page=page)
        await query.message.reply_text(chunk, reply_markup=keyboard)


async def _request_search_delete(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    material_id: int,
    page: int,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or _search_session(context) is None:
        await _show_search_prompt(update, context)
        return

    material = get_user_material(
        telegram_user_id=user.id,
        material_id=material_id,
    )
    if material is None:
        await _show_search_results(
            update,
            context,
            page=page,
            notice="⚠️ That material no longer exists.",
        )
        return

    if query.message is not None:
        await query.message.reply_text(
            "🗑 Delete this matching material permanently?\n\n"
            f"#{material_id} — {material.get('title') or 'Untitled Material'}\n\n"
            "This cannot be undone.",
            reply_markup=search_delete_keyboard(material_id, page=page),
        )


async def _confirm_search_delete(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    material_id: int,
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
    await _show_search_results(update, context, page=page, notice=notice)


async def _show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    query = update.callback_query
    if query is not None:
        await _safe_edit(
            query,
            teacheros_home_text(),
            reply_markup=start_menu_keyboard(),
        )


async def search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    await query.answer()
    data = query.data or ""

    try:
        if data in {"search_start", "search_new"}:
            context.user_data.clear()
            await _show_search_prompt(update, context)
            return

        if data in {"search_cancel", "search_main"}:
            await _show_main_menu(update, context)
            return

        session = _search_session(context)
        if session is None or not session.get("query"):
            await _show_search_prompt(update, context)
            return

        parts = data.split("_")

        if len(parts) == 3 and parts[:2] == ["search", "page"]:
            await _show_search_results(update, context, page=int(parts[2]))
            return

        if len(parts) == 4 and parts[:2] == ["search", "item"]:
            await _open_search_material(
                update,
                context,
                material_id=int(parts[2]),
                page=int(parts[3]),
            )
            return

        if len(parts) == 4 and parts[:2] == ["search", "delete"]:
            await _request_search_delete(
                update,
                context,
                material_id=int(parts[2]),
                page=int(parts[3]),
            )
            return

        if len(parts) == 5 and parts[:3] == ["search", "delete", "yes"]:
            await _confirm_search_delete(
                update,
                context,
                material_id=int(parts[3]),
                page=int(parts[4]),
            )
            return

        if len(parts) == 5 and parts[:3] == ["search", "delete", "no"]:
            material_id = int(parts[3])
            page = int(parts[4])
            await _safe_edit(
                query,
                "✅ Deletion cancelled. Your material is still saved.",
                reply_markup=search_material_keyboard(material_id, page=page),
            )
            return

        await _show_search_results(
            update,
            context,
            notice="⚠️ That search action expired. Please choose again.",
        )
    except (TypeError, ValueError):
        await _show_search_results(
            update,
            context,
            notice="⚠️ That search action was invalid. Please choose again.",
        )
    except Exception:
        logger.exception("TeacherOS search callback failed")
        await _safe_edit(
            query,
            "❌ TeacherOS could not complete that search action.\n\n"
            "Send /search and try again.",
        )
