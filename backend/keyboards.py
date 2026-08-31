from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from feature_flags import feature_enabled

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

WORKSHEET_TYPE_OPTIONS: dict[str, str] = {
    "vocabulary": "Vocabulary",
    "grammar": "Grammar",
    "reading": "Reading",
    "writing": "Writing",
}

ASSESSMENT_TYPE_OPTIONS: dict[str, str] = {
    "quiz": "Quiz",
    "test": "Test",
    "exam": "Exam",
    "homework": "Homework",
}

QUIZ_FORMAT_OPTIONS: dict[str, str] = {
    "mixed": "Mixed",
    "multiple_choice": "Multiple Choice",
    "fill_blank": "Fill in the Blank",
    "matching": "Matching",
    "true_false": "True / False",
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


def start_menu_keyboard(*, show_admin: bool = False) -> InlineKeyboardMarkup:
    """Return the legacy or class-aware TeacherOS home screen.

    ``show_admin`` remains in the signature for backward compatibility. The owner-only
    Admin button now lives inside Account so the home screen stays uncluttered.
    """
    del show_admin
    if feature_enabled("classes"):
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🏫 My Classes",
                        callback_data="v1|cl|list|0|0",
                    ),
                    InlineKeyboardButton(
                        "⚡ Quick Create",
                        callback_data="home_quick",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔬 Analyze Work",
                        callback_data="home_analyze",
                    ),
                    InlineKeyboardButton("🔎 Search", callback_data="search_start"),
                ],
                [InlineKeyboardButton("👤 Account", callback_data="account_home")],
            ]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📚 Lesson Planner", callback_data="lesson"),
                InlineKeyboardButton("🎲 Activities", callback_data="activity_start"),
            ],
            [
                InlineKeyboardButton("📝 Worksheets", callback_data="worksheet_start"),
                InlineKeyboardButton("✅ Assessments", callback_data="quiz_start"),
            ],
            [
                InlineKeyboardButton("🔎 Search", callback_data="search_start"),
                InlineKeyboardButton("👤 Account", callback_data="account_home"),
            ],
        ]
    )


def quick_create_keyboard() -> InlineKeyboardMarkup:
    """Keep every proven generator callback unchanged under Quick Create."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📚 Lesson Planner", callback_data="lesson"),
                InlineKeyboardButton("🎲 Activities", callback_data="activity_start"),
            ],
            [
                InlineKeyboardButton("📝 Worksheets", callback_data="worksheet_start"),
                InlineKeyboardButton("✅ Assessments", callback_data="quiz_start"),
            ],
            [
                InlineKeyboardButton(
                    "🏠 Main Menu",
                    callback_data="v1|cl|home|0|0",
                )
            ],
        ]
    )


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


def class_list_keyboard(
    classes: list[dict[str, object]],
    *,
    archived: bool,
    has_draft: bool = False,
) -> InlineKeyboardMarkup:
    """Build an owned class list with revisioned compact callbacks."""
    keyboard: list[list[InlineKeyboardButton]] = []
    for class_record in classes:
        class_id = int(class_record["id"])
        revision = int(class_record["revision"])
        name = str(class_record.get("display_name") or "Untitled class").strip()
        label = name if len(name) <= 44 else name[:41].rstrip() + "..."
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🏫 {label}",
                    callback_data=(
                        f"v1|cl|open|{_base36(class_id)}|{_base36(revision)}"
                    ),
                )
            ]
        )
    if archived:
        keyboard.append(
            [InlineKeyboardButton("⬅ Active Classes", callback_data="v1|cl|list|0|0")]
        )
    else:
        keyboard.append(
            [InlineKeyboardButton("☀ Today", callback_data="v1|cl|today|0|0")]
        )
        if has_draft:
            keyboard.append(
                [InlineKeyboardButton("▶ Resume Class Draft", callback_data="v1|cl|resume|0|0")]
            )
        keyboard.append(
            [
                InlineKeyboardButton("➕ Create a Class", callback_data="v1|cl|new|0|0"),
                InlineKeyboardButton(
                    "🗃 Archived",
                    callback_data="v1|cl|archive|0|0",
                ),
            ]
        )
    keyboard.append(
        [
            InlineKeyboardButton("💡 Why Classes?", callback_data="v1|cl|why|0|0"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0"),
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def class_intro_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅ My Classes", callback_data="v1|cl|list|0|0")],
            [InlineKeyboardButton("⚡ Quick Create instead", callback_data="home_quick")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0")],
        ]
    )


def class_detail_keyboard(
    class_id: int,
    revision: int,
    *,
    archived: bool = False,
) -> InlineKeyboardMarkup:
    encoded_id = _base36(class_id)
    encoded_revision = _base36(revision)
    keyboard: list[list[InlineKeyboardButton]] = []
    if not archived:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🔬 Analyze Work for this Class",
                    callback_data=(
                        f"v1|cl|analyze|{encoded_id}|{encoded_revision}"
                    ),
                )
            ]
        )
    keyboard.extend(
        [
            [InlineKeyboardButton("⚡ Quick Create (one-off)", callback_data="home_quick")],
            [
                InlineKeyboardButton("⬅ My Classes", callback_data="v1|cl|list|0|0"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0"),
            ],
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def analyze_picker_keyboard(classes: list[dict[str, object]]) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    for class_record in classes:
        class_id = int(class_record["id"])
        revision = int(class_record["revision"])
        name = str(class_record.get("display_name") or "Untitled class").strip()
        label = name if len(name) <= 40 else name[:37].rstrip() + "..."
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🔬 {label}",
                    callback_data=(
                        f"v1|cl|analyze|{_base36(class_id)}|{_base36(revision)}"
                    ),
                )
            ]
        )
    keyboard.extend(
        [
            [InlineKeyboardButton("🏫 My Classes", callback_data="v1|cl|list|0|0")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0")],
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def class_linked_back_keyboard(class_id: int, revision: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⬅ Back to Class",
                    callback_data=(
                        f"v1|cl|open|{_base36(class_id)}|{_base36(revision)}"
                    ),
                )
            ],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="v1|cl|home|0|0")],
        ]
    )


def class_recovery_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Refresh My Classes", callback_data="v1|cl|list|0|0")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="v1|rc|home|0|0")],
        ]
    )


def account_home_keyboard(*, show_admin: bool = False) -> InlineKeyboardMarkup:
    """Account hub for private user tools and subscription actions."""
    keyboard = [
        [
            InlineKeyboardButton("📊 My Usage", callback_data="usage_show"),
            InlineKeyboardButton("🪪 پلن من", callback_data="account_plan"),
        ],
        [
            InlineKeyboardButton("📁 Library", callback_data="library_start"),
            InlineKeyboardButton("⬆️ ارتقای حساب", callback_data="payment_home"),
        ],
        [
            InlineKeyboardButton("⭐ Rate TeacherOS", callback_data="feedback_start"),
            InlineKeyboardButton("ℹ️ Help & Policies", callback_data="info_home"),
        ],
    ]
    if show_admin:
        keyboard.append([InlineKeyboardButton("🛡 Admin", callback_data="admin_overview")])
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="account_main")])
    return InlineKeyboardMarkup(keyboard)


def launch_info_keyboard(*, compact: bool = False) -> InlineKeyboardMarkup:
    """About, privacy, and terms navigation used at public launch."""
    if compact:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("⬅ Help & Policies", callback_data="info_home")],
                [InlineKeyboardButton("👤 Back to Account", callback_data="info_account")],
            ]
        )
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("ℹ️ About TeacherOS", callback_data="info_about")],
            [
                InlineKeyboardButton("🔐 Privacy", callback_data="info_privacy"),
                InlineKeyboardButton("📄 Terms", callback_data="info_terms"),
            ],
            [InlineKeyboardButton("👤 Back to Account", callback_data="info_account")],
        ]
    )


def feedback_rating_keyboard() -> InlineKeyboardMarkup:
    """Friendly one-tap rating keyboard for fast beta feedback."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "😣 Very frustrating",
                    callback_data="feedback_rating_1",
                )
            ],
            [
                InlineKeyboardButton("😕 Frustrating", callback_data="feedback_rating_2"),
                InlineKeyboardButton("😐 Okay", callback_data="feedback_rating_3"),
            ],
            [
                InlineKeyboardButton("🙂 Good", callback_data="feedback_rating_4"),
                InlineKeyboardButton("🤩 Excellent", callback_data="feedback_rating_5"),
            ],
            [InlineKeyboardButton("Not now", callback_data="feedback_cancel")],
        ]
    )


def feedback_required_text_keyboard() -> InlineKeyboardMarkup:
    """Navigation shown when a very-frustrating rating needs an explanation."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅ Change rating", callback_data="feedback_back_rating")],
            [InlineKeyboardButton("❌ Cancel", callback_data="feedback_cancel")],
        ]
    )


def feedback_optional_text_keyboard() -> InlineKeyboardMarkup:
    """Allow users to finish immediately because the rating is already saved."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Done — no comment", callback_data="feedback_finish")]]
    )


def feedback_done_keyboard(*, allow_comment: bool = False) -> InlineKeyboardMarkup:
    """Finish the flow, with an optional comment only after quick ratings."""
    keyboard = []
    if allow_comment:
        keyboard.append(
            [InlineKeyboardButton("💬 Add optional comment", callback_data="feedback_add_comment")]
        )
    keyboard.append([InlineKeyboardButton("✅ Done", callback_data="feedback_finish")])
    return InlineKeyboardMarkup(keyboard)


def account_plan_keyboard() -> InlineKeyboardMarkup:
    """Actions shown below the user's current subscription details."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 به‌روزرسانی", callback_data="account_plan"),
                InlineKeyboardButton("⬆️ ارتقای حساب", callback_data="payment_home"),
            ],
            [InlineKeyboardButton("⬅ بازگشت به حساب کاربری", callback_data="account_home")],
        ]
    )


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


def lesson_confirm_keyboard(*, class_mode: bool = False) -> InlineKeyboardMarkup:
    override = [[InlineKeyboardButton("✏ ONE-TIME level/duration override", callback_data="lesson_override")]] if class_mode else []
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 Generate Lesson", callback_data="lesson_generate")],
            *override,
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


def activity_confirm_keyboard(*, class_mode: bool = False) -> InlineKeyboardMarkup:
    override = [[InlineKeyboardButton("✏ ONE-TIME level override", callback_data="activity_override")]] if class_mode else []
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 Generate Activity", callback_data="activity_generate")],
            *override,
            [
                InlineKeyboardButton("⬅ Back", callback_data="activity_back_topic"),
                InlineKeyboardButton("❌ Cancel", callback_data="activity_cancel"),
            ],
        ]
    )



def worksheet_type_keyboard() -> InlineKeyboardMarkup:
    icons = {
        "vocabulary": "🔤",
        "grammar": "🧩",
        "reading": "📖",
        "writing": "✍️",
    }
    keyboard = [
        [
            InlineKeyboardButton(
                f"{icons[code]} {label}",
                callback_data=f"worksheet_type_{code}",
            )
        ]
        for code, label in WORKSHEET_TYPE_OPTIONS.items()
    ]
    keyboard.append(
        [
            InlineKeyboardButton("⬅ Back", callback_data="worksheet_back_main"),
            InlineKeyboardButton("❌ Cancel", callback_data="worksheet_cancel"),
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def worksheet_confirm_keyboard(*, class_mode: bool = False) -> InlineKeyboardMarkup:
    override = [[InlineKeyboardButton("✏ ONE-TIME level override", callback_data="worksheet_override")]] if class_mode else []
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🚀 Generate Worksheet",
                    callback_data="worksheet_generate",
                )
            ],
            *override,
            [
                InlineKeyboardButton("⬅ Back", callback_data="worksheet_back_topic"),
                InlineKeyboardButton("❌ Cancel", callback_data="worksheet_cancel"),
            ],
        ]
    )


def quiz_assessment_type_keyboard() -> InlineKeyboardMarkup:
    icons = {
        "quiz": "⚡",
        "test": "📋",
        "exam": "🎓",
        "homework": "🏠",
    }
    keyboard = [
        [
            InlineKeyboardButton(
                f"{icons[code]} {label}",
                callback_data=f"quiz_assessment_{code}",
            )
        ]
        for code, label in ASSESSMENT_TYPE_OPTIONS.items()
    ]
    keyboard.append(
        [
            InlineKeyboardButton("⬅ Back", callback_data="quiz_back_main"),
            InlineKeyboardButton("❌ Cancel", callback_data="quiz_cancel"),
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def quiz_format_keyboard() -> InlineKeyboardMarkup:
    icons = {
        "mixed": "🧰",
        "multiple_choice": "🔘",
        "fill_blank": "✏️",
        "matching": "🔗",
        "true_false": "✅",
    }
    keyboard = [
        [
            InlineKeyboardButton(
                f"{icons[code]} {label}",
                callback_data=f"quiz_format_{code}",
            )
        ]
        for code, label in QUIZ_FORMAT_OPTIONS.items()
    ]
    keyboard.append(
        [
            InlineKeyboardButton(
                "⬅ Back",
                callback_data="quiz_back_assessment_type",
            ),
            InlineKeyboardButton("❌ Cancel", callback_data="quiz_cancel"),
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def quiz_question_count_keyboard() -> InlineKeyboardMarkup:
    """Quick assessment-length choices plus a custom-number option."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("5 questions", callback_data="quiz_count_5"),
                InlineKeyboardButton("10 questions", callback_data="quiz_count_10"),
            ],
            [
                InlineKeyboardButton("15 questions", callback_data="quiz_count_15"),
                InlineKeyboardButton("20 questions", callback_data="quiz_count_20"),
            ],
            [
                InlineKeyboardButton("25 questions", callback_data="quiz_count_25"),
                InlineKeyboardButton("30 questions", callback_data="quiz_count_30"),
            ],
            [
                InlineKeyboardButton(
                    "✍️ Custom number",
                    callback_data="quiz_count_custom",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅ Back",
                    callback_data="quiz_back_question_format",
                ),
                InlineKeyboardButton("❌ Cancel", callback_data="quiz_cancel"),
            ],
        ]
    )


def generated_material_export_keyboard(
    material_id: int, *, material_type: str | None = None, class_id: int | None = None
) -> InlineKeyboardMarkup:
    """Day 10 post-generation toolbar; export callbacks remain backward compatible."""
    actions = [
        InlineKeyboardButton("💾 Save", callback_data=f"ma|sv|{material_id}"),
        InlineKeyboardButton("✏ Adapt", callback_data=f"ma|ad|{material_id}"),
    ]
    extra = []
    if material_type == "lesson" and class_id is not None:
        extra.append([InlineKeyboardButton("➡ Use as Next Lesson", callback_data=f"ma|nx|{material_id}")])
    return InlineKeyboardMarkup(
        [
            actions,
            [
                InlineKeyboardButton(
                    "📄 Download Word",
                    callback_data=f"export_library_{material_id}_all_0",
                ),
                InlineKeyboardButton(
                    "🧾 Download PDF",
                    callback_data=f"pdf_library_{material_id}_all_0",
                ),
            ],
            [
                InlineKeyboardButton("🔁 Regenerate with change", callback_data=f"ma|rg|{material_id}"),
                InlineKeyboardButton("🚩 Report Problem", callback_data=f"ma|rp|{material_id}"),
            ],
            *extra,
            [
                InlineKeyboardButton("📁 Open Library", callback_data="library_start"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="account_main"),
            ],
        ]
    )


def lesson_schedule_keyboard(material_id: int) -> InlineKeyboardMarkup:
    """Day 11 date choices shown after Use as Next Lesson."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Today", callback_data=f"ma|pd|{material_id}|td"),
                InlineKeyboardButton("Tomorrow", callback_data=f"ma|pd|{material_id}|tm"),
            ],
            [
                InlineKeyboardButton("Next class", callback_data=f"ma|pd|{material_id}|nc"),
                InlineKeyboardButton("Later / no date", callback_data=f"ma|pd|{material_id}|lt"),
            ],
            [InlineKeyboardButton("Keep generated only", callback_data=f"ma|pk|{material_id}|na")],
        ]
    )


def lesson_replace_keyboard(material_id: int, date_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(
                "Replace current plan",
                callback_data=f"ma|pr|{material_id}|{date_code}",
            )],
            [InlineKeyboardButton("Keep current plan", callback_data=f"ma|pk|{material_id}|na")],
        ]
    )


def quiz_confirm_keyboard(*, class_mode: bool = False) -> InlineKeyboardMarkup:
    override = [[InlineKeyboardButton("✏ ONE-TIME level override", callback_data="quiz_override")]] if class_mode else []
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🚀 Generate Assessment",
                    callback_data="quiz_generate",
                )
            ],
            *override,
            [
                InlineKeyboardButton("⬅ Back", callback_data="quiz_back_topic"),
                InlineKeyboardButton("❌ Cancel", callback_data="quiz_cancel"),
            ],
        ]
    )


def class_library_keyboard(
    materials: list[dict[str, object]], class_id: int, revision: int
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(str(item["title"])[:48], callback_data=f"library_item_{item['id']}_0")]
        for item in materials[:20]
    ]
    rows.append([InlineKeyboardButton(
        "⬅ Class Home",
        callback_data=f"v1|cl|open|{_base36(class_id)}|{_base36(revision)}",
    )])
    return InlineKeyboardMarkup(rows)

_LIBRARY_FILTER_LABELS: dict[str, str] = {
    "all": "All",
    "lesson": "Lessons",
    "activity": "Activities",
    "worksheet": "Worksheets",
    "assessment": "Assessments",
}

_LIBRARY_TYPE_ICONS: dict[str, str] = {
    "lesson": "📚",
    "activity": "🎲",
    "worksheet": "📝",
    "assessment": "✅",
}


def _short_button_text(value: object, maximum: int = 44) -> str:
    text = " ".join(str(value or "Untitled").split())
    if len(text) <= maximum:
        return text
    return text[: maximum - 1].rstrip() + "…"


def library_list_keyboard(
    materials: list[dict[str, object]],
    *,
    selected_filter: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Build the filter, material, pagination, and main-menu buttons."""
    keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                ("✓ " if selected_filter == "all" else "") + "All",
                callback_data="library_filter_all_0",
            ),
            InlineKeyboardButton(
                ("✓ " if selected_filter == "lesson" else "") + "Lessons",
                callback_data="library_filter_lesson_0",
            ),
        ],
        [
            InlineKeyboardButton(
                ("✓ " if selected_filter == "activity" else "") + "Activities",
                callback_data="library_filter_activity_0",
            ),
            InlineKeyboardButton(
                ("✓ " if selected_filter == "worksheet" else "") + "Worksheets",
                callback_data="library_filter_worksheet_0",
            ),
        ],
        [
            InlineKeyboardButton(
                ("✓ " if selected_filter == "assessment" else "") + "Assessments",
                callback_data="library_filter_assessment_0",
            )
        ],
    ]

    for material in materials:
        material_id = int(material["id"])
        material_type = str(material.get("material_type") or "")
        icon = _LIBRARY_TYPE_ICONS.get(material_type, "📄")
        title = _short_button_text(material.get("title"))
        level = str(material.get("level") or "").strip()
        label = f"{icon} #{material_id}"
        if level:
            label += f" · {level}"
        label += f" · {title}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    label,
                    callback_data=(
                        f"library_item_{material_id}_{selected_filter}_{page}"
                    ),
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                "⬅ Previous",
                callback_data=f"library_page_{selected_filter}_{page - 1}",
            )
        )
    if page + 1 < total_pages:
        navigation.append(
            InlineKeyboardButton(
                "Next ➡",
                callback_data=f"library_page_{selected_filter}_{page + 1}",
            )
        )
    if navigation:
        keyboard.append(navigation)

    keyboard.append(
        [
            InlineKeyboardButton("🔎 Search", callback_data="search_start"),
            InlineKeyboardButton("👤 Account", callback_data="account_home"),
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def library_material_keyboard(
    material_id: int,
    *,
    selected_filter: str,
    page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📄 Word",
                    callback_data=(
                        f"export_library_{material_id}_{selected_filter}_{page}"
                    ),
                ),
                InlineKeyboardButton(
                    "🧾 PDF",
                    callback_data=(
                        f"pdf_library_{material_id}_{selected_filter}_{page}"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    "⬅ Back to Library",
                    callback_data=f"library_page_{selected_filter}_{page}",
                )
            ],
            [
                InlineKeyboardButton(
                    "🗑 Delete",
                    callback_data=(
                        f"library_delete_{material_id}_{selected_filter}_{page}"
                    ),
                ),
                InlineKeyboardButton("👤 Account", callback_data="account_home"),
            ],
        ]
    )


def library_delete_keyboard(
    material_id: int,
    *,
    selected_filter: str,
    page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Yes, delete it",
                    callback_data=(
                        f"library_delete_yes_{material_id}_{selected_filter}_{page}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "No, keep it",
                    callback_data=(
                        f"library_delete_no_{material_id}_{selected_filter}_{page}"
                    ),
                )
            ],
        ]
    )



def search_prompt_keyboard() -> InlineKeyboardMarkup:
    """Navigation shown while TeacherOS waits for a typed search phrase."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⬅ Back to Library", callback_data="library_start"),
                InlineKeyboardButton("❌ Cancel", callback_data="search_cancel"),
            ]
        ]
    )


def search_results_keyboard(
    materials: list[dict[str, object]],
    *,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Build result, pagination, and search-navigation buttons."""
    keyboard: list[list[InlineKeyboardButton]] = []

    for material in materials:
        material_id = int(material["id"])
        material_type = str(material.get("material_type") or "")
        icon = _LIBRARY_TYPE_ICONS.get(material_type, "📄")
        title = _short_button_text(material.get("title"))
        level = str(material.get("level") or "").strip()
        label = f"{icon} #{material_id}"
        if level:
            label += f" · {level}"
        label += f" · {title}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    label,
                    callback_data=f"search_item_{material_id}_{page}",
                )
            ]
        )

    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                "⬅ Previous",
                callback_data=f"search_page_{page - 1}",
            )
        )
    if page + 1 < total_pages:
        navigation.append(
            InlineKeyboardButton(
                "Next ➡",
                callback_data=f"search_page_{page + 1}",
            )
        )
    if navigation:
        keyboard.append(navigation)

    keyboard.extend(
        [
            [InlineKeyboardButton("🔎 New Search", callback_data="search_new")],
            [
                InlineKeyboardButton("📁 Library", callback_data="library_start"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="search_main"),
            ],
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def search_material_keyboard(material_id: int, *, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📄 Word",
                    callback_data=f"export_search_{material_id}_{page}",
                ),
                InlineKeyboardButton(
                    "🧾 PDF",
                    callback_data=f"pdf_search_{material_id}_{page}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⬅ Back to Results",
                    callback_data=f"search_page_{page}",
                )
            ],
            [
                InlineKeyboardButton(
                    "🗑 Delete",
                    callback_data=f"search_delete_{material_id}_{page}",
                ),
                InlineKeyboardButton("🏠 Main Menu", callback_data="search_main"),
            ],
        ]
    )


def search_delete_keyboard(material_id: int, *, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Yes, delete it",
                    callback_data=f"search_delete_yes_{material_id}_{page}",
                )
            ],
            [
                InlineKeyboardButton(
                    "No, keep it",
                    callback_data=f"search_delete_no_{material_id}_{page}",
                )
            ],
        ]
    )


def usage_keyboard() -> InlineKeyboardMarkup:
    """Navigation for the private user usage and plan summary."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="usage_refresh"),
                InlineKeyboardButton("⬆️ ارتقای حساب", callback_data="payment_home"),
            ],
            [
                InlineKeyboardButton("📁 Library", callback_data="library_start"),
                InlineKeyboardButton("👤 Account", callback_data="account_home"),
            ],
        ]
    )


def admin_keyboard(selected_section: str = "overview") -> InlineKeyboardMarkup:
    """Owner-only admin dashboard navigation."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    ("✓ " if selected_section == "overview" else "") + "Overview",
                    callback_data="admin_overview",
                ),
                InlineKeyboardButton(
                    ("✓ " if selected_section == "users" else "") + "Users",
                    callback_data="admin_users",
                ),
            ],
            [
                InlineKeyboardButton(
                    ("✓ " if selected_section == "content" else "") + "Usage",
                    callback_data="admin_content",
                ),
                InlineKeyboardButton(
                    ("✓ " if selected_section == "plans" else "") + "Plans",
                    callback_data="admin_plans",
                ),
            ],
            [
                InlineKeyboardButton(
                    ("✓ " if selected_section == "revenue" else "") + "Revenue",
                    callback_data="admin_revenue",
                ),
                InlineKeyboardButton(
                    ("✓ " if selected_section == "feedback" else "") + "Feedback",
                    callback_data="admin_feedback",
                ),
            ],
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"admin_{selected_section}"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="admin_main"),
            ],
        ]
    )


def admin_feedback_keyboard(items: list[dict[str, object]]) -> InlineKeyboardMarkup:
    """Owner actions for recent beta reports."""
    keyboard: list[list[InlineKeyboardButton]] = []
    for item in items:
        feedback_id = int(item["id"])
        status = str(item.get("status") or "open")
        if status == "open":
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"👀 Review #{feedback_id}",
                        callback_data=f"admin_feedback_reviewed_{feedback_id}",
                    ),
                    InlineKeyboardButton(
                        f"✅ Resolve #{feedback_id}",
                        callback_data=f"admin_feedback_resolved_{feedback_id}",
                    ),
                ]
            )
        elif status == "reviewed":
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"✅ Resolve #{feedback_id}",
                        callback_data=f"admin_feedback_resolved_{feedback_id}",
                    )
                ]
            )

    keyboard.extend(
        [
            [InlineKeyboardButton("🔄 Refresh Feedback", callback_data="admin_feedback")],
            [InlineKeyboardButton("⬅ Admin Dashboard", callback_data="admin_overview")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="admin_main")],
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def payment_home_keyboard(
    *,
    sandbox: bool,
    pro_price: int | None = None,
    premium_price: int | None = None,
) -> InlineKeyboardMarkup:
    """انتخاب پلن و دسترسی به سوابق پرداخت کاربر."""
    pro_label = "⭐ پلن Pro"
    premium_label = "👑 پلن Premium"
    if pro_price is not None:
        pro_label += f" · {pro_price:,} تومان"
    if premium_price is not None:
        premium_label += f" · {premium_price:,} تومان"
    if sandbox:
        pro_label = "🧪 " + pro_label
        premium_label = "🧪 " + premium_label
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(pro_label, callback_data="plan_select_pro")],
            [InlineKeyboardButton(premium_label, callback_data="plan_select_premium")],
            [InlineKeyboardButton("🧾 سوابق پرداخت", callback_data="payment_history")],
            [InlineKeyboardButton("👤 بازگشت به حساب کاربری", callback_data="account_home")],
        ]
    )


def plan_confirmation_keyboard(*, plan_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ ادامه و ورود به درگاه زرین‌پال",
                    callback_data=f"plan_buy_{plan_code}",
                )
            ],
            [InlineKeyboardButton("⬅ بازگشت به پلن‌ها", callback_data="payment_home")],
            [InlineKeyboardButton("👤 حساب کاربری", callback_data="account_home")],
        ]
    )


def subscription_limit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💳 مشاهده و خرید پلن", callback_data="payment_home")],
            [InlineKeyboardButton("👤 حساب کاربری", callback_data="account_home")],
        ]
    )


def payment_ready_keyboard(*, payment_id: int, payment_url: str) -> InlineKeyboardMarkup:
    """باز کردن صفحه پرداخت و بررسی نتیجه تراکنش."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💳 ورود به صفحه پرداخت", url=payment_url)],
            [InlineKeyboardButton("🔄 بررسی وضعیت پرداخت", callback_data=f"payment_status_{payment_id}")],
            [InlineKeyboardButton("🧾 سوابق پرداخت", callback_data="payment_history")],
            [InlineKeyboardButton("⬅ بازگشت به پلن‌ها", callback_data="payment_home")],
        ]
    )


def payment_history_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅ بازگشت به پلن‌ها", callback_data="payment_home")],
            [InlineKeyboardButton("👤 حساب کاربری", callback_data="account_home")],
        ]
    )
