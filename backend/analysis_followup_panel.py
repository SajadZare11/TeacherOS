from __future__ import annotations

import logging
from typing import Any
from telegram import Update
from telegram.ext import ContextTypes

from evidence_keyboards import un_b36
from analysis_followup_keyboards import (
    ACTION_TYPE_CODES,
    analysis_followup_duration_keyboard,
    analysis_followup_types_keyboard,
    analysis_followup_view_keyboard,
)
from analysis_followup_service import (
    accept_followup_action,
    create_analysis_followup_action,
    get_analysis_followup_action,
)


logger = logging.getLogger(__name__)


async def handle_analysis_followup_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("v1|fa|"):
        return False

    await query.answer()
    parts = query.data.split("|")
    action = parts[2] if len(parts) > 2 else ""
    user = update.effective_user
    if not user:
        return False

    try:
        if action == "t":
            # v1|fa|t|{aid}|{bid}|{rev}
            aid = un_b36(parts[3])
            bid = un_b36(parts[4])
            rev = un_b36(parts[5]) if len(parts) > 5 else 1
            kb = analysis_followup_types_keyboard(aid, bid, rev)
            await query.edit_message_text(
                "⚡ *Create Teaching Follow-up Action*\n\n"
                "Connect this approved finding directly to a high-impact classroom resource:",
                reply_markup=kb,
                parse_mode="Markdown",
            )
            return True

        elif action == "d":
            # v1|fa|d|{aid}|{type_code}|{bid}|{rev}
            aid = un_b36(parts[3])
            tcode = parts[4]
            bid = un_b36(parts[5])
            rev = un_b36(parts[6]) if len(parts) > 6 else 1
            kb = analysis_followup_duration_keyboard(aid, tcode, bid, rev)
            action_name = ACTION_TYPE_CODES.get(tcode, "Follow-up Action")
            await query.edit_message_text(
                f"⏱ *Select Duration for {action_name}*:",
                reply_markup=kb,
                parse_mode="Markdown",
            )
            return True

        elif action == "g":
            # v1|fa|g|{aid}|{type_code}|{dur}|{bid}|{rev}
            aid = un_b36(parts[3])
            tcode = parts[4]
            dur = int(parts[5])
            bid = un_b36(parts[6])
            rev = un_b36(parts[7]) if len(parts) > 7 else 1
            action_type = ACTION_TYPE_CODES.get(tcode, "reteach_lesson")

            followup = create_analysis_followup_action(
                telegram_user=user,
                analysis_id=aid,
                action_type=action_type,
                duration_minutes=dur,
                save_to_library=True,
            )
            fid = int(followup["id"])
            mid = followup.get("material_id")
            kb = analysis_followup_view_keyboard(fid, aid, bid, mid, rev + 1, accepted=False)
            await query.edit_message_text(
                followup.get("content_markdown", "")[:4000],
                reply_markup=kb,
            )
            return True

        elif action == "acc":
            # v1|fa|acc|{fid}|{aid}|{bid}|{rev}
            fid = un_b36(parts[3])
            aid = un_b36(parts[4])
            bid = un_b36(parts[5])
            rev = un_b36(parts[6]) if len(parts) > 6 else 1
            accepted = accept_followup_action(telegram_user=user, followup_id=fid)
            if not accepted:
                await query.edit_message_text("Could not accept follow-up action.")
                return True
            mid = accepted.get("material_id")
            kb = analysis_followup_view_keyboard(fid, aid, bid, mid, rev + 1, accepted=True)
            await query.edit_message_text(
                "✅ *Teaching Action Accepted & Added to Class Plan!*\n\n"
                + accepted.get("content_markdown", "")[:3800],
                reply_markup=kb,
                parse_mode="Markdown",
            )
            return True

    except Exception as exc:
        logger.exception("Error handling analysis followup callback: %s", exc)
        await query.edit_message_text("⚠️ This teaching action is unavailable. Please try again.")
        return True

    return False
