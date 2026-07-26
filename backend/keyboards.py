from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

GRAMMAR_OPTIONS: dict[str, str] = {
    "present_simple": "Present Simple",
    "present_continuous": "Present Continuous",
    "present_perfect": "Present Perfect",
    "present_perfect_continuous": "Present Perfect Continuous",
    "past_simple": "Past Simple",
    "past_continuous": "Past Continuous",
    "past_perfect": "Past Perfect",
    "past_perfect_continuous": "Past Perfect Continuous",
    "future_will": "Future Simple (Will)",
    "going_to": "Be Going To",
    "present_continuous_future": "Present Continuous (Future)",
    "future_continuous": "Future Continuous",
    "future_perfect": "Future Perfect",
    "modals": "Modals",
    "passive_voice": "Passive Voice",
    "reported_speech": "Reported Speech",
    "conditionals": "Conditionals",
    "relative_clauses": "Relative Clauses",
    "gerunds_infinitives": "Gerunds & Infinitives",
    "articles": "Articles",
    "prepositions": "Prepositions",
    "none": "None",
}

ACTIVITY_TYPE_OPTIONS: dict[str, str] = {
    "speaking": "Speaking",
    "role_play": "Role Play",
    "debate": "Debate",
    "pair_work": "Pair Work",
    "group_work": "Group Work",
    "information_gap": "Information Gap",
    "icebreaker": "Icebreaker",
}


def start_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("📚 Lesson Planner", callback_data="lesson"),
            InlineKeyboardButton("🎲 Activities", callback_data="activity_start"),
        ],
        [
            InlineKeyboardButton("📝 Worksheets", callback_data="menu_worksheets"),
            InlineKeyboardButton("✅ Assessments", callback_data="menu_assessments"),
        ],
        [
            InlineKeyboardButton("📁 Library", callback_data="menu_library"),
            InlineKeyboardButton("👤 Account", callback_data="menu_account"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def back_cancel_keyboard(back_callback: str, cancel_callback: str) -> InlineKeyboardMarkup:
    """Reusable navigation row for steps that require typed text."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⬅ Back", callback_data=back_callback),
                InlineKeyboardButton("❌ Cancel", callback_data=cancel_callback),
            ]
        ]
    )


def level_keyboard(
    flow: str,
    back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    levels = ("A1", "A2", "B1", "B2", "C1", "C2")
    keyboard = [
        [
            InlineKeyboardButton(levels[index], callback_data=f"{flow}_level_{levels[index]}"),
            InlineKeyboardButton(
                levels[index + 1],
                callback_data=f"{flow}_level_{levels[index + 1]}",
            ),
        ]
        for index in range(0, len(levels), 2)
    ]

    if back_callback is not None:
        keyboard.append(
            [
                InlineKeyboardButton("⬅ Back", callback_data=back_callback),
                InlineKeyboardButton("❌ Cancel", callback_data=f"{flow}_cancel"),
            ]
        )

    return InlineKeyboardMarkup(keyboard)


def grammar_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"lesson_grammar_{code}")]
        for code, label in GRAMMAR_OPTIONS.items()
    ]
    keyboard[-1][0] = InlineKeyboardButton(
        "Skip Grammar",
        callback_data="lesson_grammar_none",
    )
    keyboard.append(
        [
            InlineKeyboardButton("⬅ Back", callback_data="lesson_back_topic"),
            InlineKeyboardButton("❌ Cancel", callback_data="lesson_cancel"),
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def duration_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(f"{minutes} min", callback_data=f"lesson_duration_{minutes}")]
        for minutes in (30, 45, 60, 90)
    ]
    keyboard.append(
        [
            InlineKeyboardButton("⬅ Back", callback_data="lesson_back_grammar"),
            InlineKeyboardButton("❌ Cancel", callback_data="lesson_cancel"),
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def lesson_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 Generate Lesson", callback_data="lesson_generate")],
            [
                InlineKeyboardButton("⬅ Back", callback_data="lesson_back_duration"),
                InlineKeyboardButton("❌ Cancel", callback_data="lesson_cancel"),
            ],
        ]
    )


def activity_type_keyboard() -> InlineKeyboardMarkup:
    icons = {
        "speaking": "🗣",
        "role_play": "🎭",
        "debate": "⚖",
        "pair_work": "👥",
        "group_work": "👨‍👩‍👧",
        "information_gap": "🧩",
        "icebreaker": "❄",
    }
    keyboard = [
        [
            InlineKeyboardButton(
                f"{icons[code]} {label}",
                callback_data=f"activity_type_{code}",
            )
        ]
        for code, label in ACTIVITY_TYPE_OPTIONS.items()
    ]
    keyboard.append(
        [
            InlineKeyboardButton("⬅ Back", callback_data="activity_back_main"),
            InlineKeyboardButton("❌ Cancel", callback_data="activity_cancel"),
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def activity_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 Generate Activity", callback_data="activity_generate")],
            [
                InlineKeyboardButton("⬅ Back", callback_data="activity_back_topic"),
                InlineKeyboardButton("❌ Cancel", callback_data="activity_cancel"),
            ],
        ]
    )
