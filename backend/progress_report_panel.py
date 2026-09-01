"""TeacherOS Progress Report Panel (Day 23).

Dispatches Telegram callbacks for report generation, section editing, explicit approval,
and Word / PDF document export delivery.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any

from telegram import InputFile, Update
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes

from class_service import get_class
from curriculum_discipline_service import get_current_curriculum_unit
from database import database_connection, register_telegram_user
from entitlement_service import check_feature_access
from progress_report_keyboards import (
    _base36,
    report_dashboard_keyboard,
    report_edit_cancel_keyboard,
    report_edit_section_picker_keyboard,
    report_list_keyboard,
    report_type_picker_keyboard,
    report_view_keyboard,
)
from progress_report_service import (
    REPORT_TYPE_LABELS,
    approve_progress_report,
    export_progress_report_pdf,
    export_progress_report_word,
    generate_progress_report,
    get_progress_report,
    list_progress_reports,
    update_progress_report_section,
)

logger = logging.getLogger(__name__)

_CALLBACK_PATTERN = re.compile(
    r"^v1\|rp\|(?P<action>[a-z0-9_]{1,10})\|"
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


def _format_report_preview(report: dict[str, Any]) -> str:
    status_icon = "✅ Approved" if report["status"] == "approved" else "📝 Draft (Needs Review)"
    evidence_note = "⚠️ INSUFFICIENT EVIDENCE (Teacher input needed)" if report.get("has_insufficient_evidence") else "🔒 Grounded in Approved Evidence"

    lines = [
        f"📋 {report['title']}",
        f"Type: {REPORT_TYPE_LABELS.get(report['report_type'], report['report_type'])}",
        f"Status: {status_icon} (v{report['version']})",
        f"Period: {report['reporting_period_start']} to {report['reporting_period_end']}",
        f"Evidence Status: {evidence_note}",
        "",
        "1. 📚 Learning Covered:",
        f"{report.get('learning_covered_text', '')}",
        "",
        "2. 💪 Observed Strengths:",
        f"{report.get('strengths_text', '')}",
        "",
        "3. ⚠️ Priorities Needing Support:",
        f"{report.get('priorities_text', '')}",
        "",
        "4. 🎯 Next Instructional Steps:",
        f"{report.get('next_steps_text', '')}",
        "",
        "5. 💬 Teacher Comments:",
        f"{report.get('teacher_comments', 'None')}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Callback Query Dispatcher
# ---------------------------------------------------------------------------

async def handle_progress_report_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle all progress report callbacks."""
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

    # -----------------------------------------------------------------------
    # Action: Dashboard Home (home)
    # -----------------------------------------------------------------------
    if action == "home":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        reports = list_progress_reports(user_id=user_id, class_id=class_id)

        lines = [
            f"📊 Progress Reports · {owned['display_name']}",
            "",
            "Turn approved lesson outcomes and evidence into evidence-safe reports:",
            "  • Whole-Class Summaries",
            "  • End-of-Unit Reports",
            "  • Teacher Reflections",
            "",
            f"Existing Reports: {len(reports)}",
            "",
            "🔒 Evidence Safety: Reports never invent attendance, effort, or behavior.",
        ]

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=report_dashboard_keyboard(
                class_id=class_id,
                revision=revision,
                reports_count=len(reports),
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: List Reports (list)
    # -----------------------------------------------------------------------
    if action == "list":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        reports = list_progress_reports(user_id=user_id, class_id=class_id)

        lines = [
            f"📜 Progress Reports List · {owned['display_name']}",
            "",
        ]
        if not reports:
            lines.append("No reports created yet. Tap 'Generate New Report' below.")
        else:
            lines.append("Select a report below to inspect, edit, approve, or export:")

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=report_list_keyboard(
                class_id=class_id,
                revision=revision,
                reports=reports,
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Choose Report Type (new)
    # -----------------------------------------------------------------------
    if action == "new":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        text = (
            f"➕ Generate Progress Report · {owned['display_name']}\n\n"
            "Choose report format:\n\n"
            "• Whole-Class Summary: Aggregates active syllabus targets & evidence.\n"
            "• End-of-Unit Summary: Aligned with current coursebook unit.\n"
            "• Teacher Reflection: Self-review of instructional adaptations."
        )

        await _safe_edit(
            query,
            text,
            reply_markup=report_type_picker_keyboard(class_id=class_id, revision=revision),
        )
        return

    # -----------------------------------------------------------------------
    # Actions: Generate specific type (tcls, tunt, tref)
    # -----------------------------------------------------------------------
    if action in {"tcls", "tunt", "tref"}:
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query, "Generating report...")

        type_map = {
            "tcls": "whole_class_summary",
            "tunt": "end_of_unit_summary",
            "tref": "teacher_reflection",
        }
        report_type = type_map[action]

        # Determine reporting period (past 30 days)
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        unit_id = None
        if report_type == "end_of_unit_summary":
            active_unit = get_current_curriculum_unit(user_id=user_id, class_id=class_id)
            if active_unit:
                unit_id = active_unit["id"]

        report = generate_progress_report(
            user_id=user_id,
            class_id=class_id,
            report_type=report_type,
            reporting_period_start=start_date,
            reporting_period_end=end_date,
            unit_id=unit_id,
        )

        preview = _format_report_preview(report)
        await _safe_edit(
            query,
            preview,
            reply_markup=report_view_keyboard(
                report_id=report["id"],
                class_id=class_id,
                revision=revision,
                status=report["status"],
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: View Report (view)
    # -----------------------------------------------------------------------
    if action == "view":
        report_id = _decode_b36(raw_object)
        report = get_progress_report(user_id=user_id, report_id=report_id)
        if not report:
            await _answer_query(query, "Report not found.")
            return

        await _answer_query(query)
        preview = _format_report_preview(report)
        await _safe_edit(
            query,
            preview,
            reply_markup=report_view_keyboard(
                report_id=report_id,
                class_id=report["class_id"],
                revision=revision,
                status=report["status"],
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Approve Report (appr)
    # -----------------------------------------------------------------------
    if action == "appr":
        report_id = _decode_b36(raw_object)
        approved = approve_progress_report(user_id=user_id, report_id=report_id)
        if not approved:
            await _answer_query(query, "Report not found.")
            return

        await _answer_query(query, "Report Approved!")
        preview = _format_report_preview(approved)
        await _safe_edit(
            query,
            "✅ Report Marked Final & Approved!\n\n" + preview,
            reply_markup=report_view_keyboard(
                report_id=report_id,
                class_id=approved["class_id"],
                revision=revision,
                status="approved",
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Actions: Edit Section (esec, ecom, enxt, estr, epri)
    # -----------------------------------------------------------------------
    if action == "esec":
        report_id = _decode_b36(raw_object)
        report = get_progress_report(user_id=user_id, report_id=report_id)
        if not report:
            await _answer_query(query, "Report not found.")
            return

        await _answer_query(query)
        await _safe_edit(
            query,
            f"✏ Edit Report Section · {report['title']}\n\nSelect a section to edit:",
            reply_markup=report_edit_section_picker_keyboard(
                report_id=report_id,
                class_id=report["class_id"],
                revision=revision,
            ),
        )
        return

    if action in {"ecom", "enxt", "estr", "epri"}:
        report_id = _decode_b36(raw_object)
        report = get_progress_report(user_id=user_id, report_id=report_id)
        if not report:
            await _answer_query(query, "Report not found.")
            return

        field_map = {
            "ecom": ("teacher_comments", "Teacher Comments"),
            "enxt": ("next_steps_text", "Next Steps"),
            "estr": ("strengths_text", "Observed Strengths"),
            "epri": ("priorities_text", "Priorities"),
        }
        field_key, field_name = field_map[action]

        context.user_data["report_edit"] = {
            "report_id": report_id,
            "class_id": report["class_id"],
            "field_name": field_key,
            "revision": revision,
            "state": "editing",
        }

        await _answer_query(query)
        current_val = report.get(field_key) or "(empty)"
        text = (
            f"✏ Edit {field_name}\n\n"
            f"Current Content:\n{current_val}\n\n"
            "Reply with your updated text for this section:"
        )

        await _safe_edit(
            query,
            text,
            reply_markup=report_edit_cancel_keyboard(report_id=report_id, revision=revision),
        )
        return

    # -----------------------------------------------------------------------
    # Actions: Word (.docx) & PDF (.pdf) Exports (exw, exp)
    # -----------------------------------------------------------------------
    if action == "exw":
        report_id = _decode_b36(raw_object)
        report = get_progress_report(user_id=user_id, report_id=report_id)
        if not report:
            await _answer_query(query, "Report not found.")
            return
        if report.get("status") != "approved":
            await _answer_query(query, "Approve the report before exporting it.")
            return
        access = check_feature_access(tg_user.id, "progress_reports_export")
        if not access["allowed"]:
            await _answer_query(query, access.get("upgrade_prompt") or "Report export is unavailable on your plan.")
            return

        await _answer_query(query, "Generating Word document...")
        try:
            filename, data = export_progress_report_word(user_id=user_id, report_id=report_id)
        except Exception:
            logger.exception("Word progress report export failed")
            await _answer_query(query, "Word export failed safely. The report remains unchanged; try again later.")
            return

        chat_id = update.effective_chat.id if update.effective_chat else tg_user_id
        await context.bot.send_document(
            chat_id=chat_id,
            document=InputFile(io.BytesIO(data), filename=filename),
            caption=f"📄 Word Export for {report['title']}",
        )
        return

    if action == "exp":
        report_id = _decode_b36(raw_object)
        report = get_progress_report(user_id=user_id, report_id=report_id)
        if not report:
            await _answer_query(query, "Report not found.")
            return
        if report.get("status") != "approved":
            await _answer_query(query, "Approve the report before exporting it.")
            return
        access = check_feature_access(tg_user.id, "progress_reports_export")
        if not access["allowed"]:
            await _answer_query(query, access.get("upgrade_prompt") or "Report export is unavailable on your plan.")
            return

        await _answer_query(query, "Generating PDF document...")
        try:
            filename, data = export_progress_report_pdf(user_id=user_id, report_id=report_id)
        except Exception:
            logger.exception("PDF progress report export failed")
            await _answer_query(query, "PDF export failed safely. The report remains unchanged; try again later.")
            return

        chat_id = update.effective_chat.id if update.effective_chat else tg_user_id
        await context.bot.send_document(
            chat_id=chat_id,
            document=InputFile(io.BytesIO(data), filename=filename),
            caption=f"📑 PDF Export for {report['title']}",
        )
        return


# ---------------------------------------------------------------------------
# Message Handler for Section Editing
# ---------------------------------------------------------------------------

async def handle_progress_report_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle text input when editing a progress report section."""
    edit_state = context.user_data.get("report_edit")
    if not isinstance(edit_state, dict) or edit_state.get("state") != "editing":
        return

    msg = update.message
    if msg is None or not msg.text:
        return

    tg_user = update.effective_user
    if tg_user is None:
        return

    user_id = register_telegram_user(tg_user)
    report_id = int(edit_state["report_id"])
    class_id = int(edit_state["class_id"])
    field_name = edit_state["field_name"]
    revision = int(edit_state["revision"])

    new_text = msg.text.strip()
    updated = update_progress_report_section(
        user_id=user_id,
        report_id=report_id,
        field_name=field_name,
        new_value=new_text,
    )
    context.user_data.pop("report_edit", None)

    if not updated:
        await msg.reply_text("⚠️ Could not update report section.")
        return

    preview = _format_report_preview(updated)
    await msg.reply_text(
        f"✅ Section Updated (v{updated['version']})!\n\n" + preview,
        reply_markup=report_view_keyboard(
            report_id=report_id,
            class_id=class_id,
            revision=revision,
            status=updated["status"],
        ),
    )
