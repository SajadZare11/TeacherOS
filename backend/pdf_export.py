from __future__ import annotations

import logging

from telegram import InputFile, Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from database import get_user_material, record_export_event
from pdf_document import create_pdf_export

logger = logging.getLogger(__name__)


def _parse_pdf_callback(data: str) -> int:
    parts = data.split("_")
    if len(parts) == 5 and parts[:2] == ["pdf", "library"]:
        return int(parts[2])
    if len(parts) == 4 and parts[:2] == ["pdf", "search"]:
        return int(parts[2])
    raise ValueError("Invalid PDF export callback")


async def pdf_export_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Export one owned library material as PDF from Library or Search."""
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return

    try:
        material_id = _parse_pdf_callback(query.data or "")
    except (TypeError, ValueError):
        await query.answer("That PDF button is invalid. Open the material again.", show_alert=True)
        return

    await query.answer("Preparing PDF document…")

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

        stream, filename = create_pdf_export(material)
        if query.message is None:
            return

        await query.message.reply_document(
            document=InputFile(stream, filename=filename),
            filename=filename,
            caption=(
                "✅ PDF export ready\n"
                f"Library ID: #{material_id}\n"
                f"{material.get('title') or 'TeacherOS Material'}"
            ),
        )
        try:
            record_export_event(
                telegram_user=user,
                export_format="pdf",
                material_id=material_id,
            )
        except Exception:
            logger.exception("PDF export succeeded but usage tracking failed")
    except Exception:
        logger.exception("PDF export failed for material %s", material_id)
        if query.message is not None:
            await query.message.reply_text(
                "❌ TeacherOS could not create the PDF file.\n\n"
                "Run: python -m pip install -r requirements.txt\n"
                "Then restart the bot and try again."
            )
