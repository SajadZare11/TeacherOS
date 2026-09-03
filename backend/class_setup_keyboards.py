from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from string_catalog import tr


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


def cb(action: str, object_id: str, revision: int) -> str:
    return f"v1|cl|{action}|{object_id}|{_base36(revision)}"


def setup_entry_keyboard(*, can_template: bool, has_draft: bool, lang: str = "en") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_draft:
        rows.append([InlineKeyboardButton(tr("btn_resume_draft", lang), callback_data="v1|cl|resume|0|0")])
        rows.append([InlineKeyboardButton(tr("btn_discard_draft", lang), callback_data="v1|cl|discard|0|0")])
    else:
        rows.append([InlineKeyboardButton(tr("btn_fast_setup", lang), callback_data="v1|cl|qbegin|0|0")])
        rows.append([InlineKeyboardButton(tr("btn_detailed_setup", lang), callback_data="v1|cl|begin|0|0")])
        if can_template:
            rows.append([InlineKeyboardButton(tr("btn_use_template", lang), callback_data="v1|cl|template|0|0")])
    rows.append([InlineKeyboardButton(tr("btn_my_classes", lang), callback_data="v1|cl|list|0|0")])
    return InlineKeyboardMarkup(rows)


def typed_step_keyboard(
    revision: int, *, back_action: str = "back", skip: bool = False, lang: str = "en"
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if skip:
        rows.append([InlineKeyboardButton(tr("btn_skip", lang), callback_data=cb("skip", "0", revision))])
    rows.append(
        [
            InlineKeyboardButton(tr("nav_back", lang), callback_data=cb(back_action, "0", revision)),
            InlineKeyboardButton(tr("btn_save_draft", lang), callback_data=cb("draft", "0", revision)),
            InlineKeyboardButton(tr("nav_cancel", lang), callback_data=cb("cancel", "0", revision)),
        ]
    )
    return InlineKeyboardMarkup(rows)


def choice_keyboard(
    action: str,
    options: tuple[tuple[str, str], ...],
    revision: int,
    lang: str = "en",
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(label, callback_data=cb(action, code, revision))]
        for code, label in options
    ]
    rows.append(
        [
            InlineKeyboardButton(tr("nav_back", lang), callback_data=cb("back", "0", revision)),
            InlineKeyboardButton(tr("btn_save_draft", lang), callback_data=cb("draft", "0", revision)),
            InlineKeyboardButton(tr("nav_cancel", lang), callback_data=cb("cancel", "0", revision)),
        ]
    )
    return InlineKeyboardMarkup(rows)


def multi_keyboard(
    action: str,
    options: tuple[tuple[str, str], ...],
    selected: list[str],
    revision: int,
    lang: str = "en",
) -> InlineKeyboardMarkup:
    rows = []
    for code, label in options:
        marker = "✅ " if code in selected else "▫️ "
        rows.append([InlineKeyboardButton(marker + label, callback_data=cb(action, code, revision))])
    rows.append([InlineKeyboardButton(tr("btn_continue", lang), callback_data=cb("next", "0", revision))])
    rows.append(
        [
            InlineKeyboardButton(tr("nav_back", lang), callback_data=cb("back", "0", revision)),
            InlineKeyboardButton(tr("btn_save_draft", lang), callback_data=cb("draft", "0", revision)),
            InlineKeyboardButton(tr("nav_cancel", lang), callback_data=cb("cancel", "0", revision)),
        ]
    )
    return InlineKeyboardMarkup(rows)


def review_keyboard(draft_id: int, revision: int, lang: str = "en") -> InlineKeyboardMarkup:
    edits = (
        ("name", tr("field_name", lang)),
        ("level", tr("field_level", lang)),
        ("age", tr("field_age", lang)),
        ("size", tr("field_size", lang)),
        ("duration", tr("field_duration", lang)),
        ("goal", tr("field_goal", lang)),
        ("weak", tr("field_weak", lang)),
        ("book", tr("field_book", lang)),
        ("equipment", tr("field_equipment", lang)),
        ("preference", tr("field_preference", lang)),
    )
    rows = [
        [InlineKeyboardButton(f"✏ {label}", callback_data=cb("edit", code, revision))]
        for code, label in edits
    ]
    rows.append([InlineKeyboardButton(tr("btn_create_class_confirm", lang), callback_data=cb("save", _base36(draft_id), revision))])
    rows.append(
        [
            InlineKeyboardButton(tr("nav_back", lang), callback_data=cb("back", "0", revision)),
            InlineKeyboardButton(tr("btn_save_draft", lang), callback_data=cb("draft", "0", revision)),
            InlineKeyboardButton(tr("nav_cancel", lang), callback_data=cb("cancel", "0", revision)),
        ]
    )
    return InlineKeyboardMarkup(rows)


def cancel_keyboard(revision: int, lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr("btn_continue_setup", lang), callback_data=cb("resume", "0", revision))],
            [InlineKeyboardButton(tr("btn_save_finish_later", lang), callback_data=cb("draft", "0", revision))],
            [InlineKeyboardButton(tr("btn_discard_draft", lang), callback_data=cb("discard", "0", revision))],
        ]
    )


def discard_keyboard(revision: int, lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr("btn_yes_discard", lang), callback_data=cb("dropyes", "0", revision))],
            [InlineKeyboardButton(tr("btn_keep_draft", lang), callback_data=cb("resume", "0", revision))],
        ]
    )


def saved_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr("btn_resume_setup", lang), callback_data="v1|cl|resume|0|0")],
            [InlineKeyboardButton(tr("btn_my_classes", lang), callback_data="v1|cl|list|0|0")],
            [InlineKeyboardButton(tr("nav_home", lang), callback_data="v1|cl|home|0|0")],
        ]
    )
