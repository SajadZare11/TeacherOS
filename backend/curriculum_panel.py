"""TeacherOS CEFR Curriculum Panel (Day 22).

Dispatches Telegram callbacks for coursebook unit alignment, CEFR communicative mode
mappings, and teacher override controls.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from telegram import Update
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes

from class_service import get_class
from curriculum_discipline_service import (
    COMMUNICATIVE_MODE_LABELS,
    get_class_curriculum_coverage,
    get_current_curriculum_unit,
    list_curriculum_units,
    override_cefr_mapping,
    save_curriculum_unit,
)
from curriculum_keyboards import (
    _base36,
    cefr_coverage_keyboard,
    cefr_mapping_detail_keyboard,
    curriculum_home_keyboard,
    mode_picker_keyboard,
    unit_editor_cancel_keyboard,
)
from database import database_connection, register_telegram_user

logger = logging.getLogger(__name__)

_CALLBACK_PATTERN = re.compile(
    r"^v1\|cu\|(?P<action>[a-z0-9_]{1,10})\|"
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

async def handle_curriculum_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle all CEFR curriculum and unit callbacks."""
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
    # Action: Curriculum Home (home)
    # -----------------------------------------------------------------------
    if action == "home":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        unit = get_current_curriculum_unit(user_id=user_id, class_id=class_id)

        lines = [
            f"📚 Curriculum & CEFR Alignment · {owned['display_name']}",
            f"Target CEFR Level: {owned.get('level') or 'B1'}",
            "",
        ]

        if unit:
            lines.extend([
                f"📖 Active Unit: Unit {unit['unit_number']} · {unit['unit_title']}",
                f"📚 Coursebook: {unit.get('coursebook_name') or 'Not specified'}",
                f"🎯 Syllabus Target: {unit.get('exam_syllabus_target') or 'General Communicative'}",
                f"📝 Notes: {unit.get('curriculum_notes') or 'None'}",
            ])
        else:
            lines.extend([
                "No active unit currently set for this class.",
                "Set your coursebook unit to focus lesson planning on aligned communicative goals.",
            ])

        lines.extend([
            "",
            "🔒 Lightweight alignment: TeacherOS stores unit titles and can-do goals without scraping copyrighted textbooks.",
        ])

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=curriculum_home_keyboard(
                class_id=class_id,
                revision=revision,
                has_unit=unit is not None,
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Unit Editor Prompt (uedit)
    # -----------------------------------------------------------------------
    if action == "uedit":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        context.user_data["curriculum_edit"] = {
            "class_id": class_id,
            "revision": revision,
            "state": "unit_text",
        }

        text = (
            f"✏ Set Current Coursebook Unit · {owned['display_name']}\n\n"
            "Reply with your unit info separated by vertical bars (|):\n\n"
            "Format:\n"
            "`Unit Number | Unit Title | Coursebook Name | Notes`\n\n"
            "Example:\n"
            "`3 | Business Travel & Negotiations | Empower B2 | Target: polite indirect questions`\n\n"
            "Only the title is required. Do not include copyrighted textbook pages."
        )

        await _safe_edit(
            query,
            text,
            reply_markup=unit_editor_cancel_keyboard(class_id=class_id, revision=revision),
        )
        return

    # -----------------------------------------------------------------------
    # Action: CEFR Coverage (cov, cfilt)
    # -----------------------------------------------------------------------
    if action in {"cov", "cfilt"}:
        class_id = 0
        current_filter = "all"

        if action == "cov":
            class_id = _decode_b36(raw_object)
        else:
            f_code = raw_object[0] if raw_object else "0"
            class_id_str = raw_object[1:] if len(raw_object) > 1 else ""
            class_id = _decode_b36(class_id_str)
            f_map = {"0": "all", "1": "covered", "2": "partly", "3": "not_yet"}
            current_filter = f_map.get(f_code, "all")

        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        cov_data = get_class_curriculum_coverage(user_id=user_id, class_id=class_id)

        target_list: list[dict[str, Any]] = []
        if current_filter == "covered":
            target_list = cov_data.get("covered_targets", [])
        elif current_filter == "partly":
            target_list = cov_data.get("partly_covered_targets", [])
        elif current_filter == "not_yet":
            target_list = cov_data.get("not_yet_covered_targets", [])
        else:
            target_list = (
                cov_data.get("covered_targets", [])
                + cov_data.get("partly_covered_targets", [])
                + cov_data.get("not_yet_covered_targets", [])
            )

        dist = cov_data.get("communicative_mode_distribution", {})
        lines = [
            f"📊 CEFR Communicative Coverage · {owned['display_name']}",
            "",
            "🎯 Coverage Summary:",
            f"  • Covered / Secure: {cov_data.get('covered_count', 0)}",
            f"  • Partly Covered: {cov_data.get('partly_covered_count', 0)}",
            f"  • Not Yet Covered: {cov_data.get('not_yet_covered_count', 0)}",
            "",
            "🗣 Mode Breakdown:",
            f"  • Spoken Interaction: {dist.get('interaction_spoken', 0)}",
            f"  • Spoken Production: {dist.get('production_speaking', 0)}",
            f"  • Written Production: {dist.get('production_writing', 0)}",
            f"  • Reading / Listening: {dist.get('reception_reading', 0) + dist.get('reception_listening', 0)}",
            f"  • Language Mediation: {dist.get('mediation', 0)}",
            "",
            "Select an objective below to inspect or override its CEFR category:",
        ]

        if not target_list:
            lines.append("\n(No objectives in this category yet.)")

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=cefr_coverage_keyboard(
                class_id=class_id,
                revision=revision,
                mappings=target_list,
                current_filter=current_filter,
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: Mapping Details & Override (map, mchg, mspp, mspi, mwrp, mwri, mrea, mlis, mmed)
    # -----------------------------------------------------------------------
    if action == "map":
        mapping_id = _decode_b36(raw_object)
        with database_connection() as conn:
            m = conn.execute(
                """
                SELECT m.*, o.objective
                FROM cefr_objective_mappings AS m
                JOIN class_objectives AS o ON o.id = m.objective_id
                WHERE m.id = ? AND m.user_id = ?
                """,
                (mapping_id, user_id),
            ).fetchone()
        if not m:
            await _answer_query(query, "Mapping not found.")
            return

        await _answer_query(query)
        mode_name = COMMUNICATIVE_MODE_LABELS.get(m["communicative_mode"], m["communicative_mode"])
        overridden = "Yes (Teacher Corrected)" if m.get("teacher_overridden") else "No (AI Mapped)"

        lines = [
            "🎯 CEFR Objective Mapping Details",
            "",
            f"📌 Objective:\n{m['objective']}",
            "",
            f"🗣 Communicative Mode: {mode_name}",
            f"🏷 Competence: {m['competence_category'].replace('_', ' ').title()}",
            f"📊 Level: {m['cefr_level']}",
            f"🔒 Teacher Override: {overridden}",
            f"💬 Can-Do Statement: \"{m['can_do_statement']}\"",
        ]

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=cefr_mapping_detail_keyboard(
                mapping_id=mapping_id,
                class_id=m["class_id"],
                revision=revision,
            ),
        )
        return

    if action == "mchg":
        mapping_id = _decode_b36(raw_object)
        with database_connection() as conn:
            m = conn.execute(
                "SELECT class_id FROM cefr_objective_mappings WHERE id = ? AND user_id = ?",
                (mapping_id, user_id),
            ).fetchone()
        if not m:
            await _answer_query(query, "Mapping not found.")
            return

        await _answer_query(query)
        await _safe_edit(
            query,
            "✏ Choose CEFR Communicative Mode\n\nSelect the primary communicative activity for this syllabus target:",
            reply_markup=mode_picker_keyboard(
                mapping_id=mapping_id,
                class_id=m["class_id"],
                revision=revision,
            ),
        )
        return

    if action in {"mspp", "mspi", "mwrp", "mwri", "mrea", "mlis", "mmed"}:
        mapping_id = _decode_b36(raw_object)
        mode_code_map = {
            "mspp": "production_speaking",
            "mspi": "interaction_spoken",
            "mwrp": "production_writing",
            "mwri": "interaction_written",
            "mrea": "reception_reading",
            "mlis": "reception_listening",
            "mmed": "mediation",
        }
        selected_mode = mode_code_map[action]
        updated = override_cefr_mapping(
            user_id=user_id,
            mapping_id=mapping_id,
            communicative_mode=selected_mode,
            teacher_note="Teacher updated communicative mode",
        )
        if not updated:
            await _answer_query(query, "Mapping not found.")
            return

        await _answer_query(query, f"Mode set to: {COMMUNICATIVE_MODE_LABELS.get(selected_mode, selected_mode)}")

        with database_connection() as conn:
            m = conn.execute(
                """
                SELECT m.*, o.objective
                FROM cefr_objective_mappings AS m
                JOIN class_objectives AS o ON o.id = m.objective_id
                WHERE m.id = ? AND m.user_id = ?
                """,
                (mapping_id, user_id),
            ).fetchone()

        mode_name = COMMUNICATIVE_MODE_LABELS.get(m["communicative_mode"], m["communicative_mode"])
        lines = [
            "✅ CEFR Mapping Overridden by Teacher",
            "",
            f"📌 Objective:\n{m['objective']}",
            "",
            f"🗣 New Communicative Mode: {mode_name}",
            "🔒 This teacher correction will be retained in future class context.",
        ]

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=cefr_mapping_detail_keyboard(
                mapping_id=mapping_id,
                class_id=m["class_id"],
                revision=revision,
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Action: All Units History (ulist)
    # -----------------------------------------------------------------------
    if action == "ulist":
        class_id = _decode_b36(raw_object)
        owned = get_class(telegram_user_id=tg_user_id, class_id=class_id)
        if not owned:
            await _answer_query(query, "Class not found.")
            return

        await _answer_query(query)
        units = list_curriculum_units(user_id=user_id, class_id=class_id)

        lines = [
            f"📜 Unit History · {owned['display_name']}",
            "",
        ]

        if not units:
            lines.append("No curriculum units recorded yet.")
        else:
            for u in units:
                st = "Active" if u["status"] == "current" else u["status"].title()
                book = f" ({u['coursebook_name']})" if u.get("coursebook_name") else ""
                lines.append(f"• Unit {u['unit_number']}: {u['unit_title']}{book} · {st}")

        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=curriculum_home_keyboard(
                class_id=class_id,
                revision=revision,
                has_unit=bool(units),
            ),
        )
        return


# ---------------------------------------------------------------------------
# Text Message Handler for Unit Input
# ---------------------------------------------------------------------------

async def handle_curriculum_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle text responses during curriculum unit editing."""
    edit_state = context.user_data.get("curriculum_edit")
    if not isinstance(edit_state, dict) or edit_state.get("state") != "unit_text":
        return

    msg = update.message
    if msg is None or not msg.text:
        return

    tg_user = update.effective_user
    if tg_user is None:
        return

    class_id = int(edit_state["class_id"])
    revision = int(edit_state["revision"])
    user_id = register_telegram_user(tg_user)

    raw_text = msg.text.strip()
    parts = [p.strip() for p in raw_text.split("|")]

    unit_number = "1"
    unit_title = parts[0]
    coursebook_name = None
    curriculum_notes = None

    if len(parts) >= 2:
        unit_number = parts[0]
        unit_title = parts[1]
    if len(parts) >= 3:
        coursebook_name = parts[2]
    if len(parts) >= 4:
        curriculum_notes = parts[3]

    try:
        saved = save_curriculum_unit(
            user_id=user_id,
            class_id=class_id,
            unit_number=unit_number,
            unit_title=unit_title,
            coursebook_name=coursebook_name,
            curriculum_notes=curriculum_notes,
            status="current",
        )
        context.user_data.pop("curriculum_edit", None)

        response_lines = [
            "✅ Active Coursebook Unit Saved!",
            "",
            f"📖 Unit {saved['unit_number']}: {saved['unit_title']}",
            f"📚 Coursebook: {saved.get('coursebook_name') or 'Not specified'}",
            f"📝 Notes: {saved.get('curriculum_notes') or 'None'}",
            "",
            "Lesson planning and objective mappings will now align with this unit.",
        ]

        await msg.reply_text(
            "\n".join(response_lines),
            reply_markup=curriculum_home_keyboard(
                class_id=class_id,
                revision=revision,
                has_unit=True,
            ),
        )
    except Exception as exc:
        logger.warning("Failed to save curriculum unit: %s", exc)
        await msg.reply_text(
            f"⚠️ Could not save unit: {exc}\n\nPlease use format: `Unit Number | Unit Title | Coursebook Name`",
            reply_markup=unit_editor_cancel_keyboard(class_id=class_id, revision=revision),
        )
