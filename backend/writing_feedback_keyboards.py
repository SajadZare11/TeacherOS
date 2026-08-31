from __future__ import annotations

from typing import Any, Sequence
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from evidence_keyboards import b36, un_b36


MODE_CODES = {
    "l": "light",
    "b": "balanced",
    "d": "detailed",
    "r": "rubric",
}
MODE_REV = {v: k for k, v in MODE_CODES.items()}


def writing_feedback_mode_keyboard(
    class_id: int | None, revision: int
) -> InlineKeyboardMarkup:
    cid_str = b36(class_id) if class_id is not None else "0"
    rev = b36(revision)
    rows = [
        [
            InlineKeyboardButton("⚡ Light (Encouraging)", callback_data=f"v1|wf|m|{cid_str}|l|{rev}"),
            InlineKeyboardButton("⚖️ Balanced (Default)", callback_data=f"v1|wf|m|{cid_str}|b|{rev}"),
        ],
        [
            InlineKeyboardButton("🔬 Detailed Diagnostic", callback_data=f"v1|wf|m|{cid_str}|d|{rev}"),
            InlineKeyboardButton("📊 Rubric Assessment", callback_data=f"v1|wf|m|{cid_str}|r|{rev}"),
        ],
    ]
    if class_id is not None:
        rows.append([InlineKeyboardButton("◀ Dashboard", callback_data=f"v1|cl|open|{cid_str}|{rev}")])
    else:
        rows.append([InlineKeyboardButton("◀ Main Menu", callback_data="menu_start")])
    return InlineKeyboardMarkup(rows)


def writing_feedback_view_keyboard(
    feedback_id: int,
    class_id: int | None,
    revision: int,
    approved: bool = False,
) -> InlineKeyboardMarkup:
    fid = b36(feedback_id)
    cid_str = b36(class_id) if class_id is not None else "0"
    rev = b36(revision)

    rows: list[list[InlineKeyboardButton]] = []
    if not approved:
        rows.append([
            InlineKeyboardButton("✅ Approve Feedback", callback_data=f"v1|wf|appr|{fid}|{cid_str}|{rev}"),
            InlineKeyboardButton("✏ Edit Comments", callback_data=f"v1|wf|edt|{fid}|{cid_str}|{rev}"),
        ])
    else:
        rows.append([
            InlineKeyboardButton("✏ Edit Comments", callback_data=f"v1|wf|edt|{fid}|{cid_str}|{rev}"),
        ])

    rows.append([
        InlineKeyboardButton("📤 Export Copies (.docx / .pdf)", callback_data=f"v1|wf|exp|{fid}|{cid_str}|{rev}")
    ])

    if class_id is not None:
        rows.append([InlineKeyboardButton("◀ Dashboard", callback_data=f"v1|cl|open|{cid_str}|{rev}")])
    else:
        rows.append([InlineKeyboardButton("◀ Main Menu", callback_data="menu_start")])

    return InlineKeyboardMarkup(rows)


def writing_feedback_export_keyboard(
    feedback_id: int,
    class_id: int | None,
    revision: int,
) -> InlineKeyboardMarkup:
    fid = b36(feedback_id)
    cid_str = b36(class_id) if class_id is not None else "0"
    rev = b36(revision)

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📄 Student Copy (.docx)", callback_data=f"v1|wf|expw|{fid}|s|{cid_str}|{rev}"),
            InlineKeyboardButton("📑 Student Copy (.pdf)", callback_data=f"v1|wf|expp|{fid}|s|{cid_str}|{rev}"),
        ],
        [
            InlineKeyboardButton("📋 Teacher Diagnostic (.docx)", callback_data=f"v1|wf|expw|{fid}|t|{cid_str}|{rev}"),
            InlineKeyboardButton("📋 Teacher Diagnostic (.pdf)", callback_data=f"v1|wf|expp|{fid}|t|{cid_str}|{rev}"),
        ],
        [
            InlineKeyboardButton("◀ Back to Feedback", callback_data=f"v1|wf|v|{fid}|{cid_str}|{rev}")
        ],
    ])
