from __future__ import annotations

from typing import Any, Sequence
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from evidence_keyboards import b36, un_b36


def evidence_analysis_keyboard(
    analysis_id: int,
    batch_id: int,
    revision: int,
    approved: bool = False,
) -> InlineKeyboardMarkup:
    aid = b36(analysis_id)
    bid = b36(batch_id)
    rev = b36(revision)

    rows: list[list[InlineKeyboardButton]] = []
    if not approved:
        rows.append([
            InlineKeyboardButton("✅ Approve Finding", callback_data=f"v1|ea|appr|{aid}|{bid}|{rev}"),
            InlineKeyboardButton("✏ Edit Summary", callback_data=f"v1|ea|edt|{aid}|{bid}|{rev}"),
        ])
        rows.append([
            InlineKeyboardButton("🔄 Rerun", callback_data=f"v1|ea|anlz|{bid}|{rev}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"v1|ea|rej|{aid}|{bid}|{rev}"),
        ])
    else:
        rows.append([
            InlineKeyboardButton("✏ Edit Approved Summary", callback_data=f"v1|ea|edt|{aid}|{bid}|{rev}"),
        ])

    rows.append([
        InlineKeyboardButton("◀ Back to Batch", callback_data=f"v1|ev|batch|{bid}|{rev}")
    ])
    return InlineKeyboardMarkup(rows)


def evidence_analysis_confirm_reject_keyboard(
    analysis_id: int,
    batch_id: int,
    revision: int,
) -> InlineKeyboardMarkup:
    aid = b36(analysis_id)
    bid = b36(batch_id)
    rev = b36(revision)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ Confirm Reject", callback_data=f"v1|ea|crej|{aid}|{bid}|{rev}"),
            InlineKeyboardButton("◀ Cancel", callback_data=f"v1|ea|v|{aid}|{bid}|{rev}"),
        ]
    ])
