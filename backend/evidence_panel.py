from __future__ import annotations

import logging
from typing import Any
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import database
from feature_flags import feature_enabled
from keyboards import class_recovery_keyboard
from evidence_keyboards import (
    EVIDENCE_TYPE_CODES,
    RETENTION_CODES,
    evidence_batch_details_keyboard,
    evidence_delete_confirm_keyboard,
    evidence_inbox_keyboard,
    evidence_item_view_keyboard,
    evidence_retention_keyboard,
    evidence_submission_method_keyboard,
    evidence_type_keyboard,
)
from evidence_service import (
    EVIDENCE_TYPE_LABELS,
    RETENTION_LABELS,
    delete_evidence_batch,
    delete_evidence_item,
    get_evidence_batch,
    list_evidence_batches,
    submit_evidence_batch,
    update_evidence_item_label,
    validate_file_submission,
)


logger = logging.getLogger(__name__)


def _decode_b36(val: str) -> int:
    return int(val, 36)


async def _safe_edit(query: Any, text: str, markup: Any) -> None:
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def handle_evidence_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    parts = query.data.split("|")
    if len(parts) < 4 or parts[0] != "v1" or parts[1] != "ev":
        return

    action = parts[2]
    user = query.from_user
    if user is None:
        return

    if not feature_enabled("evidence"):
        await _safe_edit(
            query,
            "🔒 Evidence Inbox is not enabled in this environment.",
            class_recovery_keyboard(),
        )
        return

    try:
        if action == "inbox":
            class_id = _decode_b36(parts[3])
            revision = _decode_b36(parts[4])
            batches = list_evidence_batches(telegram_user_id=user.id, class_id=class_id)
            with database.database_connection() as conn:
                class_row = conn.execute(
                    "SELECT display_name FROM classes WHERE id = ? AND user_id = (SELECT id FROM users WHERE telegram_user_id = ?)",
                    (class_id, user.id),
                ).fetchone()
            cname = str(class_row["display_name"]) if class_row else "Class"

            text = (
                f"📥 Evidence Inbox · {cname}\n\n"
                "Submit and manage anonymized student work (writing, speaking notes, quizzes).\n\n"
                "🔒 Privacy Safeguards:\n"
                "• Anonymous labels only (Student A, Student 1)\n"
                "• Deletable at any time by teacher\n"
                "• Automated privacy retention (30 days default)"
            )
            await _safe_edit(query, text, evidence_inbox_keyboard(class_id, revision, batches))
            return

        if action == "new":
            class_id = _decode_b36(parts[3])
            revision = _decode_b36(parts[4])
            text = (
                "➕ Submit Student Evidence\n\n"
                "Step 1: Choose the kind of evidence you are submitting:"
            )
            await _safe_edit(query, text, evidence_type_keyboard(class_id, revision))
            return

        if action == "type":
            class_id = _decode_b36(parts[3])
            type_code = parts[4]
            revision = _decode_b36(parts[5])
            etype = EVIDENCE_TYPE_CODES.get(type_code, "general_work")
            text = (
                f"➕ Evidence Type: {EVIDENCE_TYPE_LABELS.get(etype, etype)}\n\n"
                "Step 2: Choose your privacy retention policy:"
            )
            await _safe_edit(query, text, evidence_retention_keyboard(class_id, type_code, revision))
            return

        if action == "ret":
            class_id = _decode_b36(parts[3])
            type_code = parts[4]
            ret_code = parts[5]
            revision = _decode_b36(parts[6])
            etype = EVIDENCE_TYPE_CODES.get(type_code, "general_work")
            ret_policy = RETENTION_CODES.get(ret_code, "30_days")
            text = (
                f"➕ Ready to Submit Evidence\n\n"
                f"• Type: {EVIDENCE_TYPE_LABELS.get(etype, etype)}\n"
                f"• Retention: {RETENTION_LABELS.get(ret_policy, ret_policy)}\n"
                f"• Privacy: Anonymous labels will be applied\n\n"
                "Step 3: Choose submission method:"
            )
            await _safe_edit(
                query, text, evidence_submission_method_keyboard(class_id, type_code, ret_code, revision)
            )
            return

        if action in {"subtxt", "subfil"}:
            class_id = _decode_b36(parts[3])
            type_code = parts[4]
            ret_code = parts[5]
            revision = _decode_b36(parts[6])
            etype = EVIDENCE_TYPE_CODES.get(type_code, "general_work")
            ret_policy = RETENTION_CODES.get(ret_code, "30_days")

            context.user_data["evidence_submission"] = {
                "class_id": class_id,
                "type_code": type_code,
                "evidence_type": etype,
                "retention_policy": ret_policy,
                "revision": revision,
                "mode": "text" if action == "subtxt" else "file",
            }

            if action == "subtxt":
                msg = (
                    "📝 Paste Student Evidence Text\n\n"
                    "Type or paste student responses into the chat.\n\n"
                    "Tips for multiple students:\n"
                    "• Separate students with `---` or `Student 1:`, `Student 2:`\n"
                    "• Never include real student last names, emails, or phone numbers."
                )
            else:
                msg = (
                    "📎 Upload Evidence File (.txt or .docx)\n\n"
                    "Send a .txt or .docx document in this chat (up to 2 MB, max 50 student items).\n\n"
                    "Note: PDF and audio are deferred until consent and extraction verification."
                )
            await _safe_edit(query, msg, evidence_inbox_keyboard(class_id, revision, []))
            return

        if action == "batch":
            batch_id = _decode_b36(parts[3])
            revision = _decode_b36(parts[4])
            batch = get_evidence_batch(telegram_user_id=user.id, batch_id=batch_id)
            if batch is None:
                await _safe_edit(query, "⚠️ Evidence batch not found or deleted.", class_recovery_keyboard())
                return

            items = batch.get("items", [])
            etype = EVIDENCE_TYPE_LABELS.get(batch.get("evidence_type", ""), "Evidence")
            text = (
                f"📦 Evidence Batch #{batch_id} · {batch.get('class_name', 'Class')}\n\n"
                f"• Type: {etype}\n"
                f"• Source: {batch.get('source_format', 'text').replace('_', ' ').title()}\n"
                f"• Items: {len(items)} students ({batch.get('total_words', 0)} words)\n"
                f"• Retention: {RETENTION_LABELS.get(batch.get('retention_policy', ''), '30 Days')}\n"
                f"• Submitted: {str(batch.get('created_at', ''))[:16]} UTC\n\n"
                "Select a student below to inspect or edit labels:"
            )
            await _safe_edit(
                query, text, evidence_batch_details_keyboard(batch_id, int(batch["class_id"]), revision, items)
            )
            return

        if action == "item":
            item_id = _decode_b36(parts[3])
            revision = _decode_b36(parts[4])
            with database.database_connection() as conn:
                item_row = conn.execute(
                    """
                    SELECT i.*, b.class_id FROM evidence_items AS i
                    JOIN evidence_batches AS b ON b.id = i.batch_id
                    WHERE i.id = ? AND i.user_id = (SELECT id FROM users WHERE telegram_user_id = ?) AND i.status = 'active'
                    """,
                    (item_id, user.id),
                ).fetchone()
            if item_row is None:
                await _safe_edit(query, "⚠️ Evidence item not found or deleted.", class_recovery_keyboard())
                return

            snippet = str(item_row["content"])
            if len(snippet) > 800:
                snippet = snippet[:800] + "…"

            text = (
                f"👤 {item_row['student_label']}\n"
                f"Length: {item_row['word_count']} words ({item_row['char_count']} chars)\n\n"
                f"Excerpt:\n\"{snippet}\""
            )
            await _safe_edit(
                query, text, evidence_item_view_keyboard(item_id, int(item_row["batch_id"]), revision)
            )
            return

        if action == "edlbl":
            item_id = _decode_b36(parts[3])
            revision = _decode_b36(parts[4])
            context.user_data["evidence_edit_label"] = {
                "item_id": item_id,
                "revision": revision,
            }
            await _safe_edit(
                query,
                "✏ Edit Student Label\n\nType an anonymous label (e.g. `Student 1`, `Group A`, `Pair 2`):",
                class_recovery_keyboard(),
            )
            return

        if action == "delitm":
            item_id = _decode_b36(parts[3])
            revision = _decode_b36(parts[4])
            with database.database_connection() as conn:
                item_row = conn.execute(
                    "SELECT batch_id FROM evidence_items WHERE id = ? AND user_id = (SELECT id FROM users WHERE telegram_user_id = ?)",
                    (item_id, user.id),
                ).fetchone()
            batch_id = int(item_row["batch_id"]) if item_row else 0
            success = delete_evidence_item(telegram_user_id=user.id, item_id=item_id)
            if success and batch_id:
                batch = get_evidence_batch(telegram_user_id=user.id, batch_id=batch_id)
                if batch:
                    await _safe_edit(
                        query,
                        "✅ Item deleted successfully.",
                        evidence_batch_details_keyboard(
                            batch_id, int(batch["class_id"]), revision, batch.get("items", [])
                        ),
                    )
                    return
            await _safe_edit(query, "Item deleted or removed.", class_recovery_keyboard())
            return

        if action == "delask":
            batch_id = _decode_b36(parts[3])
            revision = _decode_b36(parts[4])
            batch = get_evidence_batch(telegram_user_id=user.id, batch_id=batch_id)
            if batch is None:
                await _safe_edit(query, "⚠️ Batch not found.", class_recovery_keyboard())
                return
            text = (
                f"🗑 Delete Batch #{batch_id}?\n\n"
                f"This will delete all {len(batch.get('items', []))} student evidence items in this batch.\n"
                "This action cannot be undone."
            )
            await _safe_edit(
                query, text, evidence_delete_confirm_keyboard(batch_id, int(batch["class_id"]), revision)
            )
            return

        if action == "delyes":
            batch_id = _decode_b36(parts[3])
            revision = _decode_b36(parts[4])
            batch = get_evidence_batch(telegram_user_id=user.id, batch_id=batch_id)
            class_id = int(batch["class_id"]) if batch else 0
            success = delete_evidence_batch(telegram_user_id=user.id, batch_id=batch_id)
            if success and class_id:
                batches = list_evidence_batches(telegram_user_id=user.id, class_id=class_id)
                await _safe_edit(
                    query,
                    "✅ Evidence batch and all student items were permanently deleted.",
                    evidence_inbox_keyboard(class_id, revision, batches),
                )
                return
            await _safe_edit(query, "Batch deleted.", class_recovery_keyboard())
            return

    except Exception:
        logger.exception("Evidence panel callback error")
        await _safe_edit(query, "⚠️ An error occurred in Evidence Inbox.", class_recovery_keyboard())


async def handle_evidence_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.effective_user is None:
        return

    # Check for text edit label state
    edit_label = context.user_data.get("evidence_edit_label")
    if edit_label and update.message.text:
        item_id = int(edit_label["item_id"])
        revision = int(edit_label["revision"])
        new_label = update.message.text.strip()
        try:
            res = update_evidence_item_label(
                telegram_user_id=update.effective_user.id,
                item_id=item_id,
                new_label=new_label,
            )
            context.user_data.pop("evidence_edit_label", None)
            if res:
                await update.message.reply_text(
                    f"✅ Label updated to '{res['student_label']}'.",
                    reply_markup=evidence_item_view_keyboard(item_id, int(res["batch_id"]), revision),
                )
                return
        except ValueError as exc:
            await update.message.reply_text(f"⚠️ {exc}\n\nPlease enter a valid anonymous label:")
            return

    # Check for evidence submission state
    sub = context.user_data.get("evidence_submission")
    if not sub:
        return

    class_id = int(sub["class_id"])
    evidence_type = str(sub["evidence_type"])
    retention_policy = str(sub["retention_policy"])
    revision = int(sub["revision"])

    try:
        if update.message.document is not None:
            doc = update.message.document
            file_name = doc.file_name or "uploaded_file"
            tg_file = await doc.get_file()
            file_bytes = await tg_file.download_as_bytearray()

            batch = submit_evidence_batch(
                telegram_user=update.effective_user,
                class_id=class_id,
                evidence_type=evidence_type,
                file_name=file_name,
                file_bytes=bytes(file_bytes),
                retention_policy=retention_policy,
                privacy_confirmed=True,
            )
            context.user_data.pop("evidence_submission", None)
            items = batch.get("items", [])
            await update.message.reply_text(
                f"✅ Evidence file processed: #{batch['id']} ({len(items)} student items extracted).\n\n"
                f"Format: {file_name} · Total Words: {batch.get('total_words', 0)}",
                reply_markup=evidence_batch_details_keyboard(int(batch["id"]), class_id, revision, items),
            )
            return

        if update.message.text:
            raw_text = update.message.text
            batch = submit_evidence_batch(
                telegram_user=update.effective_user,
                class_id=class_id,
                evidence_type=evidence_type,
                raw_text=raw_text,
                retention_policy=retention_policy,
                privacy_confirmed=True,
            )
            context.user_data.pop("evidence_submission", None)
            items = batch.get("items", [])
            await update.message.reply_text(
                f"✅ Evidence text saved: #{batch['id']} ({len(items)} student items extracted).\n\n"
                f"Total Words: {batch.get('total_words', 0)}",
                reply_markup=evidence_batch_details_keyboard(int(batch["id"]), class_id, revision, items),
            )
            return

    except ValueError as exc:
        await update.message.reply_text(
            f"⚠️ {exc}\n\nPlease try again or cancel.",
            reply_markup=class_recovery_keyboard(),
        )
    except Exception:
        logger.exception("Evidence message handler error")
        await update.message.reply_text(
            "⚠️ An error occurred while processing the evidence.",
            reply_markup=class_recovery_keyboard(),
        )
