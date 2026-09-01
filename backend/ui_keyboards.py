"""TeacherOS UI Polish Keyboards (Day 24).

Compact, accessible inline keyboards for language switching, first-run walkthroughs,
class search, and pinned favorite materials.
All callback data strings strictly guaranteed <= 64 bytes.
"""
from __future__ import annotations

from typing import Any, Sequence
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from string_catalog import tr


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
    """Construct a standard compact UI callback string."""
    encoded_id = _base36(object_id) if isinstance(object_id, int) else str(object_id)
    return f"v1|ui|{action}|{encoded_id}|{_base36(revision)}"


def language_switcher_keyboard(
    revision: int = 1,
    current_lang: str = "en",
) -> InlineKeyboardMarkup:
    """Language selection keyboard."""
    en_badge = "✓ " if current_lang == "en" else ""
    fa_badge = "✓ " if current_lang == "fa" else ""

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{en_badge}English (EN)", callback_data=_cb("slen", 0, revision)),
            InlineKeyboardButton(f"{fa_badge}فارسی (FA)", callback_data=_cb("slfa", 0, revision)),
        ],
        [
            InlineKeyboardButton("⬅ Back / بازگشت", callback_data="v1|cl|home|0|0"),
        ],
    ])


def onboarding_walkthrough_keyboard(
    step: int,
    revision: int = 1,
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """Compact 3-step first-run walkthrough keyboard."""
    if step == 1:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"{tr('nav_next', lang)} (2/3)", callback_data=_cb("onb2", 0, revision)),
            ],
            [
                InlineKeyboardButton(tr("nav_cancel", lang), callback_data="v1|cl|home|0|0"),
            ],
        ])
    elif step == 2:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(tr("nav_previous", lang), callback_data=_cb("onb1", 0, revision)),
                InlineKeyboardButton(f"{tr('nav_next', lang)} (3/3)", callback_data=_cb("onb3", 0, revision)),
            ],
            [
                InlineKeyboardButton(tr("nav_cancel", lang), callback_data="v1|cl|home|0|0"),
            ],
        ])
    else:  # step 3
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(tr("onboarding_finish_btn", lang), callback_data=_cb("onbdon", 0, revision)),
            ],
            [
                InlineKeyboardButton(tr("nav_previous", lang), callback_data=_cb("onb2", 0, revision)),
            ],
        ])


def pinned_materials_keyboard(
    class_id: int,
    revision: int,
    pinned_items: Sequence[dict[str, Any]],
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """List of pinned/favorite materials in the active class."""
    rows: list[list[InlineKeyboardButton]] = []
    for item in pinned_items[:6]:
        m_id = int(item["id"])
        title = str(item.get("title", "Material"))[:28]
        rows.append([
            InlineKeyboardButton(f"⭐ {title}", callback_data=f"mat_view_{m_id}")
        ])

    rows.append([
        InlineKeyboardButton(tr("nav_back", lang), callback_data=f"v1|cl|open|{_base36(class_id)}|{_base36(revision)}"),
        InlineKeyboardButton(tr("nav_home", lang), callback_data="v1|cl|home|0|0"),
    ])
    return InlineKeyboardMarkup(rows)


def material_pin_toggle_keyboard(
    class_id: int,
    material_id: int,
    revision: int,
    *,
    is_pinned: bool,
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """Action button to pin or unpin a material from class favorites."""
    btn_text = tr("nav_unpin", lang) if is_pinned else tr("nav_pin", lang)
    action = "unpin" if is_pinned else "pin"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(btn_text, callback_data=_cb(action, material_id, revision)),
        ],
        [
            InlineKeyboardButton(tr("nav_back", lang), callback_data=f"v1|cl|open|{_base36(class_id)}|{_base36(revision)}"),
        ],
    ])
