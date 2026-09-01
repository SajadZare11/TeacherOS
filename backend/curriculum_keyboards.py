"""TeacherOS CEFR Curriculum Keyboards (Day 22).

Compact, bounded inline keyboards for managing coursebook units and CEFR mappings.
All callbacks strictly guaranteed <= 64 bytes.
"""
from __future__ import annotations

from typing import Any, Sequence
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from curriculum_discipline_service import COMMUNICATIVE_MODE_LABELS


def _base36(value: int) -> str:
    """Encode an integer to base36 for compact callback strings."""
    if value < 0:
        raise ValueError("Callback identifiers cannot be negative.")
    if value == 0:
        return "0"
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    encoded = ""
    while value:
        value, remainder = divmod(value, 36)
        encoded = alphabet[remainder] + encoded
    return encoded


def _cb(action: str, object_id: int | str, revision: int) -> str:
    """Construct a standard compact curriculum callback string."""
    encoded_id = _base36(object_id) if isinstance(object_id, int) else str(object_id)
    return f"v1|cu|{action}|{encoded_id}|{_base36(revision)}"


# ---------------------------------------------------------------------------
# Curriculum Home & Unit Keyboards
# ---------------------------------------------------------------------------

def curriculum_home_keyboard(
    class_id: int,
    revision: int,
    *,
    has_unit: bool = True,
) -> InlineKeyboardMarkup:
    """Main curriculum & CEFR dashboard keyboard."""
    unit_btn_text = "✏ Change Current Unit" if has_unit else "➕ Set Coursebook Unit"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(unit_btn_text, callback_data=_cb("uedit", class_id, revision)),
            InlineKeyboardButton("📊 CEFR Coverage", callback_data=_cb("cov", class_id, revision)),
        ],
        [
            InlineKeyboardButton("📜 Unit History", callback_data=_cb("ulist", class_id, revision)),
            InlineKeyboardButton("🎯 Class Objectives", callback_data=f"v1|pr|objs|{_base36(class_id)}|{_base36(revision)}"),
        ],
        [
            InlineKeyboardButton("⬅ Class Home", callback_data=f"v1|cl|open|{_base36(class_id)}|{_base36(revision)}"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0"),
        ],
    ])


def cefr_coverage_keyboard(
    class_id: int,
    revision: int,
    mappings: Sequence[dict[str, Any]],
    current_filter: str = "all",
) -> InlineKeyboardMarkup:
    """CEFR objective coverage browser."""
    rows: list[list[InlineKeyboardButton]] = []

    # Filter tabs row
    rows.append([
        InlineKeyboardButton(
            ("✓ " if current_filter == "all" else "") + "All",
            callback_data=_cb("cfilt", f"0{_base36(class_id)}", revision),
        ),
        InlineKeyboardButton(
            ("✓ " if current_filter == "covered" else "") + "Covered",
            callback_data=_cb("cfilt", f"1{_base36(class_id)}", revision),
        ),
        InlineKeyboardButton(
            ("✓ " if current_filter == "partly" else "") + "Partly",
            callback_data=_cb("cfilt", f"2{_base36(class_id)}", revision),
        ),
        InlineKeyboardButton(
            ("✓ " if current_filter == "not_yet" else "") + "Not Yet",
            callback_data=_cb("cfilt", f"3{_base36(class_id)}", revision),
        ),
    ])

    for m in mappings[:6]:
        m_id = int(m["id"])
        mode = m.get("communicative_mode", "")
        icon = "🗣" if "speaking" in mode or "spoken" in mode else ("✍" if "writing" in mode else "📖")
        statement = str(m.get("can_do_statement", ""))[:28]
        rows.append([
            InlineKeyboardButton(f"{icon} {statement}", callback_data=_cb("map", m_id, revision))
        ])

    rows.append([
        InlineKeyboardButton("⬅ Curriculum Home", callback_data=_cb("home", class_id, revision)),
        InlineKeyboardButton("🏫 Class Home", callback_data=f"v1|cl|open|{_base36(class_id)}|{_base36(revision)}"),
    ])

    return InlineKeyboardMarkup(rows)


def cefr_mapping_detail_keyboard(
    mapping_id: int,
    class_id: int,
    revision: int,
) -> InlineKeyboardMarkup:
    """Action keyboard for a specific CEFR objective mapping."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏ Override CEFR Mode", callback_data=_cb("mchg", mapping_id, revision)),
        ],
        [
            InlineKeyboardButton("📊 Back to Coverage", callback_data=_cb("cov", class_id, revision)),
            InlineKeyboardButton("⬅ Curriculum Home", callback_data=_cb("home", class_id, revision)),
        ],
    ])


def mode_picker_keyboard(
    mapping_id: int,
    class_id: int,
    revision: int,
) -> InlineKeyboardMarkup:
    """Mode picker for teacher override."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗣 Spoken Production", callback_data=_cb("mspp", mapping_id, revision)),
            InlineKeyboardButton("💬 Spoken Interaction", callback_data=_cb("mspi", mapping_id, revision)),
        ],
        [
            InlineKeyboardButton("✍ Written Production", callback_data=_cb("mwrp", mapping_id, revision)),
            InlineKeyboardButton("📨 Written Interaction", callback_data=_cb("mwri", mapping_id, revision)),
        ],
        [
            InlineKeyboardButton("📖 Reading", callback_data=_cb("mrea", mapping_id, revision)),
            InlineKeyboardButton("🎧 Listening", callback_data=_cb("mlis", mapping_id, revision)),
        ],
        [
            InlineKeyboardButton("🔄 Mediation", callback_data=_cb("mmed", mapping_id, revision)),
            InlineKeyboardButton("⬅ Cancel", callback_data=_cb("map", mapping_id, revision)),
        ],
    ])


def unit_editor_cancel_keyboard(
    class_id: int,
    revision: int,
) -> InlineKeyboardMarkup:
    """Cancel button for unit text input flow."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅ Cancel", callback_data=_cb("home", class_id, revision)),
        ],
    ])
