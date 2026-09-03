from __future__ import annotations

from typing import Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from string_catalog import tr


def _b36(val: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    res = ""
    while val:
        val, rem = divmod(val, 36)
        res = alphabet[rem] + res
    return res or "0"


def class_students_list_keyboard(
    class_id: int, revision: int, students: list[dict[str, Any]], lang: str = "fa"
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    # 1. Student buttons (2 per row)
    student_row: list[InlineKeyboardButton] = []
    for st in students:
        s_id = int(st["id"])
        name = str(st["full_name"])
        student_row.append(
            InlineKeyboardButton(f"👤 {name}", callback_data=f"v1|st|hub|{_b36(s_id)}|{_b36(class_id)}")
        )
        if len(student_row) == 2:
            rows.append(student_row)
            student_row = []
    if student_row:
        rows.append(student_row)

    # 2. Add student button
    add_lbl = "➕ افزودن دانش‌آموز جدید" if lang == "fa" else "➕ Add New Student"
    rows.append([InlineKeyboardButton(add_lbl, callback_data=f"v1|st|add|{_b36(class_id)}|{_b36(revision)}")])

    # 3. Back to Class
    back_lbl = "⬅️ بازگشت به صفحه اصلی کلاس" if lang == "fa" else "⬅️ Back to Class"
    rows.append([InlineKeyboardButton(back_lbl, callback_data=f"v1|cl|open|{_b36(class_id)}|{_b36(revision)}")])
    return InlineKeyboardMarkup(rows)


def student_hub_keyboard(
    student_id: int, class_id: int, revision: int = 1, lang: str = "fa"
) -> InlineKeyboardMarkup:
    s_b36 = _b36(student_id)
    c_b36 = _b36(class_id)
    r_b36 = _b36(revision)

    if lang == "fa":
        lbl_cat1 = "📋 ۱. پروفایل و هویت (Profile)"
        lbl_cat2 = "⚡ ۲. وضعیت فعلی و مهارت‌ها (Current State)"
        lbl_cat3 = "📈 ۳. سوابق، آزمون‌ها و پیشرفت (History & Progress)"
        lbl_ai = "🤖 پیشنهاد هوشمند گام بعدی (AI Co-Teacher)"
        lbl_back = "⬅️ لیست دانش‌آموزان"
    else:
        lbl_cat1 = "📋 1. Profile & Identity"
        lbl_cat2 = "⚡ 2. Current State & Skills"
        lbl_cat3 = "📈 3. History, Assessments & Progress"
        lbl_ai = "🤖 AI Next-Step Recommendation"
        lbl_back = "⬅️ Students List"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(lbl_cat1, callback_data=f"v1|st|cat1|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_cat2, callback_data=f"v1|st|cat2|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_cat3, callback_data=f"v1|st|cat3|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_ai, callback_data=f"v1|st|ai|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_back, callback_data=f"v1|st|list|{c_b36}|{r_b36}")],
    ])


def student_category1_keyboard(student_id: int, class_id: int, lang: str = "fa") -> InlineKeyboardMarkup:
    """Category 1: Profile (Sections 1, 2, 3, 4)."""
    s_b36 = _b36(student_id)
    c_b36 = _b36(class_id)

    if lang == "fa":
        lbl_s1 = "👤 بخش ۱: هویت (نام، سن، زبان مادری)"
        lbl_s2 = "📊 بخش ۲: سطوح CEFR و اعتمادبه‌نفس (۷ مهارت)"
        lbl_s3 = "🎯 بخش ۳: اهداف بلندمدت و کوتاه‌مدت"
        lbl_s4 = "🧩 بخش ۴: ترجیحات و رفتارهای یادگیری"
        lbl_back = "⬅️ بازگشت به پرونده دانش‌آموز"
    else:
        lbl_s1 = "👤 Section 1: Student Identity"
        lbl_s2 = "📊 Section 2: CEFR & Confidence (7 Skills)"
        lbl_s3 = "🎯 Section 3: Long & Short-term Goals"
        lbl_s4 = "🧩 Section 4: Preferences & Behaviors"
        lbl_back = "⬅️ Back to Student Hub"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(lbl_s1, callback_data=f"v1|st|s1|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_s2, callback_data=f"v1|st|s2|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_s3, callback_data=f"v1|st|s3|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_s4, callback_data=f"v1|st|s4|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_back, callback_data=f"v1|st|hub|{s_b36}|{c_b36}")],
    ])


def student_category2_keyboard(student_id: int, class_id: int, lang: str = "fa") -> InlineKeyboardMarkup:
    """Category 2: Current State (Sections 5, 6, 7, 10b)."""
    s_b36 = _b36(student_id)
    c_b36 = _b36(class_id)

    if lang == "fa":
        lbl_s5 = "🌟 بخش ۵: نقاط قوت (میانگین نمرات بالای ۱۰)"
        lbl_s6 = "⚠️ بخش ۶: نقاط نیازمند تقویت (زیر ۱۰ + یادداشت)"
        lbl_s7 = "📝 بخش ۷: پروفایل خطاهای زبانی"
        lbl_s10b = "🧘 بخش ۱۰ب: اعتمادبه‌نفس مهارتی و ابعاد انگیزه"
        lbl_rate = "➕ ثبت نمره مهارت‌های این جلسه (از ۲۰)"
        lbl_add_err = "➕ ثبت خطای زبانی جدید"
        lbl_back = "⬅️ بازگشت به پرونده دانش‌آموز"
    else:
        lbl_s5 = "🌟 Section 5: Strengths (Mean Scores >= 10)"
        lbl_s6 = "⚠️ Section 6: Areas for Development (< 10)"
        lbl_s7 = "📝 Section 7: Error Profile"
        lbl_s10b = "🧘 Section 10b: Confidence & Motivation"
        lbl_rate = "➕ Score Skills for Today's Session (0-20)"
        lbl_add_err = "➕ Log a Language Error"
        lbl_back = "⬅️ Back to Student Hub"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(lbl_rate, callback_data=f"v1|st|rate|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_s5, callback_data=f"v1|st|s5|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_s6, callback_data=f"v1|st|s6|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_add_err, callback_data=f"v1|st|adderr|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_s7, callback_data=f"v1|st|s7|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_s10b, callback_data=f"v1|st|s10b|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_back, callback_data=f"v1|st|hub|{s_b36}|{c_b36}")],
    ])


def student_category3_keyboard(student_id: int, class_id: int, lang: str = "fa") -> InlineKeyboardMarkup:
    """Category 3: History & Progress (Sections 8, 9, 10a, 11)."""
    s_b36 = _b36(student_id)
    c_b36 = _b36(class_id)

    if lang == "fa":
        lbl_s8 = "📑 بخش ۸: نتایج آزمون‌های کلاسی (رسمی و غیررسمی)"
        lbl_s9 = "📈 بخش ۹: روند طولی پیشرفت مهارت‌ها"
        lbl_s10a = "🤝 بخش ۱۰الف: تعامل، انگیزه و نظم کلاسی"
        lbl_ai = "🤖 بخش ۱۱: پیشنهاد هوشمند گام بعدی (AI)"
        lbl_back = "⬅️ بازگشت به پرونده دانش‌آموز"
    else:
        lbl_s8 = "📑 Section 8: Assessment Results"
        lbl_s9 = "📈 Section 9: Longitudinal Skill Progress"
        lbl_s10a = "🤝 Section 10a: Engagement & Interaction"
        lbl_ai = "🤖 Section 11: AI Next Step Recommendation"
        lbl_back = "⬅️ Back to Student Hub"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(lbl_s8, callback_data=f"v1|st|s8|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_s9, callback_data=f"v1|st|s9|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_s10a, callback_data=f"v1|st|s10a|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_ai, callback_data=f"v1|st|ai|{s_b36}|{c_b36}")],
        [InlineKeyboardButton(lbl_back, callback_data=f"v1|st|hub|{s_b36}|{c_b36}")],
    ])


def class_assessments_keyboard(
    class_id: int, revision: int, assessments: list[dict[str, Any]], lang: str = "fa"
) -> InlineKeyboardMarkup:
    c_b36 = _b36(class_id)
    r_b36 = _b36(revision)
    rows: list[list[InlineKeyboardButton]] = []

    # New formal & informal buttons
    if lang == "fa":
        lbl_add_formal = "➕ آزمون رسمی (فاینال، آیلتس، میدترم)"
        lbl_add_informal = "➕ ارزیابی غیررسمی (کوییز، تسک، نمونه کار)"
        lbl_back = "⬅️ بازگشت به صفحه اصلی کلاس"
    else:
        lbl_add_formal = "➕ Formal Assessment (Final, IELTS, Midterm)"
        lbl_add_informal = "➕ Informal Assessment (Quiz, Task, Observation)"
        lbl_back = "⬅️ Back to Class"

    rows.append([InlineKeyboardButton(lbl_add_formal, callback_data=f"v1|ca|add_f|{c_b36}|{r_b36}")])
    rows.append([InlineKeyboardButton(lbl_add_informal, callback_data=f"v1|ca|add_inf|{c_b36}|{r_b36}")])

    # List of existing assessments
    for a in assessments[:6]:
        a_id = int(a["id"])
        title = str(a["title"])
        a_type = "رسمی" if a["assessment_type"] == "formal" else "غیررسمی"
        if lang != "fa":
            a_type = "Formal" if a["assessment_type"] == "formal" else "Informal"
        rows.append([
            InlineKeyboardButton(
                f"📝 [{a_type}] {title}",
                callback_data=f"v1|ca|view|{_b36(a_id)}|{c_b36}",
            )
        ])

    rows.append([InlineKeyboardButton(lbl_back, callback_data=f"v1|cl|open|{c_b36}|{r_b36}")])
    return InlineKeyboardMarkup(rows)
