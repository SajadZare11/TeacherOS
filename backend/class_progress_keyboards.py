"""TeacherOS Evidence-Linked Class Progress Keyboards (Day 21).

Compact, bounded inline keyboards for managing traceable class objectives,
reviewing AI-extracted proposals, and acting on instructional health cards.
All callbacks strictly guaranteed <= 64 bytes.
"""
from __future__ import annotations

from typing import Any, Sequence
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from class_progress_service import OBJECTIVE_STATUS_LABELS


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
    """Construct a standard compact progress callback string."""
    encoded_id = _base36(object_id) if isinstance(object_id, int) else str(object_id)
    return f"v1|pr|{action}|{encoded_id}|{_base36(revision)}"


# ---------------------------------------------------------------------------
# Overview & Navigation Keyboards
# ---------------------------------------------------------------------------

def progress_overview_keyboard(
    class_id: int,
    revision: int,
    *,
    pending_proposals_count: int = 0,
) -> InlineKeyboardMarkup:
    """Main progress overview keyboard."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("🎯 Class Objectives", callback_data=_cb("objs", class_id, revision)),
            InlineKeyboardButton("🩺 Health Card", callback_data=_cb("hlth", class_id, revision)),
        ]
    ]

    if pending_proposals_count > 0:
        rows.append([
            InlineKeyboardButton(
                f"💡 Proposed Targets ({pending_proposals_count})",
                callback_data=_cb("props", class_id, revision),
            )
        ])

    rows.append([
        InlineKeyboardButton("📜 Evidence Timeline", callback_data=_cb("time", class_id, revision)),
        InlineKeyboardButton("📋 Reports", callback_data=f"v1|rp|home|{_base36(class_id)}|{_base36(revision)}"),
    ])

    rows.append([
        InlineKeyboardButton("⬅ Class Home", callback_data=f"v1|cl|open|{_base36(class_id)}|{_base36(revision)}"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0"),
    ])

    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Objectives List & Status Filter Keyboards
# ---------------------------------------------------------------------------

def objectives_list_keyboard(
    class_id: int,
    revision: int,
    objectives: Sequence[dict[str, Any]],
    current_filter: str = "current",
) -> InlineKeyboardMarkup:
    """List of objectives filtered by status."""
    rows: list[list[InlineKeyboardButton]] = []

    # Filter tabs row
    rows.append([
        InlineKeyboardButton(
            ("✓ " if current_filter == "current" else "") + "Active",
            callback_data=_cb("ofilt", f"1{_base36(class_id)}", revision),
        ),
        InlineKeyboardButton(
            ("✓ " if current_filter == "needs_support" else "") + "Support",
            callback_data=_cb("ofilt", f"2{_base36(class_id)}", revision),
        ),
        InlineKeyboardButton(
            ("✓ " if current_filter == "secure" else "") + "Secure",
            callback_data=_cb("ofilt", f"3{_base36(class_id)}", revision),
        ),
        InlineKeyboardButton(
            ("✓ " if current_filter == "all" else "") + "All",
            callback_data=_cb("ofilt", f"0{_base36(class_id)}", revision),
        ),
    ])

    # Objective items
    for obj in objectives:
        obj_id = int(obj["id"])
        status = obj.get("status", "current")
        icon = "🎯" if status == "current" else ("🟡" if status == "needs_support" else ("✅" if status == "secure" else "⏸"))
        text = str(obj.get("objective", ""))[:30]
        label = f"{icon} {text}"
        rows.append([
            InlineKeyboardButton(label, callback_data=_cb("obj", obj_id, revision))
        ])

    rows.append([
        InlineKeyboardButton("💡 Review Proposed", callback_data=_cb("props", class_id, revision)),
        InlineKeyboardButton("⬅ Progress Home", callback_data=_cb("home", class_id, revision)),
    ])

    return InlineKeyboardMarkup(rows)


def objective_detail_keyboard(
    objective_id: int,
    class_id: int,
    revision: int,
) -> InlineKeyboardMarkup:
    """Actions on a specific objective."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏ Change Status", callback_data=_cb("stask", objective_id, revision)),
            InlineKeyboardButton("🔎 Trace Sources", callback_data=_cb("evsrc", objective_id, revision)),
        ],
        [
            InlineKeyboardButton("⬅ Objectives List", callback_data=_cb("objs", class_id, revision)),
            InlineKeyboardButton("⬅ Progress Home", callback_data=_cb("home", class_id, revision)),
        ],
    ])


def objective_status_picker_keyboard(
    objective_id: int,
    class_id: int,
    revision: int,
    current_status: str = "current",
) -> InlineKeyboardMarkup:
    """Picker to update objective status with teacher judgment."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎯 Set as Active", callback_data=_cb("stact", objective_id, revision)),
            InlineKeyboardButton("🟡 Needs Support", callback_data=_cb("stsup", objective_id, revision)),
        ],
        [
            InlineKeyboardButton("✅ Confirm Secure", callback_data=_cb("stsec", objective_id, revision)),
            InlineKeyboardButton("⏸ Pause", callback_data=_cb("stpau", objective_id, revision)),
        ],
        [
            InlineKeyboardButton("🗃 Archive", callback_data=_cb("starch", objective_id, revision)),
            InlineKeyboardButton("⬅ Cancel", callback_data=_cb("obj", objective_id, revision)),
        ],
    ])


# ---------------------------------------------------------------------------
# Proposed Objectives Approval Queue Keyboards
# ---------------------------------------------------------------------------

def proposed_objectives_keyboard(
    class_id: int,
    revision: int,
    proposals: Sequence[dict[str, Any]],
) -> InlineKeyboardMarkup:
    """List of AI-extracted objective proposals."""
    rows: list[list[InlineKeyboardButton]] = []

    for prop in proposals:
        prop_id = int(prop["id"])
        text = str(prop.get("objective_text", ""))[:32]
        label = f"💡 {text}"
        rows.append([
            InlineKeyboardButton(label, callback_data=_cb("prop", prop_id, revision))
        ])

    rows.append([
        InlineKeyboardButton("🎯 View Active Objectives", callback_data=_cb("objs", class_id, revision)),
        InlineKeyboardButton("⬅ Progress Home", callback_data=_cb("home", class_id, revision)),
    ])

    return InlineKeyboardMarkup(rows)


def proposed_objective_review_keyboard(
    proposal_id: int,
    class_id: int,
    revision: int,
) -> InlineKeyboardMarkup:
    """Approve or reject a single objective proposal."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Adopt as Active Target", callback_data=_cb("apact", proposal_id, revision)),
        ],
        [
            InlineKeyboardButton("🟡 Adopt as Needs Support", callback_data=_cb("apsup", proposal_id, revision)),
        ],
        [
            InlineKeyboardButton("❌ Reject / Dismiss", callback_data=_cb("prej", proposal_id, revision)),
            InlineKeyboardButton("⬅ Back to Proposals", callback_data=_cb("props", class_id, revision)),
        ],
    ])


# ---------------------------------------------------------------------------
# Health Card & Timeline Keyboards
# ---------------------------------------------------------------------------

def health_card_keyboard(
    class_id: int,
    revision: int,
    action_type: str,
    *,
    lesson_id: int | None = None,
) -> InlineKeyboardMarkup:
    """Actionable class health card keyboard."""
    rows: list[list[InlineKeyboardButton]] = []

    if action_type == "review_session":
        rows.append([
            InlineKeyboardButton(
                "⚡ Start Retrieval Session",
                callback_data=f"v1|rv|due|{_base36(class_id)}|{_base36(revision)}",
            )
        ])
    elif action_type == "record_outcome" and lesson_id:
        rows.append([
            InlineKeyboardButton(
                "📝 Record Lesson Outcome",
                callback_data=f"v1|cl|ostart|{_base36(lesson_id)}|{_base36(revision)}",
            )
        ])
    elif action_type in {"plan_lesson", "plan_reteach"}:
        rows.append([
            InlineKeyboardButton(
                "🎯 Plan Next Lesson",
                callback_data=f"v1|cl|plan|{_base36(class_id)}|{_base36(revision)}",
            )
        ])

    rows.append([
        InlineKeyboardButton("🎯 View Objectives", callback_data=_cb("objs", class_id, revision)),
        InlineKeyboardButton("📜 View Timeline", callback_data=_cb("time", class_id, revision)),
    ])

    rows.append([
        InlineKeyboardButton("⬅ Progress Home", callback_data=_cb("home", class_id, revision)),
        InlineKeyboardButton("🏫 Class Home", callback_data=f"v1|cl|open|{_base36(class_id)}|{_base36(revision)}"),
    ])

    return InlineKeyboardMarkup(rows)


def timeline_browser_keyboard(
    class_id: int,
    revision: int,
) -> InlineKeyboardMarkup:
    """Timeline navigation keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎯 Class Objectives", callback_data=_cb("objs", class_id, revision)),
            InlineKeyboardButton("🩺 Health Card", callback_data=_cb("hlth", class_id, revision)),
        ],
        [
            InlineKeyboardButton("⬅ Progress Home", callback_data=_cb("home", class_id, revision)),
            InlineKeyboardButton("🏫 Class Home", callback_data=f"v1|cl|open|{_base36(class_id)}|{_base36(revision)}"),
        ],
    ])
