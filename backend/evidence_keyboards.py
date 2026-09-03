from __future__ import annotations

from typing import Any, Sequence
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from evidence_service import EVIDENCE_TYPES, EVIDENCE_TYPE_LABELS, RETENTION_POLICIES, RETENTION_LABELS
from string_catalog import tr


def b36(number: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if number == 0:
        return "0"
    digits = []
    n = abs(number)
    while n:
        digits.append(alphabet[n % 36])
        n //= 36
    return "".join(reversed(digits))


def un_b36(text: str) -> int:
    return int(text, 36)


EVIDENCE_TYPE_CODES = {
    "w": "writing",
    "s": "speaking_notes",
    "q": "quiz_exit_ticket",
    "h": "homework_task",
    "g": "general_work",
}
EVIDENCE_TYPE_REV = {v: k for k, v in EVIDENCE_TYPE_CODES.items()}

RETENTION_CODES = {
    "7": "7_days",
    "30": "30_days",
    "u": "until_deleted",
    "m": "manual_only",
}
RETENTION_REV = {v: k for k, v in RETENTION_CODES.items()}


def evidence_inbox_keyboard(
    class_id: int, revision: int, batches: Sequence[dict[str, Any]], lang: str = "en"
) -> InlineKeyboardMarkup:
    cid = b36(class_id)
    rev = b36(revision)
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(tr("btn_submit_evidence", lang), callback_data=f"v1|ev|new|{cid}|{rev}"),
            InlineKeyboardButton(tr("btn_writing_feedback", lang), callback_data=f"v1|wf|start|{cid}|{rev}"),
        ]
    ]

    for batch in batches[:6]:
        bid = b36(int(batch["id"]))
        count = batch.get("active_items", batch.get("item_count", 0))
        etype = EVIDENCE_TYPE_LABELS.get(batch.get("evidence_type", ""), "Evidence")
        date_str = str(batch.get("created_at", ""))[:10]
        btn_text = f"📦 #{batch['id']} · {etype} ({count} items) · {date_str}"
        rows.append([InlineKeyboardButton(btn_text, callback_data=f"v1|ev|batch|{bid}|{rev}")])

    rows.append([
        InlineKeyboardButton(tr("btn_back_to_dashboard", lang), callback_data=f"v1|cl|open|{cid}|{rev}")
    ])
    return InlineKeyboardMarkup(rows)


def evidence_type_keyboard(class_id: int, revision: int) -> InlineKeyboardMarkup:
    cid = b36(class_id)
    rev = b36(revision)
    rows: list[list[InlineKeyboardButton]] = []
    for code, full_type in EVIDENCE_TYPE_CODES.items():
        label = EVIDENCE_TYPE_LABELS.get(full_type, full_type)
        rows.append([
            InlineKeyboardButton(label, callback_data=f"v1|ev|type|{cid}|{code}|{rev}")
        ])
    rows.append([
        InlineKeyboardButton("◀ Cancel", callback_data=f"v1|ev|inbox|{cid}|{rev}")
    ])
    return InlineKeyboardMarkup(rows)


def evidence_retention_keyboard(class_id: int, type_code: str, revision: int) -> InlineKeyboardMarkup:
    cid = b36(class_id)
    rev = b36(revision)
    rows: list[list[InlineKeyboardButton]] = []
    for code, full_ret in RETENTION_CODES.items():
        label = RETENTION_LABELS.get(full_ret, full_ret)
        rows.append([
            InlineKeyboardButton(label, callback_data=f"v1|ev|ret|{cid}|{type_code}|{code}|{rev}")
        ])
    rows.append([
        InlineKeyboardButton("◀ Back", callback_data=f"v1|ev|new|{cid}|{rev}")
    ])
    return InlineKeyboardMarkup(rows)


def evidence_submission_method_keyboard(
    class_id: int, type_code: str, ret_code: str, revision: int
) -> InlineKeyboardMarkup:
    cid = b36(class_id)
    rev = b36(revision)
    rows = [
        [
            InlineKeyboardButton("📝 Paste Text", callback_data=f"v1|ev|subtxt|{cid}|{type_code}|{ret_code}|{rev}"),
            InlineKeyboardButton("📎 Upload File (.txt / .docx)", callback_data=f"v1|ev|subfil|{cid}|{type_code}|{ret_code}|{rev}"),
        ],
        [
            InlineKeyboardButton("◀ Cancel", callback_data=f"v1|ev|inbox|{cid}|{rev}")
        ],
    ]
    return InlineKeyboardMarkup(rows)


def evidence_batch_details_keyboard(
    batch_id: int, class_id: int, revision: int, items: Sequence[dict[str, Any]]
) -> InlineKeyboardMarkup:
    bid = b36(batch_id)
    cid = b36(class_id)
    rev = b36(revision)
    rows: list[list[InlineKeyboardButton]] = []

    for item in items[:8]:
        iid = b36(int(item["id"]))
        label = item.get("student_label", "Student")
        words = item.get("word_count", 0)
        rows.append([
            InlineKeyboardButton(f"👤 {label} ({words} words)", callback_data=f"v1|ev|item|{iid}|{rev}")
        ])

    rows.append([
        InlineKeyboardButton("🔬 Analyze Work", callback_data=f"v1|ea|anlz|{bid}|{rev}"),
        InlineKeyboardButton("🗑 Delete Batch", callback_data=f"v1|ev|delask|{bid}|{rev}"),
    ])
    rows.append([
        InlineKeyboardButton("◀ Evidence Inbox", callback_data=f"v1|ev|inbox|{cid}|{rev}"),
        InlineKeyboardButton("🏠 Dashboard", callback_data=f"v1|cl|open|{cid}|{rev}"),
    ])
    return InlineKeyboardMarkup(rows)


def evidence_item_view_keyboard(
    item_id: int, batch_id: int, revision: int
) -> InlineKeyboardMarkup:
    iid = b36(item_id)
    bid = b36(batch_id)
    rev = b36(revision)
    rows = [
        [
            InlineKeyboardButton("✏ Edit Label", callback_data=f"v1|ev|edlbl|{iid}|{rev}"),
            InlineKeyboardButton("🗑 Delete Item", callback_data=f"v1|ev|delitm|{iid}|{rev}"),
        ],
        [
            InlineKeyboardButton("◀ Back to Batch", callback_data=f"v1|ev|batch|{bid}|{rev}")
        ],
    ]
    return InlineKeyboardMarkup(rows)


def evidence_delete_confirm_keyboard(
    batch_id: int, class_id: int, revision: int
) -> InlineKeyboardMarkup:
    bid = b36(batch_id)
    cid = b36(class_id)
    rev = b36(revision)
    rows = [
        [
            InlineKeyboardButton("⚠️ Yes, Permanently Delete", callback_data=f"v1|ev|delyes|{bid}|{rev}"),
        ],
        [
            InlineKeyboardButton("◀ Keep Batch", callback_data=f"v1|ev|batch|{bid}|{rev}")
        ],
    ]
    return InlineKeyboardMarkup(rows)
