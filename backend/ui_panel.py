"""TeacherOS UI Panel (Day 24).

Handles Telegram callbacks for language switching, 3-step onboarding walkthrough,
pinned favorites management, and class-aware material search.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from telegram import Update
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes

from class_service import get_class
from database import register_telegram_user
from string_catalog import tr
from ui_keyboards import (
    _base36,
    language_switcher_keyboard,
    onboarding_walkthrough_keyboard,
    pinned_materials_keyboard,
)
from ui_service import (
    complete_onboarding,
    get_or_create_ui_preferences,
    is_material_pinned,
    list_pinned_materials,
    pin_material_to_class,
    set_user_language,
    unpin_material_from_class,
)

logger = logging.getLogger(__name__)

_CALLBACK_PATTERN = re.compile(
    r"^v1\|ui\|(?P<action>[a-z0-9_]{1,10})\|"
    r"(?P<object_id>[0-9a-z_]{1,20})\|(?P<revision>[0-9a-z]{1,6})$"
)


def _decode_b36(val: str) -> int:
    try:
        return int(val, 36)
    except (ValueError, TypeError):
        return 0


async def _answer_query(query: Any, text: str | None = None) -> None:
    if query is None:
        return
    try:
        await query.answer(text=text)
    except (TimedOut, NetworkError, BadRequest):
        pass


async def _safe_edit(query: Any, text: str, *, reply_markup: Any) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


# ---------------------------------------------------------------------------
# Callback Query Dispatcher
# ---------------------------------------------------------------------------

async def handle_ui_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Dispatch UI polish callbacks."""
    query = update.callback_query
    if query is None or not query.data:
        return

    match = _CALLBACK_PATTERN.match(query.data)
    if not match:
        return

    action = match.group("action")
    raw_object = match.group("object_id")
    raw_rev = match.group("revision")
    revision = _decode_b36(raw_rev)

    tg_user = update.effective_user
    if tg_user is None or not isinstance(getattr(tg_user, "id", None), int):
        return

    tg_user_id = tg_user.id
    user_id = register_telegram_user(tg_user)
    prefs = get_or_create_ui_preferences(user_id)
    lang = prefs.get("language_code", "en")

    # -----------------------------------------------------------------------
    # Action: Language Selection (lang)
    # -----------------------------------------------------------------------
    if action == "lang":
        await _answer_query(query)
        text = tr("lang_choose", lang)
        await _safe_edit(
            query,
            text,
            reply_markup=language_switcher_keyboard(revision=revision, current_lang=lang),
        )
        return

    if action in {"slen", "slfa"}:
        new_lang = "en" if action == "slen" else "fa"
        set_user_language(user_id, new_lang)
        await _answer_query(query, tr("lang_switched", new_lang))
        text = tr("lang_choose", new_lang) + "\n\n" + tr("lang_switched", new_lang)
        await _safe_edit(
            query,
            text,
            reply_markup=language_switcher_keyboard(revision=revision, current_lang=new_lang),
        )
        return

    # -----------------------------------------------------------------------
    # Actions: Onboarding Walkthrough (onb1, onb2, onb3, onbdon)
    # -----------------------------------------------------------------------
    if action in {"onb1", "onb2", "onb3"}:
        step = int(action[-1])
        await _answer_query(query)
        step_titles = {
            1: tr("onboarding_step1_title", lang),
            2: tr("onboarding_step2_title", lang),
            3: tr("onboarding_step3_title", lang),
        }
        step_bodies = {
            1: tr("onboarding_step1_body", lang),
            2: tr("onboarding_step2_body", lang),
            3: tr("onboarding_step3_body", lang),
        }

        text = (
            f"{tr('onboarding_welcome_title', lang)}\n\n"
            f"<b>{step_titles[step]}</b>\n\n"
            f"{step_bodies[step]}"
        )
        await _safe_edit(
            query,
            text,
            reply_markup=onboarding_walkthrough_keyboard(step=step, revision=revision, lang=lang),
        )
        return

    if action == "onbdon":
        complete_onboarding(user_id)
        await _answer_query(query, "Welcome to TeacherOS!")
        text = (
            f"🎉 <b>{tr('header_main_menu', lang)}</b>\n\n"
            "You are ready to begin. Create your first class or access tools from the menu below:"
        )
        from keyboards import start_menu_keyboard
        await _safe_edit(
            query,
            text,
            reply_markup=start_menu_keyboard(),
        )
        return

    # -----------------------------------------------------------------------
    # Actions: Pinned / Favorite Materials (favs, pin, unpin)
    # -----------------------------------------------------------------------
    if action == "favs":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, tr("state_error_not_found", lang))
            return

        await _answer_query(query)
        pinned = list_pinned_materials(user_id=user_id, class_id=class_id)
        header = tr("header_active_class", lang, class_name=owned["display_name"], level=owned["level"])

        if not pinned:
            body = tr("state_empty_pinned", lang)
        else:
            body = f"⭐ <b>{tr('nav_favorites', lang)} ({len(pinned)})</b>\nQuick-access materials pinned for this class:"

        await _safe_edit(
            query,
            f"{header}\n\n{body}",
            reply_markup=pinned_materials_keyboard(
                class_id=class_id,
                revision=revision,
                pinned_items=pinned,
                lang=lang,
            ),
        )
        return

    if action in {"pin", "unpin"}:
        material_id = _decode_b36(raw_object)
        # Check active class from prefs or fetch
        last_class_id = prefs.get("last_active_class_id")
        if not last_class_id:
            await _answer_query(query, tr("state_error_not_found", lang))
            return

        if action == "pin":
            success = pin_material_to_class(user_id=user_id, class_id=last_class_id, material_id=material_id)
            msg = tr("state_success_pinned", lang) if success else tr("state_error_generic", lang)
        else:
            success = unpin_material_from_class(user_id=user_id, class_id=last_class_id, material_id=material_id)
            msg = tr("state_success_unpinned", lang) if success else tr("state_error_generic", lang)

        await _answer_query(query, msg)
        return
