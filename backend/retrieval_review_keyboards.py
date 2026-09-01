"""TeacherOS Retrieval & Spaced-Review Keyboards (Day 20).

Compact, bounded inline keyboards for managing the transparent spaced-retrieval
queue in Telegram. Every callback string is guaranteed <= 64 bytes.
"""
from __future__ import annotations

from typing import Any, Sequence
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from retrieval_review_service import (
    CATEGORY_ICONS,
    CATEGORY_LABELS,
    VALID_CATEGORIES,
)


def _base36(value: int) -> str:
    """Encode an integer to base36 for compact callback payloads."""
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
    """Build a standard compact review callback query."""
    encoded_id = _base36(object_id) if isinstance(object_id, int) else str(object_id)
    return f"v1|rv|{action}|{encoded_id}|{_base36(revision)}"


# ---------------------------------------------------------------------------
# Dashboard & Overview Keyboards
# ---------------------------------------------------------------------------

def review_dashboard_keyboard(
    class_id: int,
    revision: int,
    due_count: int,
    total_count: int,
) -> InlineKeyboardMarkup:
    """Main dashboard keyboard for a class's spaced-review queue."""
    rows: list[list[InlineKeyboardButton]] = []
    
    if due_count > 0:
        rows.append([
            InlineKeyboardButton(
                f"⚡ Start Review Session ({due_count} Due)",
                callback_data=_cb("due", class_id, revision),
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                "✅ Queue Up to Date (No Items Due)",
                callback_data=_cb("due", class_id, revision),
            )
        ])
        
    rows.append([
        InlineKeyboardButton("📋 Browse Queue", callback_data=_cb("q", class_id, revision)),
        InlineKeyboardButton("➕ Add Item", callback_data=_cb("add", class_id, revision)),
    ])
    
    rows.append([
        InlineKeyboardButton("⚙ Interval Schedule", callback_data=_cb("set", class_id, revision)),
        InlineKeyboardButton("📊 Queue Stats", callback_data=_cb("stats", class_id, revision)),
    ])
    
    rows.append([
        InlineKeyboardButton(
            "⬅ Class Home",
            callback_data=f"v1|cl|open|{_base36(class_id)}|{_base36(revision)}",
        ),
        InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0"),
    ])
    
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Interactive Review Session Keyboards
# ---------------------------------------------------------------------------

def due_item_card_keyboard(
    item_id: int,
    class_id: int,
    revision: int,
    *,
    revealed: bool = False,
) -> InlineKeyboardMarkup:
    """Keyboard for reviewing a due item."""
    rows: list[list[InlineKeyboardButton]] = []
    
    if not revealed:
        rows.append([
            InlineKeyboardButton("👀 Show Target Answer", callback_data=_cb("rev", item_id, revision)),
        ])
    else:
        rows.append([
            InlineKeyboardButton("✅ Remembered", callback_data=_cb("rr", item_id, revision)),
            InlineKeyboardButton("◐ Partly", callback_data=_cb("rp", item_id, revision)),
            InlineKeyboardButton("↻ Forgot", callback_data=_cb("rf", item_id, revision)),
        ])
        
    rows.append([
        InlineKeyboardButton("⏰ Snooze", callback_data=_cb("snz", item_id, revision)),
        InlineKeyboardButton("⏸ Pause", callback_data=_cb("ps", item_id, revision)),
        InlineKeyboardButton("🗃 Archive", callback_data=_cb("ar", item_id, revision)),
    ])
    
    rows.append([
        InlineKeyboardButton("⬅ Review Dashboard", callback_data=_cb("home", class_id, revision)),
    ])
    
    return InlineKeyboardMarkup(rows)


def review_result_keyboard(
    item_id: int,
    class_id: int,
    revision: int,
    has_more_due: bool = True,
) -> InlineKeyboardMarkup:
    """Keyboard shown after recording a review outcome."""
    rows: list[list[InlineKeyboardButton]] = []
    
    if has_more_due:
        rows.append([
            InlineKeyboardButton("▶ Next Due Item", callback_data=_cb("due", class_id, revision)),
        ])
        
    rows.append([
        InlineKeyboardButton("📊 Set Confidence", callback_data=_cb("cf", item_id, revision)),
        InlineKeyboardButton("📋 Browse Queue", callback_data=_cb("q", class_id, revision)),
    ])
    
    rows.append([
        InlineKeyboardButton("⬅ Review Dashboard", callback_data=_cb("home", class_id, revision)),
        InlineKeyboardButton(
            "🏫 Class Home",
            callback_data=f"v1|cl|open|{_base36(class_id)}|{_base36(revision)}",
        ),
    ])
    
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Snooze & Confidence Keyboards
# ---------------------------------------------------------------------------

def snooze_picker_keyboard(
    item_id: int,
    class_id: int,
    revision: int,
) -> InlineKeyboardMarkup:
    """Keyboard offering deterministic snooze durations."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("+1 Day", callback_data=_cb("s1", item_id, revision)),
            InlineKeyboardButton("+3 Days", callback_data=_cb("s3", item_id, revision)),
            InlineKeyboardButton("+7 Days", callback_data=_cb("s7", item_id, revision)),
        ],
        [
            InlineKeyboardButton("⬅ Back to Item", callback_data=_cb("it", item_id, revision)),
            InlineKeyboardButton("⬅ Dashboard", callback_data=_cb("home", class_id, revision)),
        ],
    ])


def confidence_picker_keyboard(
    item_id: int,
    class_id: int,
    revision: int,
    current_confidence: str = "medium",
) -> InlineKeyboardMarkup:
    """Teacher confidence tag selector (low/medium/high)."""
    l_mark = "✅ " if current_confidence == "low" else ""
    m_mark = "✅ " if current_confidence == "medium" else ""
    h_mark = "✅ " if current_confidence == "high" else ""
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{l_mark}🟡 Low Confidence", callback_data=_cb("cfl", item_id, revision)),
        ],
        [
            InlineKeyboardButton(f"{m_mark}🟢 Medium Confidence", callback_data=_cb("cfm", item_id, revision)),
        ],
        [
            InlineKeyboardButton(f"{h_mark}🔵 High Confidence", callback_data=_cb("cfh", item_id, revision)),
        ],
        [
            InlineKeyboardButton("⬅ Back to Item", callback_data=_cb("it", item_id, revision)),
            InlineKeyboardButton("⬅ Dashboard", callback_data=_cb("home", class_id, revision)),
        ],
    ])


# ---------------------------------------------------------------------------
# Queue Browser & Pagination Keyboards
# ---------------------------------------------------------------------------

def queue_browser_keyboard(
    class_id: int,
    revision: int,
    items: Sequence[dict[str, Any]],
    page: int,
    total_pages: int,
    current_filter: str = "active",
) -> InlineKeyboardMarkup:
    """Paginated list of review items."""
    rows: list[list[InlineKeyboardButton]] = []
    
    # Filter selection row
    rows.append([
        InlineKeyboardButton(
            ("✓ " if current_filter == "active" else "") + "Active",
            callback_data=_cb("qf", f"1{_base36(class_id)}", revision),
        ),
        InlineKeyboardButton(
            ("✓ " if current_filter == "due" else "") + "Due",
            callback_data=_cb("qf", f"2{_base36(class_id)}", revision),
        ),
        InlineKeyboardButton(
            ("✓ " if current_filter == "paused" else "") + "Paused",
            callback_data=_cb("qf", f"3{_base36(class_id)}", revision),
        ),
        InlineKeyboardButton(
            ("✓ " if current_filter == "all" else "") + "All",
            callback_data=_cb("qf", f"0{_base36(class_id)}", revision),
        ),
    ])
    
    # Individual item buttons
    for it in items:
        item_id = int(it["id"])
        icon = CATEGORY_ICONS.get(it.get("category", ""), "•")
        prompt = str(it.get("prompt_text", ""))[:28]
        due_str = str(it.get("next_review_date", ""))
        label = f"{icon} {prompt} · {due_str}"
        rows.append([
            InlineKeyboardButton(label, callback_data=_cb("it", item_id, revision))
        ])
        
    # Pagination row
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton("⬅ Prev", callback_data=_cb("qp", f"{page - 1}_{_base36(class_id)}", revision))
        )
    if page + 1 < total_pages:
        nav_row.append(
            InlineKeyboardButton("Next ➡", callback_data=_cb("qp", f"{page + 1}_{_base36(class_id)}", revision))
        )
    if nav_row:
        rows.append(nav_row)
        
    rows.append([
        InlineKeyboardButton("➕ Add Item", callback_data=_cb("add", class_id, revision)),
        InlineKeyboardButton("⬅ Dashboard", callback_data=_cb("home", class_id, revision)),
    ])
    
    return InlineKeyboardMarkup(rows)


def queue_item_actions_keyboard(
    item_id: int,
    class_id: int,
    revision: int,
    status: str,
) -> InlineKeyboardMarkup:
    """Action menu for a single item inspected from the queue browser."""
    rows: list[list[InlineKeyboardButton]] = []
    
    # Action row 1: review / resume / pause
    if status == "paused":
        rows.append([
            InlineKeyboardButton("▶ Resume Item", callback_data=_cb("rs", item_id, revision)),
            InlineKeyboardButton("📊 Set Confidence", callback_data=_cb("cf", item_id, revision)),
        ])
    else:
        rows.append([
            InlineKeyboardButton("⚡ Review Now", callback_data=_cb("rev", item_id, revision)),
            InlineKeyboardButton("⏸ Pause", callback_data=_cb("ps", item_id, revision)),
        ])
        
    # Action row 2: snooze / archive
    rows.append([
        InlineKeyboardButton("⏰ Snooze", callback_data=_cb("snz", item_id, revision)),
        InlineKeyboardButton(
            "🗃 Unarchive" if status == "archived" else "🗃 Archive",
            callback_data=_cb("rs" if status == "archived" else "ar", item_id, revision),
        ),
    ])
    
    rows.append([
        InlineKeyboardButton("⬅ Back to Queue", callback_data=_cb("q", class_id, revision)),
        InlineKeyboardButton("⬅ Dashboard", callback_data=_cb("home", class_id, revision)),
    ])
    
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Manual Ingestion / Category Selection Keyboards
# ---------------------------------------------------------------------------

def add_category_keyboard(
    class_id: int,
    revision: int,
) -> InlineKeyboardMarkup:
    """Select category for adding a manual review item."""
    codes = {
        "vocabulary": "vc",
        "grammar": "gr",
        "pronunciation": "pr",
        "functional_language": "fl",
        "common_error": "ce",
        "exam_strategy": "es",
    }
    
    rows: list[list[InlineKeyboardButton]] = []
    cat_items = list(codes.items())
    for i in range(0, len(cat_items), 2):
        row = []
        for cat, code in cat_items[i : i + 2]:
            icon = CATEGORY_ICONS.get(cat, "")
            label = f"{icon} {CATEGORY_LABELS.get(cat, cat.title())}"
            row.append(InlineKeyboardButton(label, callback_data=_cb("acat", f"{code}_{_base36(class_id)}", revision)))
        rows.append(row)
        
    rows.append([
        InlineKeyboardButton("❌ Cancel", callback_data=_cb("acx", class_id, revision)),
        InlineKeyboardButton("⬅ Dashboard", callback_data=_cb("home", class_id, revision)),
    ])
    
    return InlineKeyboardMarkup(rows)


def add_confirm_keyboard(
    class_id: int,
    revision: int,
) -> InlineKeyboardMarkup:
    """Confirm adding the item into the spaced review queue."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Save to Review Queue", callback_data=_cb("aok", class_id, revision)),
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data=_cb("acx", class_id, revision)),
        ],
    ])


# ---------------------------------------------------------------------------
# Settings Keyboards
# ---------------------------------------------------------------------------

def intervals_settings_keyboard(
    class_id: int,
    revision: int,
) -> InlineKeyboardMarkup:
    """Interval schedule settings and reset."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Reset to [2, 7, 21, 45] Days", callback_data=_cb("irst", class_id, revision)),
        ],
        [
            InlineKeyboardButton("⬅ Review Dashboard", callback_data=_cb("home", class_id, revision)),
            InlineKeyboardButton(
                "🏫 Class Home",
                callback_data=f"v1|cl|open|{_base36(class_id)}|{_base36(revision)}",
            ),
        ],
    ])
