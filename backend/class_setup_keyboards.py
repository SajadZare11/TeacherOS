from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _base36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    encoded = ""
    while value:
        value, remainder = divmod(value, 36)
        encoded = alphabet[remainder] + encoded
    return encoded


def cb(action: str, object_id: str, revision: int) -> str:
    return f"v1|cl|{action}|{object_id}|{_base36(revision)}"


def setup_entry_keyboard(*, can_template: bool, has_draft: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_draft:
        rows.append([InlineKeyboardButton("▶ Resume saved draft", callback_data="v1|cl|resume|0|0")])
        rows.append([InlineKeyboardButton("🗑 Discard saved draft", callback_data="v1|cl|discard|0|0")])
    else:
        rows.append([InlineKeyboardButton("➕ Start blank", callback_data="v1|cl|begin|0|0")])
        if can_template:
            rows.append([InlineKeyboardButton("♻ Use my last class as template", callback_data="v1|cl|template|0|0")])
    rows.append([InlineKeyboardButton("⬅ My Classes", callback_data="v1|cl|list|0|0")])
    return InlineKeyboardMarkup(rows)


def typed_step_keyboard(revision: int, *, back_action: str = "back", skip: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if skip:
        rows.append([InlineKeyboardButton("Skip", callback_data=cb("skip", "0", revision))])
    rows.append(
        [
            InlineKeyboardButton("⬅ Back", callback_data=cb(back_action, "0", revision)),
            InlineKeyboardButton("💾 Save Draft", callback_data=cb("draft", "0", revision)),
            InlineKeyboardButton("❌ Cancel", callback_data=cb("cancel", "0", revision)),
        ]
    )
    return InlineKeyboardMarkup(rows)


def choice_keyboard(
    action: str,
    options: tuple[tuple[str, str], ...],
    revision: int,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(label, callback_data=cb(action, code, revision))]
        for code, label in options
    ]
    rows.append(
        [
            InlineKeyboardButton("⬅ Back", callback_data=cb("back", "0", revision)),
            InlineKeyboardButton("💾 Draft", callback_data=cb("draft", "0", revision)),
            InlineKeyboardButton("❌ Cancel", callback_data=cb("cancel", "0", revision)),
        ]
    )
    return InlineKeyboardMarkup(rows)


def multi_keyboard(
    action: str,
    options: tuple[tuple[str, str], ...],
    selected: list[str],
    revision: int,
) -> InlineKeyboardMarkup:
    rows = []
    for code, label in options:
        marker = "✅ " if code in selected else "▫️ "
        rows.append([InlineKeyboardButton(marker + label, callback_data=cb(action, code, revision))])
    rows.append([InlineKeyboardButton("Continue", callback_data=cb("next", "0", revision))])
    rows.append(
        [
            InlineKeyboardButton("⬅ Back", callback_data=cb("back", "0", revision)),
            InlineKeyboardButton("💾 Draft", callback_data=cb("draft", "0", revision)),
            InlineKeyboardButton("❌ Cancel", callback_data=cb("cancel", "0", revision)),
        ]
    )
    return InlineKeyboardMarkup(rows)


def review_keyboard(draft_id: int, revision: int) -> InlineKeyboardMarkup:
    edits = (
        ("name", "Name"), ("level", "Level"), ("age", "Age"),
        ("size", "Size"), ("duration", "Duration"), ("goal", "Goal"),
        ("weak", "Weak areas"), ("book", "Coursebook"),
        ("equipment", "Equipment"), ("preference", "Preference"),
    )
    rows = [
        [InlineKeyboardButton(f"✏ {label}", callback_data=cb("edit", code, revision))]
        for code, label in edits
    ]
    rows.append([InlineKeyboardButton("✅ Create Class", callback_data=cb("save", _base36(draft_id), revision))])
    rows.append(
        [
            InlineKeyboardButton("⬅ Back", callback_data=cb("back", "0", revision)),
            InlineKeyboardButton("💾 Draft", callback_data=cb("draft", "0", revision)),
            InlineKeyboardButton("❌ Cancel", callback_data=cb("cancel", "0", revision)),
        ]
    )
    return InlineKeyboardMarkup(rows)


def cancel_keyboard(revision: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Continue setup", callback_data=cb("resume", "0", revision))],
            [InlineKeyboardButton("💾 Save and finish later", callback_data=cb("draft", "0", revision))],
            [InlineKeyboardButton("🗑 Discard draft", callback_data=cb("discard", "0", revision))],
        ]
    )


def discard_keyboard(revision: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Yes, discard", callback_data=cb("dropyes", "0", revision))],
            [InlineKeyboardButton("Keep draft", callback_data=cb("resume", "0", revision))],
        ]
    )


def saved_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("▶ Resume setup", callback_data="v1|cl|resume|0|0")],
            [InlineKeyboardButton("🏫 My Classes", callback_data="v1|cl|list|0|0")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0")],
        ]
    )
