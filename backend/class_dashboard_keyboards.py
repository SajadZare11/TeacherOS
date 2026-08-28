from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _base36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value < 0:
        raise ValueError("Callback identifiers cannot be negative.")
    if value == 0:
        return "0"
    encoded = ""
    while value:
        value, remainder = divmod(value, 36)
        encoded = alphabet[remainder] + encoded
    return encoded


def _cb(action: str, object_id: int | str, revision: int) -> str:
    encoded_object = _base36(object_id) if isinstance(object_id, int) else object_id
    return f"v1|cl|{action}|{encoded_object}|{_base36(revision)}"


def class_dashboard_keyboard(class_id: int, revision: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎯 Plan Next Lesson", callback_data=_cb("plan", class_id, revision))],
            [
                InlineKeyboardButton("🔬 Analyze Work", callback_data=_cb("analyze", class_id, revision)),
                InlineKeyboardButton("🧰 Create Materials", callback_data=_cb("create", class_id, revision)),
            ],
            [
                InlineKeyboardButton("✅ Record Outcome", callback_data=_cb("outcome", class_id, revision)),
                InlineKeyboardButton("📈 Progress", callback_data=_cb("progress", class_id, revision)),
            ],
            [
                InlineKeyboardButton("📁 Library", callback_data=_cb("library", class_id, revision)),
                InlineKeyboardButton("👤 Profile", callback_data=_cb("profile", class_id, revision)),
            ],
            [InlineKeyboardButton("More details", callback_data=_cb("details", class_id, revision))],
            [
                InlineKeyboardButton("⬅ My Classes", callback_data="v1|cl|list|0|0"),
                InlineKeyboardButton("☀ Today", callback_data="v1|cl|today|0|0"),
            ],
        ]
    )


def archived_dashboard_keyboard(class_id: int, revision: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("♻ Restore Class", callback_data=_cb("restask", class_id, revision))],
            [InlineKeyboardButton("👤 View Profile", callback_data=_cb("profile", class_id, revision))],
            [InlineKeyboardButton("⬅ Archived Classes", callback_data="v1|cl|archive|0|0")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0")],
        ]
    )


def class_details_keyboard(class_id: int, revision: int, *, archived: bool) -> InlineKeyboardMarkup:
    back = _cb("open", class_id, revision)
    rows = [[InlineKeyboardButton("⬅ Class Home", callback_data=back)]]
    if not archived:
        rows.insert(0, [InlineKeyboardButton("👤 Edit Profile", callback_data=_cb("profile", class_id, revision))])
    rows.append([InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0")])
    return InlineKeyboardMarkup(rows)


def class_profile_keyboard(class_id: int, revision: int, *, archived: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not archived:
        fields = (
            ("nm", "Name"), ("lv", "Level"), ("ag", "Age group"),
            ("sz", "Class size"), ("du", "Duration"), ("go", "Goal"),
            ("wk", "Weak areas"), ("bk", "Coursebook"),
            ("eq", "Equipment"), ("pf", "Preference"),
        )
        rows.extend(
            [InlineKeyboardButton(f"✏ {label}", callback_data=_cb("pfedit", code, revision))]
            for code, label in fields
        )
        rows.append(
            [InlineKeyboardButton("🗃 Archive Class", callback_data=_cb("archask", class_id, revision))]
        )
    rows.extend(
        [
            [InlineKeyboardButton("⬅ Class Home", callback_data=_cb("open", class_id, revision))],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0")],
        ]
    )
    return InlineKeyboardMarkup(rows)


def confirmation_keyboard(
    class_id: int, revision: int, *, archive: bool
) -> InlineKeyboardMarkup:
    yes_action = "archyes" if archive else "restyes"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Yes, archive" if archive else "Yes, restore", callback_data=_cb(yes_action, class_id, revision))],
            [InlineKeyboardButton("No, keep current status", callback_data=_cb("open", class_id, revision))],
        ]
    )


def edit_choice_keyboard(
    choices: tuple[tuple[str, str], ...], revision: int
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(label, callback_data=_cb("edset", code, revision))]
        for code, label in choices
    ]
    rows.append([InlineKeyboardButton("⬅ Profile", callback_data=_cb("profile", "0", revision))])
    return InlineKeyboardMarkup(rows)


def edit_multi_keyboard(
    field_code: str,
    choices: tuple[tuple[str, str], ...],
    selected: list[str],
    revision: int,
) -> InlineKeyboardMarkup:
    rows = []
    for code, label in choices:
        marker = "✅ " if code in selected else "▫️ "
        rows.append(
            [InlineKeyboardButton(marker + label, callback_data=_cb("edmulti", field_code + code, revision))]
        )
    rows.append([InlineKeyboardButton("Save this field", callback_data=_cb("edsave", field_code, revision))])
    rows.append([InlineKeyboardButton("⬅ Cancel edit", callback_data=_cb("profile", "0", revision))])
    return InlineKeyboardMarkup(rows)


def edit_text_keyboard(class_id: int, revision: int, *, coursebook: bool) -> InlineKeyboardMarkup:
    rows = []
    if coursebook:
        rows.append([InlineKeyboardButton("Clear / no coursebook", callback_data=_cb("edclear", class_id, revision))])
    rows.append([InlineKeyboardButton("⬅ Cancel edit", callback_data=_cb("profile", class_id, revision))])
    return InlineKeyboardMarkup(rows)


def today_queue_keyboard(items: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    labels = {
        "unfinished_setup": "▶ Finish class setup",
        "missing_outcome": "✅ Record missing outcome",
        "pending_analysis": "🔬 Approve pending analysis",
        "planned_lesson": "📅 Open planned lesson",
        "review_due": "🔁 Review due work",
    }
    actions = {
        "missing_outcome": "outcome",
        "pending_analysis": "analyze",
        "planned_lesson": "open",
        "review_due": "progress",
    }
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        kind = str(item["kind"])
        if kind == "unfinished_setup":
            callback = "v1|cl|resume|0|0"
        else:
            callback = _cb(
                actions[kind], int(item["class_id"]), int(item["revision"])
            )
        class_name = str(item.get("display_name") or "")
        suffix = "" if kind == "unfinished_setup" else f" · {class_name[:24]}"
        rows.append([InlineKeyboardButton(labels[kind] + suffix, callback_data=callback)])
    rows.extend(
        [
            [InlineKeyboardButton("🏫 My Classes", callback_data="v1|cl|list|0|0")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0")],
        ]
    )
    return InlineKeyboardMarkup(rows)


def class_action_keyboard(
    class_id: int, revision: int, action: str, *, class_aware: bool = False
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if action == "plan":
        rows.append([InlineKeyboardButton(
            "Plan with saved class" if class_aware else "Use one-off Lesson Planner",
            callback_data=(f"cg|ls|{class_id:x}|{revision:x}" if class_aware else "lesson"),
        )])
    elif action == "create":
        rows.extend(
            [
                [
                    InlineKeyboardButton("🎲 Activity", callback_data=(f"cg|ac|{class_id:x}|{revision:x}" if class_aware else "activity_start")),
                    InlineKeyboardButton("📝 Worksheet", callback_data=(f"cg|ws|{class_id:x}|{revision:x}" if class_aware else "worksheet_start")),
                ],
                [InlineKeyboardButton("✅ Assessment", callback_data=(f"cg|as|{class_id:x}|{revision:x}" if class_aware else "quiz_start"))],
            ]
        )
    elif action == "library":
        rows.append([InlineKeyboardButton("📁 Open Library", callback_data="library_start")])
    rows.extend(
        [
            [InlineKeyboardButton("⬅ Class Home", callback_data=_cb("open", class_id, revision))],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0")],
        ]
    )
    return InlineKeyboardMarkup(rows)
