from __future__ import annotations

import logging

from telegram import InputFile, Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from database import get_user_material, record_export_event
from word_document import create_word_export

logger = logging.getLogger(__name__)


async def word_export_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Export one owned library material from either library or search results."""
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return

    data = query.data or ""
    parts = data.split("_")

    try:
        if len(parts) == 5 and parts[:2] == ["export", "library"]:
            material_id = int(parts[2])
        elif len(parts) == 4 and parts[:2] == ["export", "search"]:
            material_id = int(parts[2])
        else:
            raise ValueError("Invalid export callback")
    except (TypeError, ValueError):
        await query.answer("That export button is invalid. Open the material again.", show_alert=True)
        return

    await query.answer("Preparing Word document…")

    material = get_user_material(
        telegram_user_id=user.id,
        material_id=material_id,
    )
    if material is None:
        if query.message is not None:
            await query.message.reply_text(
                "⚠️ That material no longer exists or does not belong to your account."
            )
        return

    try:
        if update.effective_chat is not None:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action=ChatAction.UPLOAD_DOCUMENT,
            )

        stream, filename = create_word_export(material)
        if query.message is None:
            return

        await query.message.reply_document(
            document=InputFile(stream, filename=filename),
            filename=filename,
            caption=(
                f"✅ Word export ready\n"
                f"Library ID: #{material_id}\n"
                f"{material.get('title') or 'TeacherOS Material'}"
            ),
        )
        try:
            record_export_event(
                telegram_user=user,
                export_format="word",
                material_id=material_id,
            )
        except Exception:
            logger.exception("Word export succeeded but usage tracking failed")
    except Exception:
        logger.exception("Word export failed for material %s", material_id)
        if query.message is not None:
            await query.message.reply_text(
                "❌ TeacherOS could not create the Word file.\n\n"
                "Run: python -m pip install -r requirements.txt\n"
                "Then restart the bot and try again."
            )
