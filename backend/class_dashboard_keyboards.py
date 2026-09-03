from __future__ import annotations

from typing import Any

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


def _cb(action: str, object_id: int | str, revision: int) -> str:
    encoded_object = _base36(object_id) if isinstance(object_id, int) else object_id
    return f"v1|cl|{action}|{encoded_object}|{_base36(revision)}"


def class_dashboard_keyboard(class_id: int, revision: int, lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr("btn_plan_next_lesson", lang), callback_data=_cb("plan", class_id, revision))],
            [
                InlineKeyboardButton(tr("btn_analyze_work", lang), callback_data=_cb("analyze", class_id, revision)),
                InlineKeyboardButton(tr("btn_create_materials", lang), callback_data=_cb("create", class_id, revision)),
            ],
            [
                InlineKeyboardButton(tr("btn_record_outcome", lang), callback_data=_cb("outcome", class_id, revision)),
                InlineKeyboardButton(tr("btn_spaced_review", lang), callback_data=f"v1|rv|home|{_base36(class_id)}|{_base36(revision)}"),
            ],
            [
                InlineKeyboardButton(tr("btn_progress", lang), callback_data=f"v1|pr|home|{_base36(class_id)}|{_base36(revision)}"),
                InlineKeyboardButton(tr("btn_curriculum", lang), callback_data=f"v1|cu|home|{_base36(class_id)}|{_base36(revision)}"),
            ],
            [
                InlineKeyboardButton(tr("btn_class_library", lang), callback_data=_cb("library", class_id, revision)),
                InlineKeyboardButton(tr("btn_class_profile", lang), callback_data=_cb("profile", class_id, revision)),
            ],
            [
                InlineKeyboardButton(tr("btn_differentiate", lang), callback_data=_cb("diff", class_id, revision)),
                InlineKeyboardButton(tr("btn_more_details", lang), callback_data=_cb("details", class_id, revision)),
            ],
            [InlineKeyboardButton(tr("btn_lesson_history", lang), callback_data=_cb("hist", class_id, revision))],
            [InlineKeyboardButton(tr("btn_advanced_tools", lang), callback_data=_cb("adv", class_id, revision))],
            [
                InlineKeyboardButton(tr("btn_my_classes", lang), callback_data="v1|cl|list|0|0"),
                InlineKeyboardButton(tr("btn_today", lang), callback_data="v1|cl|today|0|0"),
            ],
        ]
    )


def class_hub_keyboard(class_id: int, revision: int, lang: str = "en") -> InlineKeyboardMarkup:
    """Clean, friendly 4-pillar dashboard keyboard for a class."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr("hub_cat_class", lang), callback_data=_cb("m_cls", class_id, revision))],
            [InlineKeyboardButton(tr("hub_cat_planning", lang), callback_data=_cb("m_pln", class_id, revision))],
            [InlineKeyboardButton(tr("hub_cat_assessment", lang), callback_data=_cb("m_ass", class_id, revision))],
            [InlineKeyboardButton(tr("hub_cat_tools", lang), callback_data=_cb("m_tls", class_id, revision))],
            [InlineKeyboardButton(tr("btn_my_classes", lang), callback_data="v1|cl|list|0|0")],
        ]
    )


def class_menu_class_keyboard(class_id: int, revision: int, lang: str = "en") -> InlineKeyboardMarkup:
    """Pillar 1: Class & Students."""
    c_b36 = _base36(class_id)
    r_b36 = _base36(revision)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr("btn_my_classes", lang), callback_data="v1|cl|list|0|0")],
            [InlineKeyboardButton(tr("btn_class_students", lang), callback_data=f"v1|st|list|{c_b36}|{r_b36}")],
            [InlineKeyboardButton(tr("btn_class_profile", lang), callback_data=_cb("profile", class_id, revision))],
            [InlineKeyboardButton(tr("btn_record_outcome", lang), callback_data=_cb("outcome", class_id, revision))],
            [InlineKeyboardButton(tr("btn_menu_back", lang), callback_data=_cb("open", class_id, revision))],
        ]
    )


def class_menu_planning_keyboard(class_id: int, revision: int, lang: str = "en") -> InlineKeyboardMarkup:
    """Pillar 2: Planning & Prep."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr("btn_plan_next_lesson", lang), callback_data=_cb("plan", class_id, revision))],
            [InlineKeyboardButton(tr("btn_create_materials", lang), callback_data=_cb("create", class_id, revision))],
            [InlineKeyboardButton(tr("btn_class_library", lang), callback_data=_cb("library", class_id, revision))],
            [InlineKeyboardButton(tr("btn_menu_back", lang), callback_data=_cb("open", class_id, revision))],
        ]
    )


def class_menu_assessment_keyboard(class_id: int, revision: int, lang: str = "en") -> InlineKeyboardMarkup:
    """Pillar 3: Assessment & Feedback."""
    c_b36 = _base36(class_id)
    r_b36 = _base36(revision)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr("btn_analyze_work", lang), callback_data=_cb("analyze", class_id, revision))],
            [InlineKeyboardButton(tr("btn_class_assessments", lang), callback_data=f"v1|ca|list|{c_b36}|{r_b36}")],
            [InlineKeyboardButton(tr("btn_menu_back", lang), callback_data=_cb("open", class_id, revision))],
        ]
    )


def class_menu_tools_keyboard(class_id: int, revision: int, lang: str = "en") -> InlineKeyboardMarkup:
    """Pillar 4: TeacherOS Tools."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr("btn_advanced_tools", lang), callback_data=_cb("adv", class_id, revision))],
            [InlineKeyboardButton(tr("btn_menu_back", lang), callback_data=_cb("open", class_id, revision))],
        ]
    )


def class_advanced_tools_keyboard(class_id: int, revision: int, lang: str = "en") -> InlineKeyboardMarkup:
    """Specialized deep pedagogical tools with clear newbie-friendly explanations."""
    encoded_id = _base36(class_id)
    encoded_rev = _base36(revision)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(tr("btn_adv_diff", lang), callback_data=_cb("diff", class_id, revision)),
                InlineKeyboardButton(tr("btn_adv_review", lang), callback_data=f"v1|rv|home|{encoded_id}|{encoded_rev}"),
            ],
            [
                InlineKeyboardButton(tr("btn_adv_analyze", lang), callback_data=_cb("analyze", class_id, revision)),
                InlineKeyboardButton(tr("btn_adv_curriculum", lang), callback_data=f"v1|cu|home|{encoded_id}|{encoded_rev}"),
            ],
            [
                InlineKeyboardButton(tr("btn_adv_reports", lang), callback_data=f"v1|pr|home|{encoded_id}|{encoded_rev}"),
                InlineKeyboardButton(tr("btn_adv_history", lang), callback_data=_cb("hist", class_id, revision)),
            ],
            [
                InlineKeyboardButton(tr("btn_adv_writing", lang), callback_data=f"v1|wf|home|{encoded_id}|{encoded_rev}"),
                InlineKeyboardButton(tr("btn_more_details", lang), callback_data=_cb("details", class_id, revision)),
            ],
            [InlineKeyboardButton(tr("btn_back_to_class_hub", lang), callback_data=_cb("open", class_id, revision))],
        ]
    )


def archived_dashboard_keyboard(class_id: int, revision: int, lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr("btn_restore_class", lang), callback_data=_cb("restask", class_id, revision))],
            [InlineKeyboardButton(tr("btn_class_profile", lang), callback_data=_cb("profile", class_id, revision))],
            [InlineKeyboardButton(tr("btn_archived_classes", lang), callback_data="v1|cl|archive|0|0")],
            [InlineKeyboardButton(tr("nav_home", lang), callback_data="v1|cl|home|0|0")],
        ]
    )


def class_details_keyboard(class_id: int, revision: int, *, archived: bool, lang: str = "en") -> InlineKeyboardMarkup:
    back = _cb("open", class_id, revision)
    rows = [[InlineKeyboardButton(tr("btn_class_home", lang), callback_data=back)]]
    if not archived:
        rows.insert(0, [InlineKeyboardButton(tr("btn_edit_profile", lang), callback_data=_cb("profile", class_id, revision))])
    rows.append([InlineKeyboardButton(tr("nav_home", lang), callback_data="v1|cl|home|0|0")])
    return InlineKeyboardMarkup(rows)


def class_profile_keyboard(class_id: int, revision: int, *, archived: bool, lang: str = "en") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not archived:
        fields = (
            ("nm", tr("field_name", lang)), ("lv", tr("field_level", lang)), ("ag", tr("field_age", lang)),
            ("sz", tr("field_size", lang)), ("du", tr("field_duration", lang)), ("go", tr("field_goal", lang)),
            ("wk", tr("field_weak", lang)), ("bk", tr("field_book", lang)),
            ("eq", tr("field_equipment", lang)), ("pf", tr("field_preference", lang)),
        )
        rows.extend(
            [InlineKeyboardButton(f"✏ {label}", callback_data=_cb("pfedit", code, revision))]
            for code, label in fields
        )
        rows.append(
            [InlineKeyboardButton(tr("btn_archive_class", lang), callback_data=_cb("archask", class_id, revision))]
        )
    rows.extend(
        [
            [InlineKeyboardButton(tr("btn_class_home", lang), callback_data=_cb("open", class_id, revision))],
            [InlineKeyboardButton(tr("nav_home", lang), callback_data="v1|cl|home|0|0")],
        ]
    )
    return InlineKeyboardMarkup(rows)


def confirmation_keyboard(
    class_id: int, revision: int, *, archive: bool, lang: str = "en"
) -> InlineKeyboardMarkup:
    yes_action = "archyes" if archive else "restyes"
    yes_label = tr("btn_yes_archive", lang) if archive else tr("btn_yes_restore", lang)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(yes_label, callback_data=_cb(yes_action, class_id, revision))],
            [InlineKeyboardButton(tr("btn_no_keep_status", lang), callback_data=_cb("open", class_id, revision))],
        ]
    )


def edit_choice_keyboard(
    choices: tuple[tuple[str, str], ...], revision: int, lang: str = "en"
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(label, callback_data=_cb("edset", code, revision))]
        for code, label in choices
    ]
    rows.append([InlineKeyboardButton(f"⬅ {tr('field_preference', lang)}" if False else f"⬅ {tr('btn_class_profile', lang)}", callback_data=_cb("profile", "0", revision))])
    return InlineKeyboardMarkup(rows)


def edit_multi_keyboard(
    field_code: str,
    choices: tuple[tuple[str, str], ...],
    selected: list[str],
    revision: int,
    lang: str = "en",
) -> InlineKeyboardMarkup:
    rows = []
    for code, label in choices:
        marker = "✅ " if code in selected else "▫️ "
        rows.append(
            [InlineKeyboardButton(marker + label, callback_data=_cb("edmulti", field_code + code, revision))]
        )
    rows.append([InlineKeyboardButton(tr("btn_save_field", lang), callback_data=_cb("edsave", field_code, revision))])
    rows.append([InlineKeyboardButton(tr("btn_cancel_edit", lang), callback_data=_cb("profile", "0", revision))])
    return InlineKeyboardMarkup(rows)


def edit_text_keyboard(class_id: int, revision: int, *, coursebook: bool, lang: str = "en") -> InlineKeyboardMarkup:
    rows = []
    if coursebook:
        rows.append([InlineKeyboardButton(tr("btn_clear_coursebook", lang), callback_data=_cb("edclear", class_id, revision))])
    rows.append([InlineKeyboardButton(tr("btn_cancel_edit", lang), callback_data=_cb("profile", class_id, revision))])
    return InlineKeyboardMarkup(rows)


def today_queue_keyboard(items: list[dict[str, Any]], lang: str = "en") -> InlineKeyboardMarkup:
    if lang == "fa":
        labels = {
            "unfinished_setup": "▶ تکمیل ثبت کلاس",
            "missing_outcome": "✅ ثبت نتیجه تدریس",
            "pending_analysis": "🔬 بررسی تکالیف و شواهد",
            "planned_lesson": "📅 مشاهده درس بعدی",
            "review_due": "🔁 مرور زمان‌بندی‌شده",
        }
    else:
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
        rows.append([InlineKeyboardButton(labels.get(kind, kind) + suffix, callback_data=callback)])
    rows.extend(
        [
            [InlineKeyboardButton(tr("menu_my_classes", lang), callback_data="v1|cl|list|0|0")],
            [InlineKeyboardButton(tr("nav_home", lang), callback_data="v1|cl|home|0|0")],
        ]
    )
    return InlineKeyboardMarkup(rows)


def class_action_keyboard(
    class_id: int, revision: int, action: str, *, class_aware: bool = False, lang: str = "en"
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if action == "plan":
        plan_label = ("طراحی درس بر اساس کلاس" if class_aware else "طراحی درس سریع") if lang == "fa" else ("Plan with saved class" if class_aware else "Use one-off Lesson Planner")
        rows.append([InlineKeyboardButton(
            plan_label,
            callback_data=(f"cg|ls|{class_id:x}|{revision:x}" if class_aware else "lesson"),
        )])
    elif action == "create":
        rows.extend(
            [
                [
                    InlineKeyboardButton(tr("menu_activities", lang), callback_data=(f"cg|ac|{class_id:x}|{revision:x}" if class_aware else "activity_start")),
                    InlineKeyboardButton(tr("menu_worksheets", lang), callback_data=(f"cg|ws|{class_id:x}|{revision:x}" if class_aware else "worksheet_start")),
                ],
                [InlineKeyboardButton(tr("menu_assessments", lang), callback_data=(f"cg|as|{class_id:x}|{revision:x}" if class_aware else "quiz_start"))],
            ]
        )
    elif action == "library":
        rows.append([InlineKeyboardButton(tr("btn_general_library", lang), callback_data="library_start")])
    rows.extend(
        [
            [InlineKeyboardButton(tr("btn_class_home", lang), callback_data=_cb("open", class_id, revision))],
            [InlineKeyboardButton(tr("nav_home", lang), callback_data="v1|cl|home|0|0")],
        ]
    )
    return InlineKeyboardMarkup(rows)


def lesson_history_keyboard(
    lessons: list[dict[str, Any]], class_id: int, revision: int, lang: str = "en"
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for lesson in lessons:
        if lesson.get("lifecycle_state") != "planned":
            continue
        lesson_id = int(lesson["id"])
        taught_label = f"✅ تدریس شد · #{lesson_id}" if lang == "fa" else f"✅ Taught · #{lesson_id}"
        cancel_label = f"✖ لغو طرح · #{lesson_id}" if lang == "fa" else f"✖ Cancel · #{lesson_id}"
        rows.append(
            [
                InlineKeyboardButton(
                    taught_label,
                    callback_data=_cb("taught", lesson_id, revision),
                ),
                InlineKeyboardButton(
                    cancel_label,
                    callback_data=_cb("canask", lesson_id, revision),
                ),
            ]
        )
    rows.extend(
        [
            [InlineKeyboardButton(tr("btn_class_home", lang), callback_data=_cb("open", class_id, revision))],
            [InlineKeyboardButton(tr("nav_home", lang), callback_data="v1|cl|home|0|0")],
        ]
    )
    return InlineKeyboardMarkup(rows)


def lesson_cancel_confirmation_keyboard(
    lesson_id: int, class_id: int, revision: int, lang: str = "en"
) -> InlineKeyboardMarkup:
    yes_label = "بله، این طرح درس لغو شود" if lang == "fa" else "Yes, cancel this plan"
    no_label = "خیر، در برنامه‌ریزی بماند" if lang == "fa" else "No, keep it planned"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(
                yes_label,
                callback_data=_cb("canyes", lesson_id, revision),
            )],
            [InlineKeyboardButton(
                no_label,
                callback_data=_cb("hist", class_id, revision),
            )],
        ]
    )


def outcome_lesson_picker_keyboard(
    lessons: list[dict[str, Any]], class_id: int, revision: int, lang: str = "en"
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for lesson in lessons:
        lesson_id = int(lesson["id"])
        if lesson.get("outcome_id") is None:
            prefix = "ثبت نتیجه" if lang == "fa" else "Record"
            label = f"{prefix} · #{lesson_id} · {str(lesson['title'])[:24]}"
            action = "ostart"
        else:
            prefix = "ویرایش نتیجه" if lang == "fa" else "Correct"
            label = f"{prefix} · #{lesson_id} · {str(lesson['title'])[:23]}"
            action = "oedit"
        rows.append([InlineKeyboardButton(label, callback_data=_cb(action, lesson_id, revision))])
    rows.extend(
        [
            [InlineKeyboardButton(tr("btn_class_home", lang), callback_data=_cb("open", class_id, revision))],
            [InlineKeyboardButton(tr("nav_home", lang), callback_data="v1|cl|home|0|0")],
        ]
    )
    return InlineKeyboardMarkup(rows)


def outcome_result_keyboard(lesson_id: int, revision: int, lang: str = "en") -> InlineKeyboardMarkup:
    lesson = _base36(lesson_id)
    remind_label = tr("btn_outcome_set_reminder", lang)
    skip_label = "رد شدن موقت" if lang == "fa" else "Skip for now"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr("btn_outcome_result_met", lang), callback_data=_cb("ores", "a" + lesson, revision))],
            [InlineKeyboardButton(tr("btn_outcome_result_partly", lang), callback_data=_cb("ores", "p" + lesson, revision))],
            [InlineKeyboardButton(tr("btn_outcome_result_not_met", lang), callback_data=_cb("ores", "r" + lesson, revision))],
            [InlineKeyboardButton(remind_label, callback_data=_cb("oremind", lesson_id, revision))],
            [InlineKeyboardButton(skip_label, callback_data=_cb("oskip", lesson_id, revision))],
        ]
    )


_DIFFICULTY_BUTTONS = (
    ("l", "Language / concept"),
    ("i", "Instructions"),
    ("p", "Pace / time"),
    ("t", "Participation"),
    ("m", "Materials"),
    ("a", "Assessment check"),
)
_DIFFICULTY_BUTTONS_FA = (
    ("l", "مفهوم / زبان"),
    ("i", "شفافیت دستورالعمل"),
    ("p", "مدیریت زمان / سرعت"),
    ("t", "مشارکت زبان‌آموزان"),
    ("m", "محتوا و منابع"),
    ("a", "سنجش و کوئیز"),
)


def outcome_difficulty_keyboard(
    lesson_id: int, result_code: str, mask: int, revision: int, lang: str = "en"
) -> InlineKeyboardMarkup:
    lesson = _base36(lesson_id)
    mask_code = _base36(mask).rjust(2, "0")
    rows: list[list[InlineKeyboardButton]] = []
    diff_buttons = _DIFFICULTY_BUTTONS_FA if lang == "fa" else _DIFFICULTY_BUTTONS
    for index, (code, label) in enumerate(diff_buttons):
        selected = bool(mask & (1 << index))
        rows.append(
            [InlineKeyboardButton(
                ("✅ " if selected else "▫️ ") + label,
                callback_data=_cb("odiff", code + result_code + mask_code + lesson, revision),
            )]
        )
    rows.append([InlineKeyboardButton(
        tr("btn_outcome_no_difficulty", lang), callback_data=_cb("odone", result_code + "00" + lesson, revision)
    )])
    rows.append([InlineKeyboardButton(
        tr("btn_outcome_done_diff", lang), callback_data=_cb("odnext", result_code + mask_code + lesson, revision)
    )])
    back_label = "⬅ بازگشت به نتیجه" if lang == "fa" else "⬅ Result"
    rows.append([InlineKeyboardButton(back_label, callback_data=_cb("ostart", lesson_id, revision))])
    return InlineKeyboardMarkup(rows)


def outcome_completion_keyboard(
    lesson_id: int, result_code: str, mask: int, revision: int, lang: str = "en"
) -> InlineKeyboardMarkup:
    stem = result_code + _base36(mask).rjust(2, "0") + _base36(lesson_id)
    back_label = "⬅ چالش‌ها" if lang == "fa" else "⬅ Difficulties"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr("btn_outcome_comp_completed", lang), callback_data=_cb("ocomp", "c" + stem, revision))],
            [InlineKeyboardButton(tr("btn_outcome_comp_partly", lang), callback_data=_cb("ocomp", "p" + stem, revision))],
            [InlineKeyboardButton(tr("btn_outcome_comp_not", lang), callback_data=_cb("ocomp", "n" + stem, revision))],
            [InlineKeyboardButton(
                back_label,
                callback_data=_cb("odone", result_code + _base36(mask).rjust(2, "0") + _base36(lesson_id), revision),
            )],
        ]
    )


def outcome_summary_keyboard(
    lesson_id: int, class_id: int, revision: int, *, has_note: bool, lang: str = "en"
) -> InlineKeyboardMarkup:
    correct_label = "✏ ویرایش پاسخ‌ها" if lang == "fa" else "✏ Correct answers"
    note_label = ("📝 ویرایش یادداشت" if has_note else "📝 افزودن یادداشت") if lang == "fa" else ("📝 Edit note" if has_note else "📝 Add note")
    done_label = "تایید و بازگشت به کلاس" if lang == "fa" else "Done · Class Home"
    rows = [
        [
            InlineKeyboardButton(correct_label, callback_data=_cb("oedit", lesson_id, revision)),
            InlineKeyboardButton(note_label, callback_data=_cb("onote", lesson_id, revision)),
        ]
    ]
    if has_note:
        rows.append([InlineKeyboardButton(tr("btn_outcome_clear_note", lang), callback_data=_cb("onclear", lesson_id, revision))])
    rows.extend(
        [
            [InlineKeyboardButton(done_label, callback_data=_cb("open", class_id, revision))],
            [InlineKeyboardButton(tr("btn_lesson_history", lang), callback_data=_cb("hist", class_id, revision))],
        ]
    )
    return InlineKeyboardMarkup(rows)


def outcome_note_keyboard(
    lesson_id: int, class_id: int, revision: int, *, has_note: bool, lang: str = "en"
) -> InlineKeyboardMarkup:
    skip_label = "رد شدن از یادداشت / پایان" if lang == "fa" else "Skip note / Done"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(skip_label, callback_data=_cb("oskip", lesson_id, revision))]
    ]
    if has_note:
        rows.append([InlineKeyboardButton(tr("btn_outcome_clear_note", lang), callback_data=_cb("onclear", lesson_id, revision))])
    rows.append([InlineKeyboardButton(tr("btn_class_home", lang), callback_data=_cb("open", class_id, revision))])
    return InlineKeyboardMarkup(rows)


def outcome_reminder_keyboard(lesson_id: int, revision: int, lang: str = "en") -> InlineKeyboardMarkup:
    lesson = _base36(lesson_id)
    rec_now = "ثبت همین حالا" if lang == "fa" else "Record now"
    skip = "رد شدن موقت" if lang == "fa" else "Skip for now"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(tr("btn_remind_1h", lang), callback_data=_cb("orsave", "h" + lesson, revision))],
            [
                InlineKeyboardButton(tr("btn_remind_18", lang), callback_data=_cb("orsave", "e" + lesson, revision)),
                InlineKeyboardButton(tr("btn_remind_20", lang), callback_data=_cb("orsave", "w" + lesson, revision)),
            ],
            [InlineKeyboardButton(tr("btn_remind_tmrw", lang), callback_data=_cb("orsave", "t" + lesson, revision))],
            [InlineKeyboardButton(rec_now, callback_data=_cb("ostart", lesson_id, revision))],
            [InlineKeyboardButton(skip, callback_data=_cb("oskip", lesson_id, revision))],
        ]
    )


_NEXT_LESSON_MODE_CODES = {
    "recommendation": "r",
    "continue_unfinished": "u",
    "reteach": "t",
    "new_topic": "n",
    "assessment": "a",
    "manual": "m",
}
_NEXT_LESSON_PRIO_CODES = {
    "balanced": "b",
    "continuity": "c",
    "reteaching": "r",
    "assessment": "a",
}


def next_lesson_recommendation_keyboard(
    rec: dict[str, Any], class_id: int, revision: int, lang: str = "en"
) -> InlineKeyboardMarkup:
    rec_id = int(rec["id"])
    custom_topic = rec.get("teacher_request")
    mode = rec.get("effective_mode") or rec.get("recommended_mode")
    topic_suffix = ""
    if custom_topic and mode == "manual":
        topic_suffix = f" ({str(custom_topic)[:20]})"
    gen_label = tr("btn_nl_generate", lang) + topic_suffix

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                gen_label,
                callback_data=_cb("nlgen", rec_id, revision),
            )
        ],
        [
            InlineKeyboardButton(tr("btn_nl_custom_topic", lang), callback_data=_cb("nlman", rec_id, revision)),
            InlineKeyboardButton(tr("btn_nl_coursebook", lang), callback_data=_cb("nlmode", rec_id, revision)),
        ],
        [
            InlineKeyboardButton(tr("btn_nl_advanced_settings", lang), callback_data=_cb("nlprio", rec_id, revision)),
        ],
        [
            InlineKeyboardButton(tr("btn_class_home", lang), callback_data=_cb("open", class_id, revision)),
            InlineKeyboardButton(tr("nav_home", lang), callback_data="v1|cl|home|0|0"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def next_lesson_modes_keyboard(
    rec_id: int, current_mode: str | None, revision: int, lang: str = "en"
) -> InlineKeyboardMarkup:
    rec_code = _base36(rec_id)
    if lang == "fa":
        modes = (
            ("recommendation", "🎯 بر اساس پیشنهاد هوشمند"),
            ("continue_unfinished", "🔄 تکمیل مطالب قبلی"),
            ("reteach", "🔁 مرور و بازآموزی چالش‌ها"),
            ("new_topic", "🆕 شروع مبحث جدید"),
            ("assessment", "📝 آمادگی برای سنجش"),
        )
    else:
        modes = (
            ("recommendation", "🎯 Use recommendation"),
            ("continue_unfinished", "🔄 Continue unfinished work"),
            ("reteach", "🔁 Reteach with support"),
            ("new_topic", "🆕 Start a new topic"),
            ("assessment", "📝 Prepare for assessment"),
        )
    rows: list[list[InlineKeyboardButton]] = []
    for mode_key, label in modes:
        code = _NEXT_LESSON_MODE_CODES[mode_key]
        prefix = "✅ " if current_mode == mode_key else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"{prefix}{label}",
                    callback_data=_cb("nlmset", f"{code}{rec_code}", revision),
                )
            ]
        )
    prefix_m = "✅ " if current_mode == "manual" else ""
    manual_label = f"{prefix_m}✏ انتخاب دستی موضوع آزاد" if lang == "fa" else f"{prefix_m}✏ Choose manually (custom topic)"
    back_label = "⬅ بازگشت به برنامه درس" if lang == "fa" else "⬅ Back to Plan"
    rows.append(
        [
            InlineKeyboardButton(
                manual_label,
                callback_data=_cb("nlman", rec_id, revision),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                back_label,
                callback_data=_cb("nlrec", rec_id, revision),
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def next_lesson_priorities_keyboard(
    rec_id: int, current_priority: str, revision: int, lang: str = "en"
) -> InlineKeyboardMarkup:
    rec_code = _base36(rec_id)
    if lang == "fa":
        priorities = (
            ("balanced", "⚖ بهینه و متعادل (خودکار)"),
            ("continuity", "🔄 اولویت با پیوستگی درس‌ها"),
            ("reteaching", "🔁 اولویت با رفع چالش‌ها"),
            ("assessment", "📝 اولویت با سنجش و ارزیابی"),
        )
    else:
        priorities = (
            ("balanced", "⚖ Balanced (Auto)"),
            ("continuity", "🔄 Continuity first"),
            ("reteaching", "🔁 Reteaching first"),
            ("assessment", "📝 Assessment first"),
        )
    rows: list[list[InlineKeyboardButton]] = []
    for prio_key, label in priorities:
        code = _NEXT_LESSON_PRIO_CODES[prio_key]
        prefix = "✅ " if current_priority == prio_key else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"{prefix}{label}",
                    callback_data=_cb("nlpset", f"{code}{rec_code}", revision),
                )
            ]
        )
    back_label = "⬅ بازگشت به برنامه درس" if lang == "fa" else "⬅ Back to Plan"
    rows.append(
        [
            InlineKeyboardButton(
                back_label,
                callback_data=_cb("nlrec", rec_id, revision),
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def next_lesson_sources_keyboard(
    rec_id: int, sources: list[dict[str, Any]], revision: int, lang: str = "en"
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for source in sources:
        source_id = int(source["id"])
        included = int(source.get("included", 1)) == 1
        label = ("✅ " if included else "▫️ ") + str(source.get("source_label", "Source"))[:36]
        rows.append(
            [
                InlineKeyboardButton(
                    label,
                    callback_data=_cb("nltog", source_id, revision),
                )
            ]
        )
    back_label = "⬅ بازگشت به برنامه درس" if lang == "fa" else "⬅ Back to Plan"
    rows.append(
        [
            InlineKeyboardButton(
                back_label,
                callback_data=_cb("nlrec", rec_id, revision),
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def next_lesson_why_keyboard(rec_id: int, revision: int, lang: str = "en") -> InlineKeyboardMarkup:
    back_label = "⬅ بازگشت به برنامه درس" if lang == "fa" else "⬅ Back to Plan"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    back_label,
                    callback_data=_cb("nlrec", rec_id, revision),
                )
            ]
        ]
    )


def next_lesson_followup_keyboard(
    plan_id: int, class_id: int, revision: int, lang: str = "en"
) -> InlineKeyboardMarkup:
    yes_label = "👍 بله، مناسب است" if lang == "fa" else "👍 Yes, addresses target"
    no_label = "👎 نه چندان" if lang == "fa" else "👎 Not quite"
    done_label = "تایید · بازگشت به کلاس" if lang == "fa" else "Done · Class Home"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    yes_label,
                    callback_data=_cb("nlfa", f"1{_base36(plan_id)}", revision),
                ),
                InlineKeyboardButton(
                    no_label,
                    callback_data=_cb("nlfa", f"0{_base36(plan_id)}", revision),
                ),
            ],
            [
                InlineKeyboardButton(
                    done_label,
                    callback_data=_cb("open", class_id, revision),
                )
            ],
        ]
    )

