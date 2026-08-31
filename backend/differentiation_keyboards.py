from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _base36(value: int) -> str:
    if value < 0:
        raise ValueError("Callback identifiers cannot be negative.")
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    encoded = ""
    while value:
        value, remainder = divmod(value, 36)
        encoded = alphabet[remainder] + encoded
    return encoded


_ADAP_CODES = {
    "shorter": "sho",
    "longer_plus15": "lon",
    "fast_finisher": "fas",
    "easier_scaffold": "eas",
    "harder_extension": "har",
    "no_tech_low_resource": "not",
    "large_class": "lar",
    "more_communicative": "com",
    "more_exam_focused": "exa",
}

_CODE_TO_ADAP = {v: k for k, v in _ADAP_CODES.items()}


def differentiation_view_keyboard(
    differentiation_id: int,
    source_material_id: int,
    active_tab: str = "sup",
) -> InlineKeyboardMarkup:
    """Keyboard to switch between Support, Core, Challenge, and Delivery Guidance."""
    diff_b36 = _base36(differentiation_id)
    mat_b36 = _base36(source_material_id)

    sup_label = "🟢 Support (Active)" if active_tab == "sup" else "🟢 Support"
    cor_label = "🟡 Core (Active)" if active_tab == "cor" else "🟡 Core"
    cha_label = "🟣 Challenge (Active)" if active_tab == "cha" else "🟣 Challenge"
    gui_label = "📋 Guidance (Active)" if active_tab == "gui" else "📋 Delivery Guidance"

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(sup_label, callback_data=f"v1|df|tab|{diff_b36}|sup"),
                InlineKeyboardButton(cor_label, callback_data=f"v1|df|tab|{diff_b36}|cor"),
            ],
            [
                InlineKeyboardButton(cha_label, callback_data=f"v1|df|tab|{diff_b36}|cha"),
                InlineKeyboardButton(gui_label, callback_data=f"v1|df|tab|{diff_b36}|gui"),
            ],
            [
                InlineKeyboardButton("⚡ Adapt Material", callback_data=f"v1|ad|menu|{mat_b36}"),
                InlineKeyboardButton("⬅ Back to Material", callback_data=f"ma|pk|{source_material_id}"),
            ],
        ]
    )


def adaptations_menu_keyboard(source_material_id: int) -> InlineKeyboardMarkup:
    """Menu of 9 standard classroom adaptations."""
    mat_b36 = _base36(source_material_id)

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⏱ Shorter (25 min)", callback_data=f"v1|ad|gen|{mat_b36}|sho"),
                InlineKeyboardButton("⏳ +15 Min Extension", callback_data=f"v1|ad|gen|{mat_b36}|lon"),
            ],
            [
                InlineKeyboardButton("🚀 Fast Finisher", callback_data=f"v1|ad|gen|{mat_b36}|fas"),
                InlineKeyboardButton("🛟 High Scaffold", callback_data=f"v1|ad|gen|{mat_b36}|eas"),
            ],
            [
                InlineKeyboardButton("🧠 Challenge Route", callback_data=f"v1|ad|gen|{mat_b36}|har"),
                InlineKeyboardButton("📝 Zero-Tech / Paper", callback_data=f"v1|ad|gen|{mat_b36}|not"),
            ],
            [
                InlineKeyboardButton("👥 Large Class (25+)", callback_data=f"v1|ad|gen|{mat_b36}|lar"),
                InlineKeyboardButton("🗣 More Communicative", callback_data=f"v1|ad|gen|{mat_b36}|com"),
            ],
            [
                InlineKeyboardButton("📊 Exam Format (Timed)", callback_data=f"v1|ad|gen|{mat_b36}|exa"),
            ],
            [
                InlineKeyboardButton("⬅ Back to Material", callback_data=f"ma|pk|{source_material_id}"),
            ],
        ]
    )


def adaptation_view_keyboard(
    adaptation_id: int,
    source_material_id: int,
) -> InlineKeyboardMarkup:
    """View adapted material with quick actions."""
    mat_b36 = _base36(source_material_id)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎯 Differentiate", callback_data=f"v1|df|gen|{mat_b36}|sup"),
                InlineKeyboardButton("⚡ Other Adaptations", callback_data=f"v1|ad|menu|{mat_b36}"),
            ],
            [
                InlineKeyboardButton("⬅ Back to Material", callback_data=f"ma|pk|{source_material_id}"),
            ],
        ]
    )
