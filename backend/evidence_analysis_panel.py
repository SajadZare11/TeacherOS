from __future__ import annotations

import logging
from typing import Any
from telegram import Update
from telegram.ext import ContextTypes

from evidence_analysis_keyboards import (
    evidence_analysis_confirm_reject_keyboard,
    evidence_analysis_keyboard,
)
from evidence_analysis_service import (
    analyze_evidence_batch,
    approve_evidence_analysis,
    get_evidence_analysis,
    reject_evidence_analysis,
    update_analysis_summary,
)
from evidence_keyboards import un_b36


logger = logging.getLogger(__name__)


def render_evidence_analysis_text(analysis: dict[str, Any]) -> str:
    findings = analysis.get("findings", {})
    response_count = int(analysis.get("response_count", 0))
    uncertainty = str(analysis.get("uncertainty", "medium")).upper()
    uncertainty_reason = analysis.get("uncertainty_reason", "")
    notice = analysis.get("limited_evidence_notice")
    approved = bool(analysis.get("approved", 0))
    status = str(analysis.get("status", "draft")).upper()

    lines: list[str] = [
        f"🔬 Evidence Analysis — {analysis.get('class_name', 'Class')}",
        f"Status: {status} {'(Approved)' if approved else '(Draft)'}",
        f"📊 Analyzed Sample: {response_count} student response(s)",
        f"🏷️ Uncertainty: {uncertainty}",
        f"Rationale: {uncertainty_reason}",
    ]

    if notice:
        lines.append("")
        lines.append(notice)

    # Strengths
    strengths = findings.get("strengths", [])
    if strengths:
        lines.append("")
        lines.append("💪 Key Strengths:")
        for s in strengths:
            labels_str = ", ".join(s.get("evidence_labels", []))
            lines.append(f"• {s['area']} [{labels_str}]:")
            lines.append(f"  {s['description']}")

    # Common Errors & Growth Areas
    errors = findings.get("common_errors", [])
    if errors:
        lines.append("")
        lines.append("⚠️ Areas for Growth (Error Patterns):")
        for e in errors:
            band = str(e.get("frequency_band", "some")).capitalize()
            labels_str = ", ".join(e.get("evidence_labels", []))
            lines.append(f"• {e['error_name']} (Frequency: {band}) [{labels_str}]:")
            lines.append(f"  {e['description']}")
            for ex in e.get("examples", [])[:1]:
                lines.append(f'  Example: "{ex}"')

    # Likely Misconceptions
    misconceptions = findings.get("likely_misconceptions", [])
    if misconceptions:
        lines.append("")
        lines.append("💡 Pedagogical Hypotheses:")
        for m in misconceptions:
            lines.append(f"• {m['hypothesis']}")

    # Next Priorities
    priorities = findings.get("next_priorities", [])
    if priorities:
        lines.append("")
        lines.append("🎯 Recommended Next Priorities:")
        for p in priorities:
            lines.append(f"{p['priority']}. {p['title']}")
            lines.append(f"   Action: {p['action']}")

    # Temporary Groups
    groups = findings.get("temporary_groups", [])
    if groups:
        lines.append("")
        lines.append("👥 Optional Temporary Groups (Fluid):")
        for g in groups:
            students = ", ".join(g.get("student_labels", []))
            lines.append(f"• {g['group_name']} ({students}): {g['focus']}")

    if approved and analysis.get("approved_summary"):
        lines.append("")
        lines.append("📝 Approved Pedagogical Summary:")
        lines.append(analysis["approved_summary"])

    if analysis.get("source_evidence_purged_or_deleted"):
        lines.append("")
        lines.append("🔒 Raw student evidence has been purged. Approved summary preserved.")

    return "\n".join(lines)


async def handle_evidence_analysis_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("v1|ea|"):
        return False

    await query.answer()
    parts = query.data.split("|")
    action = parts[2] if len(parts) > 2 else ""
    user = update.effective_user
    if not user:
        return False

    try:
        if action == "anlz":
            # v1|ea|anlz|{batch_id}|{rev}
            batch_id = un_b36(parts[3])
            revision = un_b36(parts[4]) if len(parts) > 4 else 1
            analysis = analyze_evidence_batch(
                telegram_user=user,
                batch_id=batch_id,
            )
            text = render_evidence_analysis_text(analysis)
            kb = evidence_analysis_keyboard(
                int(analysis["id"]),
                int(analysis["batch_id"]),
                revision + 1,
                approved=bool(analysis.get("approved", 0)),
            )
            await query.edit_message_text(text, reply_markup=kb)
            return True

        elif action == "v":
            # v1|ea|v|{an_id}|{batch_id}|{rev}
            an_id = un_b36(parts[3])
            batch_id = un_b36(parts[4])
            revision = un_b36(parts[5]) if len(parts) > 5 else 1
            analysis = get_evidence_analysis(telegram_user=user, analysis_id=an_id)
            if not analysis:
                await query.edit_message_text("Analysis finding not found.")
                return True
            text = render_evidence_analysis_text(analysis)
            kb = evidence_analysis_keyboard(
                int(analysis["id"]),
                int(analysis["batch_id"]),
                revision + 1,
                approved=bool(analysis.get("approved", 0)),
            )
            await query.edit_message_text(text, reply_markup=kb)
            return True

        elif action == "appr":
            # v1|ea|appr|{an_id}|{batch_id}|{rev}
            an_id = un_b36(parts[3])
            batch_id = un_b36(parts[4])
            revision = un_b36(parts[5]) if len(parts) > 5 else 1
            analysis = approve_evidence_analysis(telegram_user=user, analysis_id=an_id)
            if not analysis:
                await query.edit_message_text("Analysis finding could not be approved.")
                return True
            text = "✅ Analysis finding approved successfully!\n\n" + render_evidence_analysis_text(analysis)
            kb = evidence_analysis_keyboard(
                int(analysis["id"]),
                int(analysis["batch_id"]),
                revision + 1,
                approved=True,
            )
            await query.edit_message_text(text, reply_markup=kb)
            return True

        elif action == "rej":
            # v1|ea|rej|{an_id}|{batch_id}|{rev}
            an_id = un_b36(parts[3])
            batch_id = un_b36(parts[4])
            revision = un_b36(parts[5]) if len(parts) > 5 else 1
            kb = evidence_analysis_confirm_reject_keyboard(an_id, batch_id, revision)
            await query.edit_message_text(
                "Are you sure you want to reject and dismiss this finding?",
                reply_markup=kb,
            )
            return True

        elif action == "crej":
            # v1|ea|crej|{an_id}|{batch_id}|{rev}
            an_id = un_b36(parts[3])
            batch_id = un_b36(parts[4])
            revision = un_b36(parts[5]) if len(parts) > 5 else 1
            reject_evidence_analysis(telegram_user=user, analysis_id=an_id)
            from evidence_keyboards import evidence_batch_details_keyboard
            from evidence_service import get_evidence_batch
            batch = get_evidence_batch(telegram_user=user, batch_id=batch_id)
            if batch:
                kb = evidence_batch_details_keyboard(
                    batch_id, int(batch["class_id"]), revision + 1, batch.get("items", [])
                )
                await query.edit_message_text("❌ Finding dismissed.", reply_markup=kb)
            else:
                await query.edit_message_text("❌ Finding dismissed.")
            return True

        elif action == "edt":
            # v1|ea|edt|{an_id}|{batch_id}|{rev}
            an_id = un_b36(parts[3])
            batch_id = un_b36(parts[4])
            if context.user_data is not None:
                context.user_data["evidence_editing_analysis_id"] = an_id
                context.user_data["evidence_editing_batch_id"] = batch_id
            await query.edit_message_text(
                "✏️ Please send your custom approved summary in a reply message."
            )
            return True

    except Exception as exc:
        logger.exception("Error handling evidence analysis callback: %s", exc)
        await query.edit_message_text(f"⚠️ Error: {exc}")
        return True

    return False
