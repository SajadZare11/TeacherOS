from __future__ import annotations

import logging
import re
from typing import Any

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from class_service import list_classes
from class_dashboard_keyboards import class_dashboard_keyboard, class_hub_keyboard
from class_setup_keyboards import (
    cancel_keyboard,
    choice_keyboard,
    discard_keyboard,
    multi_keyboard,
    review_keyboard,
    saved_keyboard,
    setup_entry_keyboard,
    typed_step_keyboard,
)
from class_setup_service import (
    ClassLimitReachedError,
    complete_setup,
    discard_setup_draft,
    get_setup_draft,
    save_setup_draft,
    start_setup_draft,
)
from keyboards import class_recovery_keyboard
from ui_service import resolve_lang


logger = logging.getLogger(__name__)
SETUP_ACTIONS = {
    "new", "begin", "qbegin", "template", "resume", "back", "skip", "level", "age",
    "size", "duration", "goal", "weak", "equip", "prefer", "next", "edit",
    "save", "draft", "cancel", "discard", "dropyes",
}

LEVELS = (
    ("a1", "🌱 A1 · Beginner"),
    ("a2", "🚶 A2 · Elementary"),
    ("b1", "🗣️ B1 · Intermediate"),
    ("b2", "💪 B2 · Upper-Intermediate"),
    ("c1", "🎓 C1 · Advanced"),
    ("c2", "🏆 C2 · Mastery"),
    ("ns", "🤔 Not sure yet"),
)
AGES = (("yl", "Young learners"), ("teen", "Teens"), ("adult", "Adults"), ("mixed", "Mixed"), ("ns", "Not sure"))
SIZES = (("one", "One-to-one"), ("small", "2-5 learners"), ("medium", "6-12 learners"), ("large", "13-20 learners"), ("xlarge", "21+ learners"), ("ns", "Not sure"))
DURATIONS = (("30", "30 minutes"), ("45", "45 minutes"), ("60", "60 minutes"), ("90", "90 minutes"), ("ns", "Not sure"))
GOALS = (("general", "General English"), ("speaking", "Conversation"), ("exam", "Exam preparation"), ("business", "Business English"), ("academic", "Academic English"), ("travel", "Travel English"))
WEAK = (("spk", "Speaking"), ("lst", "Listening"), ("read", "Reading"), ("write", "Writing"), ("gram", "Grammar"), ("vocab", "Vocabulary"), ("pron", "Pronunciation"), ("ns", "Not sure"))
EQUIPMENT = (("board", "Board"), ("proj", "Projector"), ("audio", "Speakers/audio"), ("print", "Printer"), ("net", "Internet"), ("none", "None"), ("ns", "Not sure"))
PREFERENCES = (("comm", "Communicative"), ("struct", "Structured"), ("task", "Task-based"), ("game", "Games and interaction"), ("exam", "Exam-focused"), ("balanced", "Balanced"), ("ns", "Not sure"))
CHOICE_LABELS = {
    "weak_areas": dict(WEAK),
    "equipment": dict(EQUIPMENT),
    "teaching_preferences": dict(PREFERENCES),
}

LEVELS_FA = (
    ("a1", "🌱 A1 · مبتدی"),
    ("a2", "🚶 A2 · پایه"),
    ("b1", "🗣️ B1 · متوسط"),
    ("b2", "💪 B2 · فوق متوسط"),
    ("c1", "🎓 C1 · پیشرفته"),
    ("c2", "🏆 C2 · تسلط کامل"),
    ("ns", "🤔 مطمئن نیستم"),
)
AGES_FA = (("yl", "کودکان"), ("teen", "نوجوانان"), ("adult", "بزرگسالان"), ("mixed", "سنین مختلف"), ("ns", "مطمئن نیستم"))
SIZES_FA = (("one", "تک‌نفره (خصوصی)"), ("small", "۲ تا ۵ نفر"), ("medium", "۶ تا ۱۲ نفر"), ("large", "۱۳ تا ۲۰ نفر"), ("xlarge", "بیش از ۲۱ نفر"), ("ns", "مطمئن نیستم"))
DURATIONS_FA = (("30", "۳۰ دقیقه"), ("45", "۴۵ دقیقه"), ("60", "۶۰ دقیقه"), ("90", "۹۰ دقیقه"), ("ns", "مطمئن نیستم"))
GOALS_FA = (("general", "انگلیسی عمومی"), ("speaking", "مکالمه و گفت‌وگو"), ("exam", "آمادگی آزمون"), ("business", "انگلیسی تجاری"), ("academic", "انگلیسی آکادمیک"), ("travel", "انگلیسی سفر"))
WEAK_FA = (("spk", "مکالمه (Speaking)"), ("lst", "شنیداری (Listening)"), ("read", "خواندن (Reading)"), ("write", "نوشتاری (Writing)"), ("gram", "گرامر"), ("vocab", "واژگان"), ("pron", "تلفظ"), ("ns", "مطمئن نیستم"))
EQUIPMENT_FA = (("board", "تخته و ماژیک"), ("proj", "ویدئو پروژکتور"), ("audio", "اسپیکر / صوت"), ("print", "پرینتر"), ("net", "اینترنت کلاسی"), ("none", "هیچ‌کدام"), ("ns", "مطمئن نیستم"))
PREFERENCES_FA = (("comm", "ارتباط‌محور (مکالمه)"), ("struct", "ساختاریافته و منظم"), ("task", "تمرین و تکلیف‌محور"), ("game", "بازی و تعاملی"), ("exam", "آزمون‌محور و نکته‌ای"), ("balanced", "متعادل و ترکیبی"), ("ns", "مطمئن نیستم"))

CHOICE_LABELS_FA = {
    "weak_areas": dict(WEAK_FA),
    "equipment": dict(EQUIPMENT_FA),
    "teaching_preferences": dict(PREFERENCES_FA),
}


def _options(name: str, lang: str = "en") -> tuple[tuple[str, str], ...]:
    if lang == "fa":
        if name == "level": return LEVELS_FA
        if name == "age": return AGES_FA
        if name == "size": return SIZES_FA
        if name == "duration": return DURATIONS_FA
        if name == "goal": return GOALS_FA
        if name == "weak": return WEAK_FA
        if name in {"equipment", "equip"}: return EQUIPMENT_FA
        if name in {"preference", "prefer"}: return PREFERENCES_FA
    if name == "level": return LEVELS
    if name == "age": return AGES
    if name == "size": return SIZES
    if name == "duration": return DURATIONS
    if name == "goal": return GOALS
    if name == "weak": return WEAK
    if name in {"equipment", "equip"}: return EQUIPMENT
    if name in {"preference", "prefer"}: return PREFERENCES
    return ()

VALUE_MAPS = {
    "level": {"a1": "A1", "a2": "A2", "b1": "B1", "b2": "B2", "c1": "C1", "c2": "C2", "ns": "not_sure"},
    "age": {"yl": "young_learners", "teen": "teens", "adult": "adults", "mixed": "mixed", "ns": "not_sure"},
    "size": {"one": "one_to_one", "small": "2_5", "medium": "6_12", "large": "13_20", "xlarge": "21_plus", "ns": "not_sure"},
    "duration": {"30": 30, "45": 45, "60": 60, "90": 90, "ns": "not_sure"},
    "goal": {"general": "general_english", "speaking": "conversation", "exam": "exam_preparation", "business": "business_english", "academic": "academic_english", "travel": "travel_english"},
    "weak": {code: code for code, _ in WEAK},
    "equip": {code: code for code, _ in EQUIPMENT},
    "prefer": {code: code for code, _ in PREFERENCES},
}
FIELD_FOR_ACTION = {"level": "level_choice", "age": "age_group_choice", "size": "learner_count_band_choice", "duration": "duration_choice", "goal": "goal_choice"}
NEXT_STEP = {"name": "level", "level": "age", "age": "size", "size": "duration", "duration": "goal", "goal": "weak", "weak": "book", "book": "equipment", "equipment": "preference", "preference": "review"}
PREVIOUS_STEP = {value: key for key, value in NEXT_STEP.items()}
EDIT_CODES = {"name": "name", "level": "level", "age": "age", "size": "size", "duration": "duration", "goal": "goal", "weak": "weak", "book": "book", "equipment": "equipment", "preference": "preference"}


async def _safe_edit(query: Any, text: str, markup: Any) -> None:
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


def _revision(text: str) -> int:
    return int(text, 36)


def _screen(draft: dict[str, Any], lang: str = "en") -> tuple[str, Any]:
    step = draft["step"]
    rev = int(draft["revision"])
    p = draft["payload"]
    if lang == "fa":
        if step == "name":
            if p.get("fast_setup"):
                return (
                    "⚡ راه‌اندازی سریع (گام ۱ از ۲) · نام کلاس 🏫\n\n"
                    "لطفاً یک نام مشخص یا خودمانی برای کلاستان تایپ و ارسال کنید:\n"
                    "(مثلاً: «بزرگسالان پنجشنبه»، «IELTS خصوصی سارا»، «کلاس نوجوانان B1»)\n\n"
                    "💡 نکته: برای حفظ حریم خصوصی، نیازی به ثبت نام واقعی زبان‌آموزان نیست.",
                    typed_step_keyboard(rev, lang=lang),
                )
            return (
                "۱/۱۰ · نام یا عنوان کلاس 🏫\n\n"
                "لطفاً یک نام مشخص و کوتاه برای کلاستان تایپ کنید (مثلاً: «مکالمه بزرگسال پنجشنبه‌ها» یا «IELTS عصر»).\n\n"
                "💡 نکته: برای حفظ حریم خصوصی، نیازی به ثبت نام واقعی زبان‌آموزان نیست.",
                typed_step_keyboard(rev, lang=lang),
            )
        if step == "level":
            if p.get("fast_setup"):
                return (
                    "⚡ راه‌اندازی سریع (گام ۲ از ۲) · سطح زبان‌آموزان 🎯\n\n"
                    "سطح تقریبی زبان‌آموزان این کلاس را انتخاب کنید تا دستیار شما محتوا را متناسب با سطح آن‌ها تنظیم کند:",
                    choice_keyboard("level", _options("level", lang), rev, lang=lang),
                )
            return (
                "۲/۱۰ · سطح زبان‌آموزان (CEFR) 🎯\n\n"
                "سطح زبان‌آموزان این کلاس را مشخص کنید تا محتوا و تمرینات دقیقاً متناسب با سطح آن‌ها تنظیم شوند.\n"
                "اگر مطمئن نیستید، «مطمئن نیستم» را انتخاب کنید.",
                choice_keyboard("level", _options("level", lang), rev, lang=lang),
            )
        if step == "age":
            return (
                "۳/۱۰ · رده سنی زبان‌آموزان 👥\n\n"
                "رده سنی به دستیار هوشمند کمک می‌کند لحن آموزش و سبک بازی‌های کلاسی را جذاب‌تر انتخاب کند.",
                choice_keyboard("age", _options("age", lang), rev, lang=lang),
            )
        if step == "size":
            return (
                "۴/۱۰ · تعداد تقریبی زبان‌آموزان 📊\n\n"
                "تعداد زبان‌آموزان به تنظیم تمرین‌های انفرادی، دونفره (Pair work) یا گروهی کمک می‌کند.",
                choice_keyboard("size", _options("size", lang), rev, lang=lang),
            )
        if step == "duration":
            return (
                "۵/۱۰ · مدت زمان معمول هر جلسه ⏱️\n\n"
                "مدت زمان جلسه را انتخاب کنید تا زمان‌بندی بخش‌های مختلف طرح درس واقع‌بینانه باشد.",
                choice_keyboard("duration", _options("duration", lang), rev, lang=lang),
            )
        if step == "goal":
            return (
                "۶/۱۰ · هدف اصلی آموزشی 🌟\n\n"
                "تمرکز اصلی این دوره چیست؟ این هدف باعث می‌شود مطالب تولیدی همواره هم‌راستا باقی بمانند.",
                choice_keyboard("goal", _options("goal", lang), rev, lang=lang),
            )
        if step == "weak":
            return (
                "۷/۱۰ · مهارت‌های نیازمند تمرین بیشتر 📝\n\n"
                "مهارت‌هایی که زبان‌آموزان در آن‌ها به تمرین و مرور بیشتری نیاز دارند را انتخاب کرده و سپس «ادامه» را بزنید.",
                multi_keyboard("weak", _options("weak", lang), list(p.get("weak_areas", [])), rev, lang=lang),
            )
        if step == "book":
            return (
                "۸/۱۰ · کتاب درسی و سرفصل (اختیاری) 📚\n\n"
                "نام کتاب و درس جاری را تایپ کنید (مثلاً: American English File 2 | Unit 3) یا دکمه «رد شدن» را بزنید.",
                typed_step_keyboard(rev, skip=True, lang=lang),
            )
        if step == "equipment":
            return (
                "۹/۱۰ · امکانات و تجهیزات کلاس 🛠️\n\n"
                "امکاناتی که معمولاً در کلاس در دسترس دارید را علامت بزنید و «ادامه» را انتخاب کنید.",
                multi_keyboard("equip", _options("equipment", lang), list(p.get("equipment", [])), rev, lang=lang),
            )
        if step == "preference":
            return (
                "۱۰/۱۰ · روش تدریس مورد علاقه شما 💡\n\n"
                "سبک‌های تدریسی که بیشتر می‌پسندید را انتخاب کنید تا دستیار هوشمند پیشنهادات را با سلیقه شما هماهنگ کند.",
                multi_keyboard("prefer", _options("preference", lang), list(p.get("teaching_preferences", [])), rev, lang=lang),
            )
        return (_review_text(p, lang=lang), review_keyboard(int(draft["id"]), rev, lang=lang))

    if step == "name":
        if p.get("fast_setup"):
            return (
                "⚡ Quick Setup (Step 1 of 2) · Class Nickname 🏫\n\n"
                "Type a friendly nickname for this class and send it:\n"
                "(e.g., 'Mon/Wed Teens', 'Saturday Morning Kids', 'IELTS Private - Sara')\n\n"
                "💡 Tip: To protect privacy, no need to enter real student names.",
                typed_step_keyboard(rev, lang=lang),
            )
        return (
            "1/10 · Private class label\n\nType one short label, such as ‘B1 Evening’. "
            "It helps you recognize the class. Do not enter student names or sensitive information.",
            typed_step_keyboard(rev, lang=lang),
        )
    if step == "level":
        if p.get("fast_setup"):
            return (
                "⚡ Quick Setup (Step 2 of 2) · Class Level 🎯\n\n"
                "Choose the approximate CEFR level for this class so lessons fit your learners:",
                choice_keyboard("level", LEVELS, rev, lang=lang),
            )
        return ("2/10 · CEFR level\n\nLevel helps TeacherOS control language difficulty. Choose Not sure rather than guessing.", choice_keyboard("level", LEVELS, rev, lang=lang))
    if step == "age":
        return ("3/10 · Age group\n\nAn age band improves activity style. Do not enter birthdays or learner profiles.", choice_keyboard("age", AGES, rev, lang=lang))
    if step == "size":
        return ("4/10 · Class-size range\n\nA range helps TeacherOS choose pair, group, or individual work.", choice_keyboard("size", SIZES, rev, lang=lang))
    if step == "duration":
        return ("5/10 · Usual lesson duration\n\nDuration keeps plans realistic. Choose Not sure if lessons vary.", choice_keyboard("duration", DURATIONS, rev, lang=lang))
    if step == "goal":
        return ("6/10 · Main goal\n\nThe main goal keeps future resources focused.", choice_keyboard("goal", GOALS, rev, lang=lang))
    if step == "weak":
        return ("7/10 · Weak areas\n\nSelect any areas that often need practice, then Continue. Use Not sure instead of guessing.", multi_keyboard("weak", WEAK, list(p.get("weak_areas", [])), rev, lang=lang))
    if step == "book":
        return ("8/10 · Coursebook and unit (optional)\n\nType a short phrase like ‘English File | Unit 4’, or Skip. This aligns future work with your syllabus. Do not enter student data.", typed_step_keyboard(rev, skip=True, lang=lang))
    if step == "equipment":
        return ("9/10 · Available equipment\n\nSelect what is normally available, then Continue. This prevents unusable activity suggestions.", multi_keyboard("equip", EQUIPMENT, list(p.get("equipment", [])), rev, lang=lang))
    if step == "preference":
        return ("10/10 · Teaching preference\n\nSelect the styles you prefer, then Continue. TeacherOS uses these as preferences, not assumptions.", multi_keyboard("prefer", PREFERENCES, list(p.get("teaching_preferences", [])), rev, lang=lang))
    return (_review_text(p, lang=lang), review_keyboard(int(draft["id"]), rev, lang=lang))


def _display(value: Any, lang: str = "en") -> str:
    if value in {None, "not_sure"}:
        return "مطمئن نیستم" if lang == "fa" else "Not sure"
    if lang == "fa":
        val_map = {
            "young_learners": "کودکان", "teens": "نوجوانان", "adults": "بزرگسالان", "mixed": "سنین مختلف",
            "one_to_one": "تک‌نفره (خصوصی)", "2_5": "۲ تا ۵ نفر", "6_12": "۶ تا ۱۲ نفر",
            "13_20": "۱۳ تا ۲۰ نفر", "21_plus": "بیش از ۲۱ نفر",
            "general_english": "انگلیسی عمومی", "conversation": "مکالمه و گفت‌وگو",
            "exam_preparation": "آمادگی آزمون", "business_english": "انگلیسی تجاری",
            "academic_english": "انگلیسی آکادمیک", "travel_english": "انگلیسی سفر",
        }
        if str(value) in val_map:
            return val_map[str(value)]
    return str(value).replace("_", " ").title()


def _display_choices(field: str, value: Any, lang: str = "en") -> str:
    if not isinstance(value, list) or not value:
        return "ثبت نشده" if lang == "fa" else "Missing"
    labels = CHOICE_LABELS_FA[field] if lang == "fa" else CHOICE_LABELS[field]
    return ", ".join(labels.get(str(item), _display(item, lang=lang)) for item in value)


def _review_text(p: dict[str, Any], lang: str = "en") -> str:
    if p.get("fast_setup"):
        if lang == "fa":
            return "\n".join(
                [
                    "⚡ راه‌اندازی سریع آماده است! 🎉",
                    "",
                    f"🏫 نام کلاس: {p.get('display_name', 'ثبت نشده')}",
                    f"🎯 سطح: {_display(p.get('level_choice'), lang=lang)}",
                    "⏱️ مشخصات پیش‌فرض: ۶۰ دقیقه · انگلیسی عمومی · بزرگسالان",
                    "",
                    "با لمس دکمه «✅ ساخت و ثبت کلاس» در زیر، کلاس شما فعال می‌شود و می‌توانید بلافاصله شروع به طرح درس کنید ✨",
                    "",
                    "💡 نکته: مشخصات تکمیلی مثل کتاب و امکانات کلاس را بعداً هر زمان مایل بودید در بخش تنظیمات کلاس تغییر دهید.",
                ]
            )
        return "\n".join(
            [
                "⚡ Quick Setup Ready! 🎉",
                "",
                f"🏫 Class Nickname: {p.get('display_name', 'Missing')}",
                f"🎯 Level: {_display(p.get('level_choice'))}",
                "⏱️ Defaults applied: 60 mins · General English · Adults",
                "",
                "Tap '✅ Create Class' below to activate your class and start planning! ✨",
                "",
                "💡 Tip: You can customize textbooks, equipment, and goals anytime in Class Settings.",
            ]
        )

    if lang == "fa":
        book = "رد شده"
        if p.get("coursebook_state") == "provided":
            book = str(p.get("coursebook") or "ثبت شده")
            if p.get("coursebook_unit"):
                book += f" · {p['coursebook_unit']}"
        return "\n".join(
            [
                "✅ بررسی و تایید مشخصات کلاس",
                "",
                "مشخصات کلاستان را مرور کنید. هر بخشی نیاز به اصلاح داشت با دکمه ویرایش آن را تغییر دهید:",
                "",
                f"نام کلاس: {p.get('display_name', 'ثبت نشده')}",
                f"سطح (CEFR): {_display(p.get('level_choice'), lang=lang)}",
                f"رده سنی: {_display(p.get('age_group_choice'), lang=lang)}",
                f"تعداد زبان‌آموزان: {_display(p.get('learner_count_band_choice'), lang=lang)}",
                f"مدت زمان جلسه: {_display(p.get('duration_choice'), lang=lang)}"
                + (" دقیقه" if isinstance(p.get("duration_choice"), int) else ""),
                f"هدف اصلی: {_display(p.get('goal_choice'), lang=lang)}",
                f"مهارت‌های نیازمند تمرین: {_display_choices('weak_areas', p.get('weak_areas'), lang=lang)}",
                f"کتاب و سرفصل: {book}",
                f"امکانات کلاسی: {_display_choices('equipment', p.get('equipment'), lang=lang)}",
                f"سبک تدریس: {_display_choices('teaching_preferences', p.get('teaching_preferences'), lang=lang)}",
                "",
                "💡 نکته: اطلاعات شخصی یا نام زبان‌آموزان ذخیره نمی‌شود.",
            ]
        )

    book = "Skipped"
    if p.get("coursebook_state") == "provided":
        book = str(p.get("coursebook") or "Provided")
        if p.get("coursebook_unit"):
            book += f" · {p['coursebook_unit']}"
    return "\n".join(
        [
            "✅ Review Class Setup",
            "",
            "Check and edit anything before creating the class.",
            "",
            f"Name: {p.get('display_name', 'Missing')}",
            f"CEFR: {_display(p.get('level_choice'))}",
            f"Age group: {_display(p.get('age_group_choice'))}",
            f"Class size: {_display(p.get('learner_count_band_choice'))}",
            f"Duration: {_display(p.get('duration_choice'))}"
            + (" minutes" if isinstance(p.get("duration_choice"), int) else ""),
            f"Main goal: {_display(p.get('goal_choice'))}",
            f"Weak areas: {_display_choices('weak_areas', p.get('weak_areas'))}",
            f"Coursebook: {book}",
            f"Equipment: {_display_choices('equipment', p.get('equipment'))}",
            "Preference: "
            + _display_choices("teaching_preferences", p.get("teaching_preferences")),
            "",
            "Privacy: no student names, disabilities, health data, or sensitive profiles are stored.",
        ]
    )


async def _render(query: Any, context: ContextTypes.DEFAULT_TYPE, draft: dict[str, Any], lang: str = "en") -> None:
    text, markup = _screen(draft, lang=lang)
    if draft["step"] in {"name", "book"}:
        context.user_data["class_setup"] = {
            "state": draft["step"], "revision": draft["revision"], "draft_id": draft["id"]
        }
    else:
        context.user_data.pop("class_setup", None)
    await _safe_edit(query, text, markup)


async def handle_setup_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    action: str,
    object_id: str,
    revision_text: str,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or not isinstance(user.id, int):
        return
    lang = resolve_lang(update, context, telegram_user_id=user.id)
    try:
        draft = get_setup_draft(telegram_user_id=user.id)
        classes = list_classes(telegram_user_id=user.id, include_archived=True, limit=1)
        if action == "new":
            if lang == "fa":
                text = (
                    "➕ ساخت کلاس جدید\n\n"
                    "با پاسخ به چند سوال کوتاه، مشخصات کلاستان ثبت می‌شود. هر زمان که بخواهید می‌توانید پیش‌نویس را ذخیره کنید و بعداً ادامه دهید.\n\n"
                    "💡 توجه: برای حفظ حریم خصوصی، فقط مشخصات کلی کلاس را ثبت کنید و از وارد کردن نام واقعی زبان‌آموزان خودداری فرمایید."
                )
            else:
                text = (
                    "➕ Create a Class\n\n"
                    "Setup uses buttons and one short phrase at a time. You can save and finish later. "
                    "Use classes for recurring teaching; use Quick Create for one-off work. "
                    "Store class context, never student names, disabilities, health data, or sensitive profiles."
                )
            await _safe_edit(
                query,
                text,
                setup_entry_keyboard(can_template=bool(classes), has_draft=draft is not None, lang=lang),
            )
            return
        if action in {"begin", "qbegin", "template"}:
            if draft is None:
                template = classes[0] if action == "template" and classes else None
                draft = start_setup_draft(telegram_user=user, template=template)
                if action == "qbegin":
                    draft["payload"]["fast_setup"] = True
                    draft = save_setup_draft(
                        telegram_user_id=user.id,
                        expected_revision=draft["revision"],
                        step=draft["step"],
                        payload=draft["payload"],
                    )
            elif action == "qbegin":
                draft["payload"]["fast_setup"] = True
                draft = save_setup_draft(
                    telegram_user_id=user.id,
                    expected_revision=draft["revision"],
                    step=draft["step"],
                    payload=draft["payload"],
                )
            await _render(query, context, draft, lang=lang)
            return
        if action == "resume":
            if draft is None:
                msg = "⚠️ هیچ پیش‌نویس ذخیره‌شده‌ای یافت نشد." if lang == "fa" else "⚠️ No saved class draft is available. No change was made."
                await _safe_edit(query, msg, class_recovery_keyboard(lang=lang))
            else:
                await _render(query, context, draft, lang=lang)
            return
        # The completion service uses the durable draft id as its idempotency key.
        # Route Save before requiring a live draft so a repeated Telegram callback
        # can recover the class created by the first tap after that draft is deleted.
        if action == "save":
            callback_draft_id = int(object_id, 36)
            class_record, created = complete_setup(
                telegram_user_id=user.id,
                draft_id=callback_draft_id,
            )
            context.user_data.clear()
            context.user_data["lang"] = lang
            if lang == "fa":
                success_text = (
                    ("🎉 کلاس جدید با موفقیت ساخته شد!" if created else "✅ این کلاس قبلاً ثبت شده است.")
                    + f"\n\n🏫 کلاس فعال: {class_record['display_name']}\n\nاطلاعات کلاس ذخیره شد و اکنون می‌توانید طرح درس جلسه اول را بسازید یا محتوای آموزشی متناسب با این کلاس تولید کنید ✨"
                )
            else:
                success_text = (
                    ("🎉 Class created successfully!" if created else "✅ Class already created")
                    + f"\n\n🏫 Active class: {class_record['display_name']}\n\nYour class context is ready. What would you like to prepare first?"
                )
            await _safe_edit(
                query,
                success_text,
                class_hub_keyboard(int(class_record["id"]), int(class_record["revision"]), lang=lang),
            )
            return
        if draft is None:
            msg = "⚠️ این مرحله تغییر یافته یا منقضی شده است." if lang == "fa" else "⚠️ This setup changed or expired. No change was made."
            await _safe_edit(query, msg, class_recovery_keyboard(lang=lang))
            return
        supplied_revision = _revision(revision_text)
        if supplied_revision not in {0, int(draft["revision"])}:
            msg = "⚠️ این مرحله تغییر یافته یا منقضی شده است." if lang == "fa" else "⚠️ This setup changed or expired. No change was made."
            await _safe_edit(query, msg, class_recovery_keyboard(lang=lang))
            return
        if action == "draft":
            context.user_data.clear()
            context.user_data["lang"] = lang
            msg = "💾 پیش‌نویس کلاس ذخیره شد\n\nهر زمان که مایل بودید می‌توانید از «کلاس‌های من» ثبت کلاس را ادامه دهید." if lang == "fa" else "💾 Class draft saved\n\nResume from My Classes whenever you are ready."
            await _safe_edit(query, msg, saved_keyboard(lang=lang))
            return
        if action == "cancel":
            msg = "فرآیند ثبت کلاس متوقف شود؟\n\nمی‌توانید پیش‌نویس را ذخیره کنید، فرآیند را ادامه دهید یا آن را حذف نمایید." if lang == "fa" else "Pause setup?\n\nKeep the saved draft, continue now, or explicitly discard it."
            await _safe_edit(query, msg, cancel_keyboard(int(draft["revision"]), lang=lang))
            return
        if action == "discard":
            msg = "آیا پیش‌نویس این کلاس حذف شود؟\n\nاین عملیات قابل بازگشت نیست." if lang == "fa" else "Discard this class draft?\n\nThis cannot be undone. No completed class will be changed."
            await _safe_edit(query, msg, discard_keyboard(int(draft["revision"]), lang=lang))
            return
        if action == "dropyes":
            discard_setup_draft(telegram_user_id=user.id)
            context.user_data.clear()
            context.user_data["lang"] = lang
            msg = "🗑 پیش‌نویس حذف شد. کلاسی ساخته نشد." if lang == "fa" else "🗑 Draft discarded. No class was created."
            await _safe_edit(query, msg, class_recovery_keyboard(lang=lang))
            return
        payload = dict(draft["payload"])
        if action == "edit":
            step = EDIT_CODES.get(object_id)
            if step is None:
                raise ValueError("Unknown edit field.")
            payload["_return_to_review"] = True
            updated = save_setup_draft(telegram_user_id=user.id, expected_revision=draft["revision"], step=step, payload=payload)
        elif action == "back":
            previous = PREVIOUS_STEP.get(draft["step"])
            if previous is None:
                msg = "🏫 کلاس‌های من" if lang == "fa" else "🏫 My Classes"
                await _safe_edit(query, msg, class_recovery_keyboard(lang=lang))
                return
            payload.pop("_return_to_review", None)
            updated = save_setup_draft(telegram_user_id=user.id, expected_revision=draft["revision"], step=previous, payload=payload)
        elif action == "skip" and draft["step"] == "book":
            payload.update({"coursebook_state": "skipped", "coursebook": None, "coursebook_unit": None})
            updated = _advance(user.id, draft, payload, "equipment")
        elif action in FIELD_FOR_ACTION:
            value = VALUE_MAPS[action].get(object_id)
            if value is None:
                raise ValueError("Unknown setup choice.")
            payload[FIELD_FOR_ACTION[action]] = value
            if action == "level" and payload.get("fast_setup"):
                payload["age_group_choice"] = payload.get("age_group_choice") or "adults"
                payload["learner_count_band_choice"] = payload.get("learner_count_band_choice") or "6_12"
                payload["duration_choice"] = payload.get("duration_choice") or 60
                payload["goal_choice"] = payload.get("goal_choice") or "general_english"
                payload["weak_areas"] = payload.get("weak_areas") or ["ns"]
                payload["coursebook_state"] = payload.get("coursebook_state") or "skipped"
                payload["equipment"] = payload.get("equipment") or ["board"]
                payload["teaching_preferences"] = payload.get("teaching_preferences") or ["balanced"]
                updated = save_setup_draft(
                    telegram_user_id=user.id,
                    expected_revision=draft["revision"],
                    step="review",
                    payload=payload,
                )
            else:
                updated = _advance(user.id, draft, payload, NEXT_STEP[draft["step"]])
        elif action in {"weak", "equip", "prefer"}:
            field = {"weak": "weak_areas", "equip": "equipment", "prefer": "teaching_preferences"}[action]
            value = VALUE_MAPS[action].get(object_id)
            if value is None:
                raise ValueError("Unknown multi-select choice.")
            selected = list(payload.get(field, []))
            if value in {"ns", "none"}:
                selected = [] if value in selected else [value]
            else:
                selected = [item for item in selected if item not in {"ns", "none"}]
                if value in selected:
                    selected.remove(value)
                else:
                    selected.append(value)
            payload[field] = selected
            updated = save_setup_draft(telegram_user_id=user.id, expected_revision=draft["revision"], step=draft["step"], payload=payload)
        elif action == "next" and draft["step"] in {"weak", "equipment", "preference"}:
            field = {"weak": "weak_areas", "equipment": "equipment", "preference": "teaching_preferences"}[draft["step"]]
            if not payload.get(field):
                hint = ("حداقل یک گزینه را انتخاب کنید (در صورت نیاز گزینه مطمئن نیستم را بزنید).\n\n" if lang == "fa" else "Choose at least one option, including Not sure if needed.\n\n")
                screen_content = _screen(draft, lang=lang)
                await _safe_edit(query, hint + screen_content[0], screen_content[1])
                return
            updated = _advance(user.id, draft, payload, NEXT_STEP[draft["step"]])
        else:
            raise ValueError("Unknown setup action.")
        if updated is None:
            msg = "⚠️ این مرحله تغییر یافته یا منقضی شده است." if lang == "fa" else "⚠️ This setup changed or expired. No change was made."
            await _safe_edit(query, msg, class_recovery_keyboard(lang=lang))
        else:
            await _render(query, context, updated, lang=lang)
    except ClassLimitReachedError as exc:
        access = exc.access
        if lang == "fa":
            limit_msg = f"⛔ سقف تعداد کلاس‌های فعال تکمیل شده است\n\nطرح فعلی: {access['plan_name']}\nکلاس‌های فعال: {access['active_classes']}\nسقف مجاز: {access['class_limit']}\n\nپیش‌نویس شما همچنان ذخیره است."
        else:
            limit_msg = f"⛔ Active class limit reached\n\nPlan: {access['plan_name']}\nActive classes: {access['active_classes']}\nLimit: {access['class_limit']}\n\nYour draft is still saved."
        await _safe_edit(query, limit_msg, saved_keyboard(lang=lang))
    except Exception:
        logger.exception("Could not continue class setup")
        err_msg = "⚠️ ادامه فرآیند امکان‌پذیر نبود. آخرین پیش‌نویس ذخیره‌شده بدون تغییر باقی ماند." if lang == "fa" else "⚠️ Class setup could not continue. Your last saved draft is unchanged."
        await _safe_edit(query, err_msg, class_recovery_keyboard(lang=lang))


def _advance(user_id: int, draft: dict[str, Any], payload: dict[str, Any], normal_next: str) -> dict[str, Any] | None:
    next_step = "review" if payload.pop("_return_to_review", False) else normal_next
    return save_setup_draft(telegram_user_id=user_id, expected_revision=draft["revision"], step=next_step, payload=payload)


async def get_class_setup_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("class_setup")
    if not isinstance(state, dict) or update.message is None or update.effective_user is None:
        return
    user = update.effective_user
    lang = resolve_lang(update, context, telegram_user_id=user.id)
    text = " ".join((update.message.text or "").split())
    draft = get_setup_draft(telegram_user_id=user.id)
    if draft is None or draft["id"] != state.get("draft_id") or draft["revision"] != state.get("revision"):
        context.user_data.pop("class_setup", None)
        msg = "⚠️ این مرحله تغییر یافته یا منقضی شده است. می‌توانید آن را از «کلاس‌های من» ادامه دهید." if lang == "fa" else "⚠️ This setup changed or expired. Resume it from My Classes."
        await update.message.reply_text(msg, reply_markup=saved_keyboard(lang=lang))
        return
    step = str(state.get("state"))
    maximum = 60 if step == "name" else 80
    word_limit = 10 if step == "name" else 14
    if not text or len(text) > maximum or len(text.split()) > word_limit or re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|\b\+?\d[\d -]{7,}\d\b", text):
        prompt_msg = (
            f"لطفاً یک عبارت کوتاه و مشخص (حداکثر {word_limit} کلمه) وارد نمایید. از درج نام اشخاص، ایمیل یا شماره تماس خودداری فرمایید."
            if lang == "fa"
            else f"Please enter one short, non-sensitive phrase (up to {word_limit} words). Do not include names, email addresses, phone numbers, health, or disability information."
        )
        await update.message.reply_text(prompt_msg, reply_markup=typed_step_keyboard(int(draft["revision"]), skip=step == "book", lang=lang))
        return
    payload = dict(draft["payload"])
    if step == "name":
        payload["display_name"] = text
        normal_next = "review" if payload.get("template_used") else "level"
    else:
        parts = [part.strip() for part in text.split("|", 1)]
        payload["coursebook"] = parts[0]
        payload["coursebook_unit"] = parts[1] if len(parts) == 2 and parts[1] else None
        payload["coursebook_state"] = "provided"
        normal_next = "equipment"
    updated = _advance(user.id, draft, payload, normal_next)
    if updated is None:
        msg = "⚠️ این فرآیند تغییر یافته است. آخرین پیش‌نویس ذخیره‌شده را از کلاس‌های من ادامه دهید." if lang == "fa" else "⚠️ This setup changed. Resume the latest saved draft."
        await update.message.reply_text(msg, reply_markup=saved_keyboard(lang=lang))
        return
    screen_text, markup = _screen(updated, lang=lang)
    if updated["step"] in {"name", "book"}:
        context.user_data["class_setup"] = {"state": updated["step"], "revision": updated["revision"], "draft_id": updated["id"]}
    else:
        context.user_data.pop("class_setup", None)
    await update.message.reply_text(screen_text, reply_markup=markup)
