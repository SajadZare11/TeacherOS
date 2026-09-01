from __future__ import annotations

import logging
from typing import Any
from telegram import Update
from telegram.ext import ContextTypes

from evidence_keyboards import un_b36
from writing_feedback_keyboards import (
    MODE_CODES,
    writing_feedback_export_keyboard,
    writing_feedback_mode_keyboard,
    writing_feedback_view_keyboard,
)
from writing_feedback_service import (
    approve_writing_feedback,
    export_writing_feedback_pdf,
    export_writing_feedback_word,
    generate_writing_feedback,
    get_writing_feedback,
    update_writing_feedback_comments,
)


logger = logging.getLogger(__name__)


async def handle_writing_feedback_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("v1|wf|"):
        return False

    await query.answer()
    parts = query.data.split("|")
    action = parts[2] if len(parts) > 2 else ""
    user = update.effective_user
    if not user:
        return False

    try:
        if action == "start":
            # v1|wf|start|{class_id_or_0}|{rev}
            cid_val = un_b36(parts[3]) if len(parts) > 3 and parts[3] != "0" else None
            revision = un_b36(parts[4]) if len(parts) > 4 else 1
            kb = writing_feedback_mode_keyboard(cid_val, revision)
            await query.edit_message_text(
                "✍️ *Writing Feedback Copilot*\n\n"
                "Select the depth and style of feedback for student writing:",
                reply_markup=kb,
                parse_mode="Markdown",
            )
            return True

        elif action == "m":
            # v1|wf|m|{cid}|{mode_code}|{rev}
            cid_val = un_b36(parts[3]) if len(parts) > 3 and parts[3] != "0" else None
            mode_code = parts[4]
            mode_name = MODE_CODES.get(mode_code, "balanced")
            if context.user_data is not None:
                context.user_data["wf_mode"] = mode_name
                context.user_data["wf_class_id"] = cid_val
                context.user_data["awaiting_student_writing"] = True

            await query.edit_message_text(
                f"✍️ *Writing Feedback ({mode_name.capitalize()} Mode)*\n\n"
                "Please send the student's text message or paste their writing below.\n\n"
                "_Tip: You can include an optional task prompt in quotes at the start._",
                parse_mode="Markdown",
            )
            return True

        elif action == "v":
            # v1|wf|v|{fid}|{cid}|{rev}
            fid = un_b36(parts[3])
            cid_val = un_b36(parts[4]) if len(parts) > 4 and parts[4] != "0" else None
            revision = un_b36(parts[5]) if len(parts) > 5 else 1
            feedback = get_writing_feedback(telegram_user=user, feedback_id=fid)
            if not feedback:
                await query.edit_message_text("Feedback record not found.")
                return True
            kb = writing_feedback_view_keyboard(fid, cid_val, revision + 1, approved=bool(feedback.get("approved", 0)))
            await query.edit_message_text(feedback.get("student_copy_text", ""), reply_markup=kb)
            return True

        elif action == "appr":
            # v1|wf|appr|{fid}|{cid}|{rev}
            fid = un_b36(parts[3])
            cid_val = un_b36(parts[4]) if len(parts) > 4 and parts[4] != "0" else None
            revision = un_b36(parts[5]) if len(parts) > 5 else 1
            feedback = approve_writing_feedback(telegram_user=user, feedback_id=fid)
            if not feedback:
                await query.edit_message_text("Could not approve feedback record.")
                return True
            kb = writing_feedback_view_keyboard(fid, cid_val, revision + 1, approved=True)
            await query.edit_message_text(
                "✅ *Feedback Approved!* Ready for student sharing or export.\n\n"
                + feedback.get("student_copy_text", ""),
                reply_markup=kb,
                parse_mode="Markdown",
            )
            return True

        elif action == "edt":
            # v1|wf|edt|{fid}|{cid}|{rev}
            fid = un_b36(parts[3])
            if context.user_data is not None:
                context.user_data["wf_editing_feedback_id"] = fid
            await query.edit_message_text(
                "✏️ Please reply with your customized teacher comments for this student."
            )
            return True

        elif action == "exp":
            # v1|wf|exp|{fid}|{cid}|{rev}
            fid = un_b36(parts[3])
            feedback = get_writing_feedback(telegram_user=user, feedback_id=fid)
            if not feedback:
                await query.edit_message_text("Feedback record not found.")
                return True
            if not bool(feedback.get("approved", 0)):
                await query.edit_message_text(
                    "⚠️ Please approve this feedback before exporting or sharing copies."
                )
                return True
            cid_val = un_b36(parts[4]) if len(parts) > 4 and parts[4] != "0" else None
            revision = un_b36(parts[5]) if len(parts) > 5 else 1
            kb = writing_feedback_export_keyboard(fid, cid_val, revision)
            await query.edit_message_text("📤 Select export document format:", reply_markup=kb)
            return True

        elif action in ("expw", "expp"):
            # v1|wf|expw|{fid}|{copy_type: s/t}|{cid}|{rev}
            fid = un_b36(parts[3])
            copy_type = "teacher" if len(parts) > 4 and parts[4] == "t" else "student"
            feedback = get_writing_feedback(telegram_user=user, feedback_id=fid)
            if not feedback:
                await query.edit_message_text("Feedback record not found.")
                return True
            if not bool(feedback.get("approved", 0)):
                await query.answer("Approve feedback before exporting.", show_alert=True)
                return True

            if action == "expw":
                filename, data = export_writing_feedback_word(feedback=feedback, copy_type=copy_type)
            else:
                filename, data = export_writing_feedback_pdf(feedback=feedback, copy_type=copy_type)

            if update.effective_chat:
                await update.effective_chat.send_document(
                    document=data,
                    filename=filename,
                    caption=f"📝 {filename}",
                )
            return True

    except Exception as exc:
        logger.exception("Error handling writing feedback callback: %s", exc)
        # Do not echo database/provider details (or any user-controlled text)
        # into Telegram. Keep the callback recoverable with a safe message.
        await query.edit_message_text("⚠️ This feedback action is unavailable. Please try again.")
        return True

    return False


async def handle_writing_feedback_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    if context.user_data is None:
        return False

    # 1. Editing comments
    if "wf_editing_feedback_id" in context.user_data:
        fid = context.user_data.pop("wf_editing_feedback_id")
        text = update.message.text if update.message else ""
        user = update.effective_user
        if text and user:
            updated = update_writing_feedback_comments(
                telegram_user=user,
                feedback_id=fid,
                new_comments=text,
            )
            if updated and update.effective_chat:
                kb = writing_feedback_view_keyboard(
                    fid,
                    updated.get("class_id"),
                    1,
                    approved=bool(updated.get("approved", 0)),
                )
                await update.effective_chat.send_message(
                    "✅ Comments updated!\n\n" + updated.get("student_copy_text", ""),
                    reply_markup=kb,
                )
                return True

    # 2. Generating new feedback
    if context.user_data.get("awaiting_student_writing"):
        context.user_data.pop("awaiting_student_writing", None)
        mode = context.user_data.pop("wf_mode", "balanced")
        cid_val = context.user_data.pop("wf_class_id", None)
        text = update.message.text if update.message else ""
        user = update.effective_user
        if text and user:
            feedback = generate_writing_feedback(
                telegram_user=user,
                student_text=text,
                feedback_mode=mode,
                class_id=cid_val,
            )
            if feedback and update.effective_chat:
                kb = writing_feedback_view_keyboard(
                    int(feedback["id"]),
                    cid_val,
                    1,
                    approved=False,
                )
                await update.effective_chat.send_message(
                    feedback.get("student_copy_text", ""),
                    reply_markup=kb,
                )
                return True

    return False
