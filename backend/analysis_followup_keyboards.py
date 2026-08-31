from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from evidence_keyboards import b36, un_b36


ACTION_TYPE_CODES = {
    "ret": "reteach_lesson",
    "ws": "targeted_worksheet",
    "dif": "differentiated_practice",
    "grp": "group_activity",
    "rea": "reassessment",
    "hw": "homework",
}
ACTION_TYPE_REV = {v: k for k, v in ACTION_TYPE_CODES.items()}


def analysis_followup_types_keyboard(
    analysis_id: int, batch_id: int, revision: int
) -> InlineKeyboardMarkup:
    aid = b36(analysis_id)
    bid = b36(batch_id)
    rev = b36(revision)

    rows = [
        [
            InlineKeyboardButton("🧑‍🏫 Reteaching Lesson", callback_data=f"v1|fa|d|{aid}|ret|{bid}|{rev}"),
            InlineKeyboardButton("📝 Targeted Worksheet", callback_data=f"v1|fa|d|{aid}|ws|{bid}|{rev}"),
        ],
        [
            InlineKeyboardButton("🎯 Differentiated Tier", callback_data=f"v1|fa|d|{aid}|dif|{bid}|{rev}"),
            InlineKeyboardButton("👥 Group Activity", callback_data=f"v1|fa|d|{aid}|grp|{bid}|{rev}"),
        ],
        [
            InlineKeyboardButton("📊 Reassessment Check", callback_data=f"v1|fa|d|{aid}|rea|{bid}|{rev}"),
            InlineKeyboardButton("🏠 Homework Task", callback_data=f"v1|fa|d|{aid}|hw|{bid}|{rev}"),
        ],
        [
            InlineKeyboardButton("◀ Back to Analysis", callback_data=f"v1|ea|v|{aid}|{bid}|{rev}")
        ],
    ]
    return InlineKeyboardMarkup(rows)


def analysis_followup_duration_keyboard(
    analysis_id: int, type_code: str, batch_id: int, revision: int
) -> InlineKeyboardMarkup:
    aid = b36(analysis_id)
    bid = b36(batch_id)
    rev = b36(revision)

    rows = [
        [
            InlineKeyboardButton("⏱ 15 Mins", callback_data=f"v1|fa|g|{aid}|{type_code}|15|{bid}|{rev}"),
            InlineKeyboardButton("⏱ 30 Mins", callback_data=f"v1|fa|g|{aid}|{type_code}|30|{bid}|{rev}"),
        ],
        [
            InlineKeyboardButton("⏱ 45 Mins", callback_data=f"v1|fa|g|{aid}|{type_code}|45|{bid}|{rev}"),
            InlineKeyboardButton("⏱ 60 Mins", callback_data=f"v1|fa|g|{aid}|{type_code}|60|{bid}|{rev}"),
        ],
        [
            InlineKeyboardButton("◀ Back to Formats", callback_data=f"v1|fa|t|{aid}|{bid}|{rev}")
        ],
    ]
    return InlineKeyboardMarkup(rows)


def analysis_followup_view_keyboard(
    followup_id: int,
    analysis_id: int,
    batch_id: int,
    material_id: int | None,
    revision: int,
    accepted: bool = False,
) -> InlineKeyboardMarkup:
    fid = b36(followup_id)
    aid = b36(analysis_id)
    bid = b36(batch_id)
    rev = b36(revision)

    rows: list[list[InlineKeyboardButton]] = []
    if not accepted:
        rows.append([
            InlineKeyboardButton("✅ Accept & Adopt", callback_data=f"v1|fa|acc|{fid}|{aid}|{bid}|{rev}")
        ])

    if material_id:
        mid = b36(material_id)
        rows.append([
            InlineKeyboardButton("📚 View in Library", callback_data=f"mat_view_{mid}")
        ])

    rows.append([
        InlineKeyboardButton("◀ Back to Analysis", callback_data=f"v1|ea|v|{aid}|{bid}|{rev}")
    ])
    return InlineKeyboardMarkup(rows)
