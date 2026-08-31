from __future__ import annotations

import logging
import re
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from differentiation_keyboards import (
    _CODE_TO_ADAP,
    adaptation_view_keyboard,
    adaptations_menu_keyboard,
    differentiation_view_keyboard,
)
from differentiation_service import (
    generate_one_tap_adaptation,
    generate_tiered_differentiation,
    get_material_adaptation,
    get_tiered_differentiation,
)


logger = logging.getLogger(__name__)

_DF_PATTERN = re.compile(
    r"^v1\|df\|(?P<action>gen|tab)\|(?P<id_b36>[0-9a-z]+)(?:\|(?P<tab>sup|cor|cha|gui))?$"
)
_AD_PATTERN = re.compile(
    r"^v1\|ad\|(?P<action>menu|gen|view)\|(?P<id_b36>[0-9a-z]+)(?:\|(?P<code>sho|lon|fas|eas|har|not|lar|com|exa))?$"
)


def _unbase36(text: str) -> int:
    return int(text, 36)


async def handle_differentiation_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle v1|df|... callback queries."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    match = _DF_PATTERN.match(query.data)
    if not match:
        return

    await query.answer()
    action = match.group("action")
    raw_id = _unbase36(match.group("id_b36"))
    tab = match.group("tab") or "sup"
    user = update.effective_user
    if user is None:
        return

    if action == "gen":
        # raw_id is source_material_id
        diff = generate_tiered_differentiation(
            telegram_user=user,
            source_material_id=raw_id,
        )
        diff_id = diff["id"]
        source_id = raw_id
    else:
        # action == 'tab', raw_id is differentiation_id
        diff = get_tiered_differentiation(
            telegram_user=user,
            differentiation_id=raw_id,
        )
        if not diff:
            await query.edit_message_text("⚠️ Differentiation record not found.")
            return
        diff_id = raw_id
        source_id = diff["source_material_id"]

    # Render tab content
    obj = diff["objective"]
    if tab == "sup":
        body = diff["support_route_markdown"]
    elif tab == "cor":
        body = diff["core_route_markdown"]
    elif tab == "cha":
        body = diff["challenge_route_markdown"]
    else:
        body = diff["delivery_guidance_markdown"]

    text = (
        f"🎯 **3-Tier Differentiation**\n"
        f"📌 **Shared Objective:** {obj}\n\n"
        f"{body}"
    )

    kb = differentiation_view_keyboard(diff_id, source_id, active_tab=tab)
    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")


async def handle_adaptation_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle v1|ad|... callback queries."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    match = _AD_PATTERN.match(query.data)
    if not match:
        return

    await query.answer()
    action = match.group("action")
    raw_id = _unbase36(match.group("id_b36"))
    code = match.group("code")
    user = update.effective_user
    if user is None:
        return

    if action == "menu":
        # raw_id is source_material_id
        kb = adaptations_menu_keyboard(raw_id)
        text = (
            "⚡ **One-Tap Classroom Adaptations**\n\n"
            "Select an emergency adaptation below. This will create a customized version "
            "while keeping your original material completely intact."
        )
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

    elif action == "gen":
        # raw_id is source_material_id, code is adaptation code
        atype = _CODE_TO_ADAP.get(code or "sho", "shorter")
        adap = generate_one_tap_adaptation(
            telegram_user=user,
            source_material_id=raw_id,
            adaptation_type=atype,
        )
        text = (
            f"⚡ **{adap['title']}**\n"
            f"💡 **What Changed:** {adap['changes_summary']}\n\n"
            f"{adap['adapted_content_markdown']}"
        )
        kb = adaptation_view_keyboard(adap["id"], raw_id)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

    elif action == "view":
        # raw_id is adaptation_id
        adap = get_material_adaptation(telegram_user=user, adaptation_id=raw_id)
        if not adap:
            await query.edit_message_text("⚠️ Adaptation record not found.")
            return
        text = (
            f"⚡ **{adap['title']}**\n"
            f"💡 **What Changed:** {adap['changes_summary']}\n\n"
            f"{adap['adapted_content_markdown']}"
        )
        kb = adaptation_view_keyboard(adap["id"], adap["source_material_id"])
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
