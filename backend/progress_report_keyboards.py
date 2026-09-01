"""TeacherOS Progress Report Keyboards (Day 23).

Compact, bounded inline keyboards for managing, editing, approving, and exporting reports.
All callbacks strictly guaranteed <= 64 bytes.
"""
from __future__ import annotations

from typing import Any, Sequence
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


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
    """Construct a standard compact report callback string."""
    encoded_id = _base36(object_id) if isinstance(object_id, int) else str(object_id)
    return f"v1|rp|{action}|{encoded_id}|{_base36(revision)}"


def report_dashboard_keyboard(
    class_id: int,
    revision: int,
    reports_count: int = 0,
) -> InlineKeyboardMarkup:
    """Main progress reports home keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Generate Report", callback_data=_cb("new", class_id, revision)),
            InlineKeyboardButton(f"📜 Reports ({reports_count})", callback_data=_cb("list", class_id, revision)),
        ],
        [
            InlineKeyboardButton("⬅ Class Home", callback_data=f"v1|cl|open|{_base36(class_id)}|{_base36(revision)}"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0"),
        ],
    ])


def report_type_picker_keyboard(
    class_id: int,
    revision: int,
) -> InlineKeyboardMarkup:
    """Choose report structure type."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Whole-Class Summary", callback_data=_cb("tcls", class_id, revision)),
        ],
        [
            InlineKeyboardButton("📖 End-of-Unit Summary", callback_data=_cb("tunt", class_id, revision)),
        ],
        [
            InlineKeyboardButton("💡 Teacher Reflection", callback_data=_cb("tref", class_id, revision)),
        ],
        [
            InlineKeyboardButton("⬅ Cancel", callback_data=_cb("home", class_id, revision)),
        ],
    ])


def report_view_keyboard(
    report_id: int,
    class_id: int,
    revision: int,
    *,
    status: str = "draft",
) -> InlineKeyboardMarkup:
    """Action keyboard for a specific progress report."""
    rows: list[list[InlineKeyboardButton]] = []

    action_row: list[InlineKeyboardButton] = [
        InlineKeyboardButton("✏ Edit Section", callback_data=_cb("esec", report_id, revision)),
    ]
    if status == "draft":
        action_row.append(
            InlineKeyboardButton("✅ Approve Final", callback_data=_cb("appr", report_id, revision))
        )
    rows.append(action_row)

    rows.append([
        InlineKeyboardButton("📄 Export Word (.docx)", callback_data=_cb("exw", report_id, revision)),
        InlineKeyboardButton("📑 Export PDF (.pdf)", callback_data=_cb("exp", report_id, revision)),
    ])

    rows.append([
        InlineKeyboardButton("📜 Reports List", callback_data=_cb("list", class_id, revision)),
        InlineKeyboardButton("⬅ Reports Home", callback_data=_cb("home", class_id, revision)),
    ])

    return InlineKeyboardMarkup(rows)


def report_edit_section_picker_keyboard(
    report_id: int,
    class_id: int,
    revision: int,
) -> InlineKeyboardMarkup:
    """Select section to update."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 Teacher Comments", callback_data=_cb("ecom", report_id, revision)),
            InlineKeyboardButton("🎯 Next Steps", callback_data=_cb("enxt", report_id, revision)),
        ],
        [
            InlineKeyboardButton("💪 Observed Strengths", callback_data=_cb("estr", report_id, revision)),
            InlineKeyboardButton("⚠️ Priorities", callback_data=_cb("epri", report_id, revision)),
        ],
        [
            InlineKeyboardButton("⬅ Back to Report", callback_data=_cb("view", report_id, revision)),
        ],
    ])


def report_edit_cancel_keyboard(
    report_id: int,
    revision: int,
) -> InlineKeyboardMarkup:
    """Cancel text input for report edit."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅ Cancel Edit", callback_data=_cb("view", report_id, revision)),
        ],
    ])


def report_list_keyboard(
    class_id: int,
    revision: int,
    reports: Sequence[dict[str, Any]],
) -> InlineKeyboardMarkup:
    """List of generated progress reports."""
    rows: list[list[InlineKeyboardButton]] = []
    for r in reports[:6]:
        r_id = int(r["id"])
        st = "✅" if r["status"] == "approved" else "📝"
        title = str(r["title"])[:30]
        rows.append([
            InlineKeyboardButton(f"{st} {title}", callback_data=_cb("view", r_id, revision))
        ])

    rows.append([
        InlineKeyboardButton("➕ Generate New Report", callback_data=_cb("new", class_id, revision)),
        InlineKeyboardButton("⬅ Reports Home", callback_data=_cb("home", class_id, revision)),
    ])

    return InlineKeyboardMarkup(rows)
