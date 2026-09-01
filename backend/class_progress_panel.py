"""TeacherOS Evidence-Linked Class Progress UI Panel (Day 21).

Dispatches Telegram callbacks for traceable class progress, objective status
corrections, proposed objective review, and instructional health cards.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from telegram import Update
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes

from class_progress_keyboards import (
    _base36,
    health_card_keyboard,
    objective_detail_keyboard,
    objective_status_picker_keyboard,
    objectives_list_keyboard,
    progress_overview_keyboard,
    proposed_objective_review_keyboard,
    proposed_objectives_keyboard,
    timeline_browser_keyboard,
)
from class_progress_service import (
    OBJECTIVE_STATUS_LABELS,
    approve_proposed_objective,
    get_class_health_card,
    get_class_progress_overview,
    get_objective_detail_with_sources,
    list_class_objectives,
    list_pending_proposed_objectives,
    reject_proposed_objective,
    update_objective_status,
)
from class_service import get_class
from database import register_telegram_user

logger = logging.getLogger(__name__)

_CALLBACK_PATTERN = re.compile(
    r"^v1\|pr\|(?P<action>[a-z0-9_]{1,10})\|"
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
# Callback Handler Dispatcher
# ---------------------------------------------------------------------------

async def handle_progress_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle all evidence-linked progress callbacks."""
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
    # Action: Progress Home Overview (home)
    # -----------------------------------------------------------------------
    if action == "home":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        overview = get_class_progress_overview(user_id=user_id, class_id=class_id)
        health = overview.get("health_card", {})
        counts = overview.get("objectives_count", {})

        lines = [
            f"📈 Evidence-Linked Progress · {owned['display_name']}",
            f"CEFR Level: {owned.get('level') or 'B1'}",
            "",
            "🎯 Syllabus & Can-Do Targets:",
            f"  • Active / In Progress: {counts.get('current', 0)}",
            f"  • Needs Support: {counts.get('needs_support', 0)}",
            f"  • Teacher-Confirmed Secure: {counts.get('secure', 0)}",
            f"  • Paused: {counts.get('paused', 0)}",
            "",
            f"🩺 Instructional Health Diagnosis:",
            f"  {health.get('headline', 'On Track')}",
            f"  👉 {health.get('recommendation', 'Continue standard syllabus.')}",
            "",
            f"📥 Approved Evidence Batches: {overview.get('evidence_batches_count', 0)}",
            f"🔁 Spaced Retrieval Due: {overview.get('due_reviews_count', 0)}",
            "",
            "All progress claims are backed by source lesson outcomes or approved work.",
        ]

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=progress_overview_keyboard(
                class_id=class_id,
                revision=revision,
                pending_proposals_count=overview.get("pending_proposals_count", 0),
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Objectives List & Filter (objs, ofilt)
    # -----------------------------------------------------------------------
    if action in {"objs", "ofilt"}:
        class_id = 0
        current_filter = "current"

        if action == "objs":
            class_id = _decode_b36(raw_object)
        else:
            f_code = raw_object[0] if raw_object else "1"
            class_id_str = raw_object[1:] if len(raw_object) > 1 else ""
            class_id = _decode_b36(class_id_str)
            f_map = {"0": "all", "1": "current", "2": "needs_support", "3": "secure"}
            current_filter = f_map.get(f_code, "current")

        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        objectives = list_class_objectives(
            user_id=user_id,
            class_id=class_id,
            status_filter=current_filter,
        )

        filter_title = {
            "current": "Active Targets",
            "needs_support": "Needs Support",
            "secure": "Teacher-Confirmed Secure",
            "all": "All Objectives",
        }.get(current_filter, current_filter.title())

        lines = [
            f"🎯 Class Objectives · {owned['display_name']}",
            f"Filter: {filter_title} ({len(objectives)} items)\n",
            "Select an objective to inspect source evidence, change status, or edit:",
        ]

        if not objectives:
            lines.append("\n(No objectives currently match this filter.)")

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=objectives_list_keyboard(
                class_id=class_id,
                revision=revision,
                objectives=objectives,
                current_filter=current_filter,
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Objective Details & Status Update (obj, stask, stact, stsup, stsec, stpau, starch, evsrc)
    # -----------------------------------------------------------------------
    if action == "obj":
        objective_id = _decode_b36(raw_object)
        detail = get_objective_detail_with_sources(user_id=user_id, objective_id=objective_id)
        if not detail:
            await _answer_query(query, "Objective not found.")
            return

        await _answer_query(query)
        status_label = OBJECTIVE_STATUS_LABELS.get(detail["status"], detail["status"].title())
        secure_text = "Yes (Verified)" if detail.get("is_secure") else "No (In Progress)"

        lines = [
            f"🎯 Objective Details",
            "",
            f"📌 Target:\n{detail['objective']}",
            "",
            f"📊 Status: {status_label}",
            f"🔒 Teacher-Confirmed Secure: {secure_text}",
            f"🏷 Category: {detail.get('category', 'general').title()}",
            f"🔗 Traceable Sources Linked: {len(detail.get('evidence_links', []))}",
        ]

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=objective_detail_keyboard(
                objective_id=objective_id,
                class_id=detail["class_id"],
                revision=revision,
            ),
        )
        return

    if action == "stask":
        objective_id = _decode_b36(raw_object)
        detail = get_objective_detail_with_sources(user_id=user_id, objective_id=objective_id)
        if not detail:
            await _answer_query(query, "Objective not found.")
            return

        await _answer_query(query)
        await _safe_edit(
            query,
            f"✏ Update Objective Status\n\n"
            f"'{detail['objective'][:45]}'\n\n"
            "Select the teacher-evaluated status for this target:",
            reply_markup=objective_status_picker_keyboard(
                objective_id=objective_id,
                class_id=detail["class_id"],
                revision=revision,
                current_status=detail["status"],
            ),
        )
        return

    if action in {"stact", "stsup", "stsec", "stpau", "starch"}:
        objective_id = _decode_b36(raw_object)
        target_status_map = {
            "stact": "current",
            "stsup": "needs_support",
            "stsec": "secure",
            "stpau": "paused",
            "starch": "archived",
        }
        status_choice = target_status_map[action]
        updated = update_objective_status(user_id=user_id, objective_id=objective_id, new_status=status_choice)
        if not updated:
            await _answer_query(query, "Objective not found.")
            return

        status_label = OBJECTIVE_STATUS_LABELS.get(status_choice, status_choice.title())
        await _answer_query(query, f"Status updated: {status_label}")

        lines = [
            "✅ Objective Status Updated",
            "",
            f"📌 Target:\n{updated['objective']}",
            "",
            f"📊 New Status: {status_label}",
            f"🔒 Teacher-Confirmed Secure: {'Yes (Verified)' if updated.get('is_secure') else 'No'}",
        ]

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=objective_detail_keyboard(
                objective_id=objective_id,
                class_id=updated["class_id"],
                revision=revision,
            ),
        )
        return

    if action == "evsrc":
        objective_id = _decode_b36(raw_object)
        detail = get_objective_detail_with_sources(user_id=user_id, objective_id=objective_id)
        if not detail:
            await _answer_query(query, "Objective not found.")
            return

        await _answer_query(query)
        links = detail.get("evidence_links", [])

        lines = [
            f"🔎 Traceable Evidence Sources",
            f"Target: '{detail['objective'][:40]}'",
            "",
        ]

        if not links:
            lines.append("No explicit evidence records linked yet.")
        else:
            for idx, lnk in enumerate(links[:5], 1):
                src_name = lnk["source_type"].replace("_", " ").title()
                supp = lnk["support_level"].replace("_", " ").title()
                excerpt = lnk["evidence_excerpt"][:60]
                lines.append(f"{idx}. [{src_name}] · {supp}")
                lines.append(f"   \"{excerpt}\"")

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=objective_detail_keyboard(
                objective_id=objective_id,
                class_id=detail["class_id"],
                revision=revision,
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Proposed Objectives (props, prop, apact, apsup, prej)
    # -----------------------------------------------------------------------
    if action == "props":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        proposals = list_pending_proposed_objectives(user_id=user_id, class_id=class_id)

        lines = [
            f"💡 Proposed Objectives · {owned['display_name']}",
            "",
            f"Pending AI Proposals: {len(proposals)}",
            "",
            "These can-do targets were extracted from generated lesson plans or approved evidence.",
            "Teacher approval is required before saving into active class context.",
        ]

        if not proposals:
            lines.append("\n(No pending proposed objectives at this time.)")

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=proposed_objectives_keyboard(
                class_id=class_id,
                revision=revision,
                proposals=proposals,
            ),
        )
        return

    if action == "prop":
        proposal_id = _decode_b36(raw_object)
        with database_connection() as conn:
            prop = conn.execute(
                "SELECT * FROM proposed_class_objectives WHERE id = ? AND user_id = ?",
                (proposal_id, user_id),
            ).fetchone()
        if not prop:
            await _answer_query(query, "Proposal not found.")
            return

        await _answer_query(query)
        src_name = prop["source_type"].replace("_", " ").title()

        lines = [
            "💡 Proposed Objective Review",
            "",
            f"🎯 Proposed Target:\n{prop['objective_text']}",
            "",
            f"🏷 Category: {prop['category'].title()}",
            f"📌 Source: {src_name}",
            f"💬 Rationale: {prop['rationale']}",
            "",
            "Adopt this target into your class syllabus or dismiss:",
        ]

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=proposed_objective_review_keyboard(
                proposal_id=proposal_id,
                class_id=prop["class_id"],
                revision=revision,
            ),
        )
        return

    if action in {"apact", "apsup"}:
        proposal_id = _decode_b36(raw_object)
        target_status = "current" if action == "apact" else "needs_support"
        approved = approve_proposed_objective(
            user_id=user_id,
            proposal_id=proposal_id,
            target_status=target_status,
        )
        if not approved:
            await _answer_query(query, "Proposal not found or expired.")
            return

        await _answer_query(query, "Objective adopted!")
        class_id = approved["class_id"]
        remaining = list_pending_proposed_objectives(user_id=user_id, class_id=class_id)

        lines = [
            "✅ Objective Adopted into Syllabus!",
            "",
            f"🎯 Target:\n{approved['objective']}",
            f"📊 Status: {OBJECTIVE_STATUS_LABELS.get(approved['status'])}",
            "",
            f"Remaining Pending Proposals: {len(remaining)}",
        ]

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=proposed_objectives_keyboard(
                class_id=class_id,
                revision=revision,
                proposals=remaining,
            ),
        )
        return

    if action == "prej":
        proposal_id = _decode_b36(raw_object)
        with database_connection() as conn:
            prop = conn.execute(
                "SELECT class_id FROM proposed_class_objectives WHERE id = ? AND user_id = ?",
                (proposal_id, user_id),
            ).fetchone()
        class_id = prop["class_id"] if prop else 0

        dismissed = reject_proposed_objective(user_id=user_id, proposal_id=proposal_id)
        if not dismissed:
            await _answer_query(query, "Proposal not found.")
            return

        await _answer_query(query, "Proposal dismissed.")
        remaining = list_pending_proposed_objectives(user_id=user_id, class_id=class_id)

        await _safe_edit(
            query,
            f"❌ Objective proposal dismissed.\n\nRemaining Pending Proposals: {len(remaining)}",
            reply_markup=proposed_objectives_keyboard(
                class_id=class_id,
                revision=revision,
                proposals=remaining,
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Health Card (hlth)
    # -----------------------------------------------------------------------
    if action == "hlth":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        health = get_class_health_card(user_id=user_id, class_id=class_id)

        lines = [
            f"🩺 Class Health Card · {owned['display_name']}",
            "",
            f"Diagnosis: {health.get('headline')}",
            "",
            f"👉 Recommended Next Action:\n{health.get('recommendation')}",
            "",
            "Prioritizes instructional clarity and learning needs, not product usage metrics.",
        ]

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=health_card_keyboard(
                class_id=class_id,
                revision=revision,
                action_type=health.get("action_type", "plan_lesson"),
                lesson_id=health.get("lesson_id"),
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Timeline (time)
    # -----------------------------------------------------------------------
    if action == "time":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        overview = get_class_progress_overview(user_id=user_id, class_id=class_id)
        timeline = overview.get("recent_timeline", [])

        lines = [
            f"📜 Lesson & Outcome Timeline · {owned['display_name']}",
            "",
        ]

        if not timeline:
            lines.append("No taught lessons or outcomes recorded yet.")
        else:
            for idx, item in enumerate(timeline, 1):
                title = item.get("title", "Lesson")
                res = (item.get("result") or "taught").replace("_", " ").title()
                date_str = (item.get("taught_at") or item.get("updated_at") or "")[:10]
                lines.append(f"{idx}. {title} · {res} ({date_str})")
                if item.get("notes"):
                    lines.append(f"   Note: \"{item['notes'][:40]}\"")

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=timeline_browser_keyboard(
                class_id=class_id,
                revision=revision,
            ),
        )
        return
