from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from class_dashboard_keyboards import (
    archived_dashboard_keyboard,
    class_action_keyboard,
    class_advanced_tools_keyboard,
    class_dashboard_keyboard,
    class_details_keyboard,
    class_hub_keyboard,
    class_menu_class_keyboard,
    class_menu_planning_keyboard,
    class_menu_assessment_keyboard,
    class_menu_tools_keyboard,
    class_profile_keyboard,
    confirmation_keyboard,
    edit_choice_keyboard,
    edit_multi_keyboard,
    edit_text_keyboard,
    lesson_cancel_confirmation_keyboard,
    lesson_history_keyboard,
    next_lesson_followup_keyboard,
    next_lesson_modes_keyboard,
    next_lesson_priorities_keyboard,
    next_lesson_recommendation_keyboard,
    next_lesson_sources_keyboard,
    next_lesson_why_keyboard,
    outcome_completion_keyboard,
    outcome_difficulty_keyboard,
    outcome_lesson_picker_keyboard,
    outcome_note_keyboard,
    outcome_reminder_keyboard,
    outcome_result_keyboard,
    outcome_summary_keyboard,
    today_queue_keyboard,
)
from class_dashboard_service import (
    class_dashboard_snapshot,
    set_class_archived,
    today_queue,
    touch_class_activity,
    update_profile_field,
)
from config import USAGE_TIMEZONE, get_usage_timezone
from class_setup_panel import (
    AGES,
    CHOICE_LABELS,
    DURATIONS,
    EQUIPMENT,
    GOALS,
    LEVELS,
    PREFERENCES,
    SIZES,
    WEAK,
    VALUE_MAPS,
)
from keyboards import class_recovery_keyboard
from feature_flags import feature_enabled
from database import list_class_materials, save_generated_material
from keyboards import class_library_keyboard, generated_material_export_keyboard, subscription_limit_keyboard
from ui_service import resolve_lang
from lesson_history_service import (
    cancel_planned_lesson,
    get_owned_class_lesson,
    lesson_conversion_metrics,
    list_lesson_history,
    mark_lesson_taught,
)
from outcome_checkin_service import (
    get_lesson_outcome,
    list_outcome_lessons,
    outcome_recording_metrics,
    schedule_outcome_reminder,
    save_outcome_facts,
    update_outcome_note,
)
from next_lesson_service import (
    MODE_LABELS,
    claim_recommendation_generation,
    complete_next_lesson_plan,
    get_or_create_recommendation,
    get_recommendation,
    ignore_recommendation,
    next_lesson_metrics,
    plan_timing_total,
    record_next_lesson_edit,
    record_next_lesson_followup,
    release_recommendation_generation,
    select_recommendation_mode,
    set_manual_next_lesson_request,
    set_recommendation_priority,
    toggle_recommendation_source,
)
from ai_gateway import generate_artifact, generation_provenance
from subscription_service import (
    generation_access_for_user,
    generation_block_message,
    selected_openrouter_model,
)


logger = logging.getLogger(__name__)
DASHBOARD_ACTIONS = {
    "open", "adv", "today", "details", "plan", "analyze", "create", "outcome", "diff",
    "progress", "profile", "pfedit", "edset", "edmulti", "edsave", "edclear",
    "archask", "archyes", "restask", "restyes", "library", "hist", "taught",
    "canask", "canyes", "ostart", "ores", "odiff", "odone", "odnext",
    "ocomp", "oedit", "onote", "onclear", "oskip", "oremind", "orsave",
    "nlrec", "nlmode", "nlmset", "nlprio", "nlpset", "nlsrc", "nltog",
    "nlwhy", "nlgen", "nlign", "nlman", "nlfa",
    "m_cls", "m_pln", "m_ass", "m_tls",
}
NEXT_LESSON_MODE_CODES = {
    "r": "recommendation",
    "u": "continue_unfinished",
    "t": "reteach",
    "n": "new_topic",
    "a": "assessment",
    "m": "manual",
}
NEXT_LESSON_PRIO_CODES = {
    "b": "balanced",
    "c": "continuity",
    "r": "reteaching",
    "a": "assessment",
}
OUTCOME_RESULT_CODES = {"a": "achieved", "p": "partly_achieved", "r": "needs_reteaching"}
OUTCOME_RESULT_LABELS = {
    "met": "Achieved", "partly_met": "Partly achieved", "not_met": "Needs reteaching"
}
OUTCOME_DIFFICULTY_BITS = {
    0: "language", 1: "instructions", 2: "pace", 3: "participation",
    4: "materials", 5: "assessment",
}
OUTCOME_DIFFICULTY_OPTION_BITS = {"l": 0, "i": 1, "p": 2, "t": 3, "m": 4, "a": 5}
OUTCOME_DIFFICULTY_LABELS = {
    "none": "No major difficulty", "language": "Language / concept",
    "instructions": "Instructions", "pace": "Pace / time",
    "participation": "Participation", "materials": "Materials",
    "assessment": "Assessment check",
}
OUTCOME_COMPLETION_CODES = {
    "c": "completed", "p": "partly_completed", "n": "not_completed"
}
OUTCOME_REMINDER_CODES = {
    "h": "one_hour", "e": "local_18", "w": "local_20", "t": "tomorrow_09"
}
FIELD_CODES = {
    "nm": "display_name",
    "lv": "level",
    "ag": "age_group",
    "sz": "learner_count_band",
    "du": "lesson_duration_minutes",
    "go": "goal",
    "wk": "weak_areas",
    "bk": "coursebook",
    "eq": "equipment",
    "pf": "teaching_preferences",
}
SINGLE_CHOICES = {
    "lv": (LEVELS, VALUE_MAPS["level"]),
    "ag": (AGES, VALUE_MAPS["age"]),
    "sz": (SIZES, VALUE_MAPS["size"]),
    "du": (DURATIONS, VALUE_MAPS["duration"]),
    "go": (GOALS, VALUE_MAPS["goal"]),
}
MULTI_CHOICES = {
    "wk": (WEAK, "weak_areas"),
    "eq": (EQUIPMENT, "equipment"),
    "pf": (PREFERENCES, "teaching_preferences"),
}


async def _safe_edit(query: Any, text: str, markup: Any) -> None:
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


def _short(value: object, maximum: int = 46) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= maximum else text[: maximum - 1].rstrip() + "…"


def _human(value: object, lang: str = "en") -> str:
    if value in {None, "not_sure", "ns"}:
        return "مطمئن نیستم" if lang == "fa" else "Not sure"
    if lang == "fa":
        val_map = {
            "young_learners": "کودکان", "teens": "نوجوانان", "adults": "بزرگسالان", "mixed": "سنین مختلف",
            "one_to_one": "تک‌نفره (خصوصی)", "2_5": "۲ تا ۵ نفر", "6_12": "۶ تا ۱۲ نفر",
            "13_20": "۱۳ تا ۲۰ نفر", "21_plus": "بیش از ۲۱ نفر",
            "general_english": "انگلیسی عمومی", "conversation": "مکالمه و گفت‌وگو",
            "exam_preparation": "آمادگی آزمون", "business_english": "انگلیسی تجاری",
            "academic_english": "انگلیسی آکادمیک", "travel_english": "انگلیسی سفر",
            "achieved": "کاملاً محقق شد", "partly_achieved": "تا حدی محقق شد", "needs_reteaching": "نیاز به تدریس مجدد",
            "completed": "کامل تدریس شد", "partly_completed": "بخشی تدریس شد", "not_completed": "تدریس نشد",
            "language_concept": "مفهوم / زبان", "instructions": "دستورالعمل", "pace_time": "مدیریت زمان",
            "participation": "مشارکت", "materials": "محتوا و منابع", "assessment_check": "سنجش", "none": "بدون چالش خاص",
            "recommendation": "پیشنهاد هوشمند", "continue_unfinished": "تکمیل مطالب قبلی",
            "reteach": "مرور و بازآموزی", "new_topic": "مبحث جدید", "assessment": "سنجش و ارزیابی", "manual": "انتخاب دستی",
            "balanced": "متعادل و بهینه", "continuity": "پیوستگی درس‌ها", "reteaching": "رفع چالش‌ها",
        }
        if str(value) in val_map:
            return val_map[str(value)]
    return str(value).replace("_", " ").title()


def _when(value: object, lang: str = "en") -> str:
    text = str(value or "").strip()
    if not text:
        return "ثبت نشده" if lang == "fa" else "Not recorded"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return _short(text, 24)
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def _profile_data(class_record: dict[str, Any]) -> dict[str, Any]:
    try:
        profile = json.loads(str(class_record.get("setup_profile_json") or "{}"))
    except json.JSONDecodeError:
        profile = {}
    return profile if isinstance(profile, dict) else {}


def _choice_text(field: str, values: object, lang: str = "en") -> str:
    if not isinstance(values, list) or not values:
        return "مطمئن نیستم" if lang == "fa" else "Not sure"
    if lang == "fa":
        val_map = {
            "spk": "مکالمه", "lst": "شنیداری", "read": "خواندن", "write": "نوشتاری", "gram": "گرامر", "vocab": "واژگان", "pron": "تلفظ",
            "board": "تخته", "proj": "پروژکتور", "audio": "صوت", "print": "پرینتر", "net": "اینترنت", "none": "هیچ‌کدام",
            "comm": "مکالمه‌محور", "struct": "ساختاریافته", "task": "تکلیف‌محور", "game": "بازی و تعامل", "exam": "آزمون‌محور", "balanced": "متعادل",
        }
        return ", ".join(val_map.get(str(item), _human(item, lang=lang)) for item in values)
    labels = CHOICE_LABELS.get(field, {})
    return ", ".join(labels.get(str(item), _human(item)) for item in values)


def _profile_lines(class_record: dict[str, Any], lang: str = "en") -> list[str]:
    profile = _profile_data(class_record)
    book = class_record.get("coursebook")
    if book and class_record.get("coursebook_unit"):
        book = f"{book} · {class_record['coursebook_unit']}"
    if not book:
        if lang == "fa":
            book = "رد شده" if profile.get("coursebook_state") == "skipped" else "مطمئن نیستم"
        else:
            book = "Skipped" if profile.get("coursebook_state") == "skipped" else "Not sure"
    duration = class_record.get("lesson_duration_minutes")
    if lang == "fa":
        dur_text = f"مدت جلسه: {duration} دقیقه" if duration else "مدت جلسه: مطمئن نیستم"
        return [
            f"نام کلاس: {class_record['display_name']}",
            f"سطح (CEFR): {_human(class_record.get('level') or profile.get('level_choice'), lang=lang)}",
            f"رده سنی: {_human(class_record.get('age_group') or profile.get('age_group_choice'), lang=lang)}",
            f"تعداد زبان‌آموزان: {_human(class_record.get('learner_count_band') or profile.get('learner_count_band_choice'), lang=lang)}",
            dur_text,
            f"هدف اصلی: {_human(class_record.get('goal') or profile.get('goal_choice'), lang=lang)}",
            f"مهارت‌های نیازمند تمرین: {_choice_text('weak_areas', profile.get('weak_areas'), lang=lang)}",
            f"کتاب و سرفصل: {book}",
            f"امکانات کلاس: {_choice_text('equipment', profile.get('equipment'), lang=lang)}",
            "سبک تدریس: " + _choice_text("teaching_preferences", profile.get("teaching_preferences"), lang=lang),
        ]
    return [
        f"Name: {class_record['display_name']}",
        f"CEFR: {_human(class_record.get('level') or profile.get('level_choice'))}",
        f"Age group: {_human(class_record.get('age_group') or profile.get('age_group_choice'))}",
        f"Class size: {_human(class_record.get('learner_count_band') or profile.get('learner_count_band_choice'))}",
        f"Duration: {duration} minutes" if duration else "Duration: Not sure",
        f"Goal: {_human(class_record.get('goal') or profile.get('goal_choice'))}",
        f"Weak areas: {_choice_text('weak_areas', profile.get('weak_areas'))}",
        f"Coursebook: {book}",
        f"Equipment: {_choice_text('equipment', profile.get('equipment'))}",
        "Preference: " + _choice_text("teaching_preferences", profile.get("teaching_preferences")),
    ]


def _advanced_tools_text(snapshot: dict[str, Any], lang: str = "en") -> str:
    class_record = snapshot["class"]
    if lang == "fa":
        return "\n".join([
            f"✨ جعبه‌ابزار تخصصی و پیشرفته تدریس 🎒",
            f"🏫 کلاس: {class_record['display_name']}",
            "",
            "همکار خوبم، این ابزارها برای مواقعی است که می‌خواهی کلاست حرفه‌ای‌تر باشد. اصلاً نگران نباش؛ نیازی نیست هر روز از همه این‌ها استفاده کنی، هر زمان نیاز داشتی در اختیارت هستند:",
            "",
            "👥 ۱. کمک به شاگردان ضعیف و قوی:",
            "اگر چند شاگرد داری که از بقیه عقب‌ترند، تمرین‌ها را برایشان ساده‌تر می‌کنم تا ناامید نشوند؛ برای شاگردان زرنگ هم تمرین‌های چالشی‌تر می‌سازم تا سر کلاس خسته نشوند.",
            "",
            "🧠 ۲. بازی‌های مرور طلایی:",
            "با روش علمی بهت یادآوری می‌کنم چه لغت‌هایی دارد از یاد بچه‌ها می‌رود تا اول کلاس در قالب بازی دوره‌شان کنی.",
            "",
            "🔍 ۳. تصحیح و بررسی تکالیف:",
            "عکس یا متن تکالیف زبان‌آموزان را بفرست تا اشتباهات مکرر گرامری یا املایی را استخراج کنم و تمرین جبرانی بسازم.",
            "",
            "📖 ۴. دفتر پیشرفت کتاب و ترم:",
            "بررسی کن چقدر از کتاب درسی تدریس شده و چقدر تا پایان ترم مانده تا بودجه‌بندی رعایت شود.",
            "",
            "📊 ۵. گزارش پیشرفت به والدین یا آموزشگاه:",
            "گزارش‌های تحلیلی و شیک برای ارائه به مدیریت یا اولیا.",
            "",
            "📚 ۶. تاریخچه درس‌های قبل:",
            "مرور آرشیو مباحثی که تا امروز در این کلاس تدریس کرده‌اید.",
            "",
            "یکی از ابزارها را انتخاب کنید یا به صفحه اصلی کلاس برگردید ✨",
        ])
    return "\n".join([
        f"✨ Advanced Teaching Toolkit 🎒",
        f"🏫 Class: {class_record['display_name']}",
        "",
        "Welcome to your advanced pedagogical suite! These tools help you handle deep teaching needs. You don't need to use all of them every day—they're here whenever you need them:",
        "",
        "👥 1. Help Fast & Slow Learners (Differentiation):",
        "Adapt tasks into tiered versions so slower students stay confident and advanced students stay challenged.",
        "",
        "🧠 2. Spaced Review Warm-Up Games:",
        "Scientifically reminds you of past vocabulary and grammar before students forget them, turning them into 5-minute warm-ups.",
        "",
        "🔍 3. Check Homework & Writing Feedback:",
        "Submit student essays or test answers to diagnose recurring mistakes and get actionable feedback.",
        "",
        "📖 4. Coursebook & Syllabus Tracker:",
        "Track how much of your coursebook units have been covered across the term.",
        "",
        "📊 5. Parent & School Progress Reports:",
        "Generate polished progress summaries ready to share with school administrators or parents.",
        "",
        "📚 6. Past Lesson History:",
        "Review summaries of everything you've taught in previous sessions.",
        "",
        "Tap any tool below, or return to Class Hub ✨",
    ])


def _menu_class_text(class_name: str, lang: str = "en") -> str:
    if lang == "fa":
        return "\n".join([
            f"🏫 ۱. کلاس و دانش‌آموزان · {class_name}",
            "",
            "مدیریت اطلاعات پایه کلاس، پرونده‌های زبان‌آموزان و ثبت نتیجه تدریس:",
            "",
            "• 📚 کلاس‌های من: بازگشت به لیست تمام کلاس‌های شما",
            "• 👤 دانش‌آموزان: پرونده‌های تشخیصی ۱۱گانه و سوابق تک‌تک زبان‌آموزان",
            "• 📋 مشخصات کلاس: مشاهده و ویرایش سطح، کتاب، سن و امکانات کلاس",
            "• ✅ ثبت نتیجه تدریس: ثبت بازخورد تدریس جلسه و چالش‌های مشاهده‌شده",
        ])
    return "\n".join([
        f"🏫 1. Class & Students · {class_name}",
        "",
        "Manage your class roster, student profiles, and teaching outcomes:",
        "",
        "• My Classes: Switch to another class or view all",
        "• Class Students: 11 diagnostic sections and learner profiles",
        "• Profile: Class level, book, age group, and settings",
        "• Record Outcome: Quick post-lesson check-in",
    ])


def _menu_planning_text(class_name: str, lang: str = "en") -> str:
    if lang == "fa":
        return "\n".join([
            f"📝 ۲. طراحی و آماده‌سازی درس · {class_name}",
            "",
            "تمام ابزارهای مورد نیاز شما برای آمادگی قبل از ورود به کلاس:",
            "",
            "• 🎯 طرح درس: ساخت فوری یا شخصی‌سازی طرح درس مرحله‌به‌مرحله برای این کلاس",
            "• 📦 تولید محتوا: ساخت فعالیت کلاسی، کاربرگ، بازی و کوئیز",
            "• 📚 کتابخانه کلاس: دسترسی به تمام فایل‌ها و طرح‌های ذخیره‌شده کلاس",
        ])
    return "\n".join([
        f"📝 2. Planning & Prep · {class_name}",
        "",
        "Everything needed before entering the classroom:",
        "",
        "• Lesson Plan: Fast step-by-step lesson plan for this class",
        "• Create Materials: Worksheets, activities, and games",
        "• Class Library: Saved teaching materials and lesson plans",
    ])


def _menu_assessment_text(class_name: str, lang: str = "en") -> str:
    if lang == "fa":
        return "\n".join([
            f"📊 ۳. ارزیابی و بازخورد · {class_name}",
            "",
            "سنجش میزان یادگیری زبان‌آموزان و ارائه بازخورد تخصصی:",
            "",
            "• 🔬 تحلیل تکالیف: بررسی عکس یا متن تکالیف و استخراج خطاهای زبانی",
            "• 📝 ارزیابی کلاسی: تعریف آزمون‌های رسمی (میدترم، فاینال، آیلتس) و غیررسمی (کوئیز)",
        ])
    return "\n".join([
        f"📊 3. Assessment & Feedback · {class_name}",
        "",
        "Evaluate learning outcomes and diagnostic insights:",
        "",
        "• Analyze Work: Homework & writing analysis with CEFR diagnostics",
        "• Class Assessments: Set up formal and informal exams/quizzes",
    ])


def _dashboard_text(snapshot: dict[str, Any], lang: str = "en") -> str:
    class_record = snapshot["class"]
    profile = _profile_data(class_record)
    planned = snapshot["next_planned_lesson"]
    outcome = snapshot["last_outcome"]

    if lang == "fa":
        compact_parts = [
            _human(class_record.get("level") or profile.get("level_choice"), lang=lang),
            _human(class_record.get("age_group") or profile.get("age_group_choice"), lang=lang),
            _human(class_record.get("learner_count_band") or profile.get("learner_count_band_choice"), lang=lang),
        ]
        compact = " · ".join(p for p in compact_parts if p not in {"Not sure", "مطمئن نیستم"}) or "مشخصات کلی کلاس"
        context_label = "کلاس بایگانی‌شده" if class_record["status"] == "archived" else "کلاس فعال"
        lines = [
            f"🎒 {context_label}: {class_record['display_name']}",
            f"🌱 مشخصات: {compact}",
            "",
            "سلام همکار عزیز! خسته نباشی ☕",
            "فضای تدریس کلاس شما در ۴ بخش اصلی سازمان‌دهی شده است:",
            "",
            "۱. 🏫 کلاس و دانش‌آموزان · ۲. 📝 طراحی و آماده‌سازی درس",
            "۳. 📊 ارزیابی و بازخورد · ۴. 🧰 ابزارهای TeacherOS",
            "",
        ]
        if class_record["status"] == "archived":
            lines.append("♻ این کلاس بایگانی شده است. برای فعال‌سازی مجدد از دکمه بازیابی استفاده کنید.")
        elif planned:
            lines.extend([
                f"📅 درس آماده: {_short(planned['title'], 32)}",
                f"⏰ زمان‌بندی: {_short(planned.get('scheduled_for') or 'تعیین‌نشده', 22)}",
            ])
        else:
            lines.extend([
                "💡 آماده‌سازی درس: از بخش «طراحی و آماده‌سازی درس» می‌توانید طرح درس این جلسه را آماده کنید ✨",
            ])
        if outcome:
            lines.extend([
                "",
                f"📝 بازخورد جلسه قبل: {_human(outcome['result'], lang=lang)}",
            ])
        return "\n".join(lines)

    compact = " · ".join(
        part for part in (
            _human(class_record.get("level") or profile.get("level_choice")),
            _human(class_record.get("age_group") or profile.get("age_group_choice")),
            _human(class_record.get("learner_count_band") or profile.get("learner_count_band_choice")),
        ) if part != "Not sure"
    ) or "General class profile"
    context_label = "Archived class" if class_record["status"] == "archived" else "Active class"
    lines = [
        f"🏫 {context_label}: {class_record['display_name']}",
        f"{compact}",
        "",
        "Hi Teacher! ☕",
        "Your teaching workspace is organized into 4 clear pillars:",
        "",
        "1. 🏫 Class & Students · 2. 📝 Planning & Prep",
        "3. 📊 Assessment & Feedback · 4. 🧰 TeacherOS Tools",
        "",
    ]
    if class_record["status"] == "archived":
        lines.append("♻ NEXT: Restore this class to continue")
    elif planned:
        lines.extend([
            f"📅 Upcoming lesson: {_short(planned['title'], 32)}",
            f"⏰ Scheduled for: {_short(planned.get('scheduled_for') or 'date not set', 22)}",
        ])
    else:
        lines.extend([
            "🎯 NEXT: Open 'Planning & Prep' to prepare this session's lesson plan! ✨",
        ])
    if outcome:
        lines.extend([
            "",
            f"Last outcome: {OUTCOME_RESULT_LABELS.get(str(outcome['result']), _human(outcome['result']))}",
        ])
    return "\n".join(lines)


def _details_text(snapshot: dict[str, Any], lang: str = "en") -> str:
    class_record = snapshot["class"]
    counts = snapshot["history_counts"]
    if lang == "fa":
        return "\n".join(
            [
                f"ℹ جزئیات و آمار کلاس · {class_record['display_name']}",
                "",
                *_profile_lines(class_record, lang=lang),
                "",
                f"تعداد طرح درس‌ها: {counts.get('lessons', 0)}",
                f"نتایج ثبت‌شده: {counts.get('outcomes', 0)}",
                f"محتواهای تولیدشده: {counts.get('materials', 0)}",
                (
                    "وضعیت جلسات: "
                    f"{counts.get('generated', 0)} تولیدشده · "
                    f"{counts.get('planned', 0)} در برنامه · "
                    f"{counts.get('taught', 0)} تدریس‌شده · "
                    f"{counts.get('cancelled', 0)} لغوشده"
                ),
                f"شواهد در انتظار تایید: {snapshot['pending_analysis_count']}",
                f"مرورهای موعدرسیده: {snapshot['due_review_count']}",
                f"آخرین فعالیت: {_when(class_record.get('last_active_at'), lang=lang)}",
            ]
        )
    return "\n".join(
        [
            f"ℹ Details · {class_record['display_name']}",
            "",
            *_profile_lines(class_record, lang=lang),
            "",
            f"Lessons: {counts.get('lessons', 0)}",
            f"Outcomes: {counts.get('outcomes', 0)}",
            f"Materials: {counts.get('materials', 0)}",
            (
                "Lifecycle: "
                f"{counts.get('generated', 0)} generated · "
                f"{counts.get('planned', 0)} planned · "
                f"{counts.get('taught', 0)} taught · "
                f"{counts.get('cancelled', 0)} cancelled"
            ),
            f"Pending analysis approval: {snapshot['pending_analysis_count']}",
            f"Reviews due: {snapshot['due_review_count']}",
            f"Last active: {_when(class_record.get('last_active_at'))}",
        ]
    )


def _history_text(
    class_name: str,
    lessons: list[dict[str, Any]],
    metrics: dict[str, int],
    *,
    notice: str | None = None,
    lang: str = "en",
) -> str:
    if lang == "fa":
        lines = [f"📚 تاریخچه جلسات تدریس · {class_name}", "", "ترتیب زمانی: قدیمی‌ترین به جدیدترین"]
        if notice:
            lines.extend(["", notice])
        if not lessons:
            lines.extend(
                [
                    "",
                    "هنوز سابقه‌ای برای این کلاس ثبت نشده است.",
                    "طرح درس‌های تولیدشده پس از تدریس در کلاس، به عنوان جلسه تدریس‌شده ثبت خواهند شد.",
                ]
            )
        else:
            lines.append("")
            state_map_fa = {"PLANNED": "در برنامه", "TAUGHT": "تدریس‌شده", "GENERATED": "تولیدشده", "CANCELLED": "لغوشده"}
            for lesson in lessons:
                state = state_map_fa.get(str(lesson["lifecycle_state"]).upper(), str(lesson["lifecycle_state"]).upper())
                when = lesson.get("taught_at") or lesson.get("scheduled_for") or lesson.get("created_at")
                material = f" · منبع #{lesson['material_id']}" if lesson.get("material_id") else ""
                lines.append(
                    f"#{lesson['id']} · {state} · {_short(lesson['title'], 34)}"
                    f" · {_short(when or 'تاریخ ثبت‌نشده', 22)}{material}"
                )
        lines.extend(
            [
                "",
                "آمار تبدیل طرح‌ها: "
                f"تولیدشده→برنامه‌ریزی‌شده {metrics.get('generated_to_planned', 0)} · "
                f"برنامه‌ریزی‌شده→تدریس‌شده {metrics.get('planned_to_taught', 0)}",
            ]
        )
        return "\n".join(lines)

    lines = [f"📚 Lesson History · {class_name}", "", "Oldest → newest · recorded facts only"]
    if notice:
        lines.extend(["", notice])
    if not lessons:
        lines.extend(
            [
                "",
                "No lesson records yet.",
                "Generating a class lesson creates a Generated record; it is not taught history.",
            ]
        )
    else:
        lines.append("")
        for lesson in lessons:
            state = str(lesson["lifecycle_state"]).upper()
            when = lesson.get("taught_at") or lesson.get("scheduled_for") or lesson.get("created_at")
            material = f" · resource #{lesson['material_id']}" if lesson.get("material_id") else ""
            lines.append(
                f"#{lesson['id']} · {state} · {_short(lesson['title'], 34)}"
                f" · {_short(when or 'date not set', 22)}{material}"
            )
    lines.extend(
        [
            "",
            "Conversions: "
            f"generated→planned {metrics.get('generated_to_planned', 0)} · "
            f"planned→taught {metrics.get('planned_to_taught', 0)}",
            "Generated and cancelled records never count as taught.",
        ]
    )
    return "\n".join(lines)


def _decode_positive_base36(value: str) -> int:
    decoded = int(value, 36)
    if decoded < 1:
        raise ValueError("Expected a positive callback identifier.")
    return decoded


def _difficulty_values(mask: int) -> list[str]:
    if mask == 0:
        return ["none"]
    if mask < 0 or mask > 63:
        raise ValueError("Invalid difficulty selection.")
    return [value for bit, value in OUTCOME_DIFFICULTY_BITS.items() if mask & (1 << bit)]


def _outcome_picker_text(
    class_name: str, lessons: list[dict[str, Any]], metrics: dict[str, int], lang: str = "en"
) -> str:
    if lang == "fa":
        lines = [
            f"✅ ثبت بازخورد و نتیجه تدریس · {class_name}", "",
            "جلسه تدریس‌شده را انتخاب کنید تا نتیجه و بازخورد کلاسی آن را ثبت نمایید:",
        ]
        if not lessons:
            lines.extend(["", "هیچ جلسه تدریس‌شده‌ای در انتظار ثبت نتیجه نیست. ابتدا یکی از جلسات برنامه‌ریزی‌شده را به عنوان «تدریس شد» علامت بزنید."])
        else:
            missing = sum(1 for lesson in lessons if lesson.get("outcome_id") is None)
            lines.extend(["", f"در انتظار ثبت بازخورد: {missing} · ثبت‌شده: {len(lessons) - missing}"])
        lines.extend(
            [
                "",
                f"میزان ثبت بازخورد کلاس: {metrics['outcomes_recorded']}/{metrics['taught']} جلسه تدریس‌شده "
                f"({metrics['recording_rate_percent']}٪)",
                "ثبت منظم بازخورد به هوش مصنوعی کمک می‌کند درس‌های آینده را متناسب با نیاز کلاس تنظیم کند ✨",
            ]
        )
        return "\n".join(lines)

    lines = [
        f"✅ Record Outcome · {class_name}", "",
        "Choose an explicitly taught lesson. Recorded facts can be corrected later.",
    ]
    if not lessons:
        lines.extend(["", "No taught lessons are waiting. Mark a planned lesson as taught first."])
    else:
        missing = sum(1 for lesson in lessons if lesson.get("outcome_id") is None)
        lines.extend(["", f"Waiting: {missing} · Recorded: {len(lessons) - missing}"])
    lines.extend(
        [
            "",
            f"Outcome capture: {metrics['outcomes_recorded']}/{metrics['taught']} taught lessons "
            f"({metrics['recording_rate_percent']}%)",
            "Regular check-ins help TeacherOS tailor upcoming lessons to your class's real progress.",
        ]
    )
    return "\n".join(lines)


def _outcome_result_text(lesson: dict[str, Any], *, notice: str | None = None, lang: str = "en") -> str:
    if lang == "fa":
        lines = [
            f"✅ بازخورد تدریس · {lesson['display_name']}",
            f"جلسه #{lesson['id']}: {_short(lesson['title'], 52)}", "",
        ]
        if notice:
            lines.extend([notice, ""])
        lines.extend(
            [
                "مرحله ۱ از ۳ · نتیجه کلی این جلسه چطور بود؟",
                "با انتخاب یکی از گزینه‌های زیر، روند پیشرفت کلاس ثبت می‌شود:",
            ]
        )
        return "\n".join(lines)

    lines = [
        f"✅ Post-lesson check-in · {lesson['display_name']}",
        f"Lesson #{lesson['id']}: {_short(lesson['title'], 52)}", "",
    ]
    if notice:
        lines.extend([notice, ""])
    lines.extend(
        [
            "Tap 1 of 3 · Overall result",
            "What was the overall result?",
            "Select an outcome to help track your group's progress.",
        ]
    )
    return "\n".join(lines)


def _outcome_difficulty_text(lesson: dict[str, Any], mask: int, *, notice: str | None = None, lang: str = "en") -> str:
    selected = _difficulty_values(mask) if mask else []
    if lang == "fa":
        lines = [
            f"✅ بازخورد تدریس · {lesson['display_name']}",
            f"جلسه #{lesson['id']}: {_short(lesson['title'], 52)}", "",
            "مرحله ۲ از ۳ · آیا در بخش خاصی چالش یا کندی وجود داشت؟",
            "اگر تدریس روان بوده، «بدون چالش خاص» را بزنید؛ در غیر این صورت بخش‌های مدنظر را انتخاب کرده و «ثبت موارد» را انتخاب کنید:",
        ]
        if selected:
            diff_names_fa = {"language_concept": "مفهوم / زبان", "instructions": "دستورالعمل", "pace_time": "مدیریت زمان", "participation": "مشارکت", "materials": "محتوا و منابع", "assessment_check": "سنجش", "none": "بدون چالش خاص"}
            lines.extend(["", "موارد انتخاب‌شده: " + ", ".join(diff_names_fa.get(item, item) for item in selected)])
        if notice:
            lines.extend(["", notice])
        return "\n".join(lines)

    lines = [
        f"✅ Post-lesson check-in · {lesson['display_name']}",
        f"Lesson #{lesson['id']}: {_short(lesson['title'], 52)}", "",
        "Tap 2 of 3 · Difficulties",
        "Choose No major difficulty for smooth sailing, or select any categories that needed extra support.",
    ]
    if selected:
        lines.extend(["", "Selected: " + ", ".join(OUTCOME_DIFFICULTY_LABELS[item] for item in selected)])
    if notice:
        lines.extend(["", notice])
    return "\n".join(lines)


def _outcome_completion_text(lesson: dict[str, Any], difficulties: list[str], lang: str = "en") -> str:
    if lang == "fa":
        diff_names_fa = {"language_concept": "مفهوم / زبان", "instructions": "دستورالعمل", "pace_time": "مدیریت زمان", "participation": "مشارکت", "materials": "محتوا و منابع", "assessment_check": "سنجش", "none": "بدون چالش خاص"}
        diff_str = ", ".join(diff_names_fa.get(item, item) for item in difficulties) or "بدون چالش خاص"
        return "\n".join(
            [
                f"✅ بازخورد تدریس · {lesson['display_name']}",
                f"جلسه #{lesson['id']}: {_short(lesson['title'], 52)}", "",
                "مرحله ۳ از ۳ · چه میزان از محتوای طرح درس پوشش داده شد؟",
                f"چالش‌های ثبت‌شده: {diff_str}",
            ]
        )

    return "\n".join(
        [
            f"✅ Post-lesson check-in · {lesson['display_name']}",
            f"Lesson #{lesson['id']}: {_short(lesson['title'], 52)}", "",
            "Tap 3 of 3 · Completion",
            "How much of the planned lesson was completed?",
            "Difficulty: " + ", ".join(OUTCOME_DIFFICULTY_LABELS[item] for item in difficulties),
            "Your tap saves this check-in immediately. An optional note can follow.",
        ]
    )


def _outcome_summary_text(
    outcome: dict[str, Any], metrics: dict[str, int], *, notice: str | None = None, lang: str = "en"
) -> str:
    difficulties = outcome.get("difficulty_categories") or []
    if lang == "fa":
        diff_names_fa = {"language_concept": "مفهوم / زبان", "instructions": "دستورالعمل", "pace_time": "مدیریت زمان", "participation": "مشارکت", "materials": "محتوا و منابع", "assessment_check": "سنجش", "none": "بدون چالش خاص"}
        diff_str = ", ".join(diff_names_fa.get(str(item), str(item)) for item in difficulties) or "ثبت نشده"
        res_names_fa = {"achieved": "✅ کاملاً محقق شد", "partly_achieved": "⚠️ تا حدی محقق شد", "needs_reteaching": "🔄 نیاز به تدریس مجدد"}
        comp_names_fa = {"completed": "کامل تدریس شد", "partly_completed": "بخشی تدریس شد", "not_completed": "تدریس نشد"}
        lines = [
            f"✅ نتیجه تدریس با موفقیت ذخیره شد · {outcome['display_name']}",
            f"جلسه #{outcome['class_lesson_id']}: {_short(outcome['lesson_title'], 52)}", "",
            f"نتیجه کلی: {res_names_fa.get(str(outcome['result']), _human(outcome['result']))}",
            f"چالش‌ها: {diff_str}",
            f"پوشش محتوا: {comp_names_fa.get(str(outcome.get('completion_status')), _human(outcome.get('completion_status')))}",
            "یادداشت معلم: " + (_short(outcome.get("notes"), 120) if outcome.get("notes") else "ثبت نشده (اختیاری)"),
            "",
            f"داشبورد کلاس به‌روز شد · ثبت بازخورد {metrics['outcomes_recorded']}/{metrics['taught']} "
            f"({metrics['recording_rate_percent']}٪)",
            "اطلاعات این جلسه در پیشنهاد درس آینده لحاظ خواهد شد ✨",
        ]
        if notice:
            lines.extend(["", notice])
        return "\n".join(lines)

    lines = [
        f"✅ Outcome saved · {outcome['display_name']}",
        f"Lesson #{outcome['class_lesson_id']}: {_short(outcome['lesson_title'], 52)}", "",
        f"Result: {OUTCOME_RESULT_LABELS.get(str(outcome['result']), _human(outcome['result']))}",
        "Difficulty: " + (", ".join(
            OUTCOME_DIFFICULTY_LABELS.get(str(item), _human(item)) for item in difficulties
        ) or "Not recorded"),
        f"Completion: {_human(outcome.get('completion_status'))}",
        "Teacher note: " + (_short(outcome.get("notes"), 120) if outcome.get("notes") else "Skipped (optional)"),
        f"Facts version: {outcome.get('facts_version', 1)}",
        "",
        f"Dashboard updated · outcome capture {metrics['outcomes_recorded']}/{metrics['taught']} "
        f"({metrics['recording_rate_percent']}%)",
        "Your teaching history helps refine upcoming recommendations.",
    ]
    if notice:
        lines.extend(["", notice])
    return "\n".join(lines)


def _next_lesson_rec_text(
    class_name: str, rec: dict[str, Any], *, notice: str | None = None, lang: str = "en"
) -> str:
    mode = rec.get("effective_mode") or rec.get("recommended_mode")
    duration = rec.get("duration_minutes", 60)
    objectives = rec.get("objective_labels") or []
    sources = rec.get("sources", [])
def _friendly_rationale(rec: dict[str, Any], lang: str = "en") -> str:
    raw = str(rec.get("rationale") or "")
    if lang == "fa":
        raw_lower = raw.lower()
        if "not enough approved outcome history" in raw_lower:
            return "چون این اولین جلسه کلاستان است، یک موضوع جذاب و کاربردی برای شروع مکالمه و سنجش مهارت‌های زبان‌آموزان انتخاب کردیم ✨"
        if "continuity" in raw_lower or "continue" in raw_lower:
            return "برای حفظ پیوستگی آموزشی و تکمیل مباحث جلسه قبل."
        if "reteach" in raw_lower:
            return "با توجه به چالش‌های جلسه قبل، مرور این مبحث با روشی تازه و تمرین‌های کاربردی پیشنهاد شده است."
        if "assessment" in raw_lower:
            return "تمرکز روی سنجش عملی آموخته‌های اخیر زبان‌آموزان."
        if "achieved" in raw_lower:
            return "جلسه قبل با موفقیت تدریس شد؛ برای جلسه جدید، گام بعدی یادگیری به همراه مرور نکات قبلی پیشنهاد شده است."
        return "پیشنهاد هوشمند متناسب با سطح و مشخصات کلاستان."
    return raw


def _next_lesson_rec_text(
    class_name: str, rec: dict[str, Any], *, notice: str | None = None, lang: str = "en"
) -> str:
    mode = rec.get("effective_mode") or rec.get("recommended_mode")
    duration = rec.get("duration_minutes", 60)
    objectives = rec.get("objective_labels") or []
    custom_topic = rec.get("teacher_request")

    if lang == "fa":
        topic_disp = str(custom_topic) if (custom_topic and mode == "manual") else "Travel (سفر و مکالمات روزمره)"
        if not custom_topic and mode != "manual":
            topic_disp = "مکالمات کاربردی و لغات کلیدی"
        lines = [
            f"🎯 آماده‌سازی طرح درس · {class_name}",
            "",
            f"📌 موضوع پیشنهادی: {topic_disp}",
            f"⏱ مدت زمان: {duration} دقیقه",
            "",
            f"💡 علت پیشنهاد:\n{_friendly_rationale(rec, lang=lang)}",
        ]
        if objectives:
            lines.extend(["", "🎯 اهداف آموزشی این جلسه:"] + [f"• {_short(obj, 60)}" for obj in objectives[:2]])
        if notice:
            lines.extend(["", notice])
        lines.extend([
            "",
            "✨ می‌خواهید همین طرح درس را برایتان بسازم یا مایلید موضوع دیگری تدریس کنید؟",
        ])
        return "\n".join(lines)

    topic_disp = str(custom_topic) if (custom_topic and mode == "manual") else "Everyday Communication & Practical Vocabulary"
    lines = [
        f"🎯 Lesson Plan · {class_name}",
        "",
        f"📌 Proposed Topic: {topic_disp}",
        f"⏱ Duration: {duration} mins",
        "",
        f"💡 Why this lesson?\n{_friendly_rationale(rec, lang=lang)}",
    ]
    if objectives:
        lines.extend(["", "Target objective(s):"] + [f"• {_short(obj, 60)}" for obj in objectives[:2]])
    if notice:
        lines.extend(["", notice])
    lines.extend([
        "",
        "Ready to generate this lesson, or would you like to pick a custom topic? ✨",
    ])
    return "\n".join(lines)


def _next_lesson_why_text(class_name: str, rec: dict[str, Any], lang: str = "en") -> str:
    sources = rec.get("sources", [])
    included = [s for s in sources if s.get("included") == 1]
    if lang == "fa":
        lines = [
            f"💡 چرا این مبحث پیشنهاد شد؟ · {class_name}",
            "",
            f"علت: {_friendly_rationale(rec, lang=lang)}",
            "",
            "سوابق و شواهد به‌کاررفته:",
        ]
        if not included:
            lines.append("• سابقه قبلی ثبت نشده؛ بر اساس سطح و مشخصات کلی کلاس پیشنهاد شده است.")
        else:
            for s in included:
                lines.append(f"• {s['source_label']}")
        return "\n".join(lines)
    lines = [
        f"💡 Why this next? · {class_name}",
        "",
        f"Rationale: {_friendly_rationale(rec, lang=lang)}",
        "",
        "Active sources:",
    ]
    if not included:
        lines.append("• No prior history; proposal relies on class profile.")
    else:
        for s in included:
            lines.append(f"• [{s['source_type'].replace('_', ' ')}] {s['source_label']}")
    return "\n".join(lines)



def _next_lesson_modes_text(class_name: str, rec: dict[str, Any], lang: str = "en") -> str:
    current = rec.get("selected_mode") or "recommendation (auto)"
    if lang == "fa":
        mode_fa_map = {
            "recommendation": "پیشنهاد هوشمند", "continue_unfinished": "تکمیل مطالب قبلی",
            "reteach": "مرور و بازآموزی", "new_topic": "مبحث جدید", "assessment": "سنجش و ارزیابی",
            "manual": "موضوع انتخابی دستی",
        }
        return "\n".join([
            f"🎯 انتخاب حالت تدریس جلسه آینده · {class_name}",
            "",
            f"حالت جاری: {mode_fa_map.get(str(current), str(current))}",
            "",
            "• پیشنهاد هوشمند: انتخاب خودکار بر اساس سوابق و چالش‌های گذشته",
            "• تکمیل مطالب قبلی: تدریس بخش‌های ناقص یا کارنشده درس قبل",
            "• مرور و بازآموزی: ارائه مجدد مباحث چالش‌برانگیز با مثال‌های جدید",
            "• مبحث جدید: ورود به درس یا سرفصل جدید",
            "• سنجش و ارزیابی: آزمون کلاسی یا کوئیز بر اساس اهداف دوره",
            "• انتخاب دستی: وارد کردن عنوان و موضوع دلخواه توسط معلم",
        ])

    return "\n".join([
        f"🎯 Choose Next Lesson Mode · {class_name}",
        "",
        f"Current: {str(current).replace('_', ' ').title()}",
        "",
        "• Use recommendation: Auto-select based on history and outcomes",
        "• Continue unfinished: Consolidate previously incomplete work",
        "• Reteach: Fresh angle with scaffolding for difficult concepts",
        "• Start a new topic: Move forward to the next curricular theme",
        "• Prepare for assessment: Observable check against current objectives",
        "• Choose manually: Type your own custom topic",
    ])


def _next_lesson_priorities_text(class_name: str, rec: dict[str, Any], lang: str = "en") -> str:
    if lang == "fa":
        prio_fa_map = {
            "balanced": "متعادل و بهینه", "continuity": "پیوستگی درس‌ها",
            "reteaching": "رفع چالش‌ها", "assessment": "سنجش و ارزیابی",
        }
        return "\n".join([
            f"⚖ اولویت‌بندی پیشنهاد هوشمند · {class_name}",
            "",
            f"اولویت فعلی: {prio_fa_map.get(str(rec.get('priority_mode', 'balanced')), str(rec.get('priority_mode', 'balanced')))}",
            "",
            "• بهینه و متعادل: تصمیم‌گیری بر اساس آخرین بازخورد ثبت‌شده",
            "• اولویت پیوستگی: اولویت با تکمیل درس‌های نیمه‌تمام گذشته",
            "• اولویت رفع چالش‌ها: اولویت با مرور نقاط ضعف و چالش‌ها",
            "• اولویت سنجش: اولویت با کوئیز و ارزیابی آموخته‌ها",
        ])

    return "\n".join([
        f"⚖ Choose Recommendation Priority · {class_name}",
        "",
        f"Current: {str(rec.get('priority_mode', 'balanced')).title()}",
        "",
        "• Balanced: Propose based on the latest recorded outcome result",
        "• Continuity first: Prioritize finishing incomplete lessons",
        "• Reteaching first: Prioritize resolving recorded difficulties",
        "• Assessment first: Prioritize evaluation against objectives",
    ])


def _next_lesson_sources_text(class_name: str, rec: dict[str, Any], lang: str = "en") -> str:
    sources = rec.get("sources", [])
    included_count = sum(1 for s in sources if s.get("included") == 1)
    if lang == "fa":
        return "\n".join([
            f"📋 منابع و سوابق فعال · {class_name}",
            "",
            f"سوابق فعال: {included_count} از {len(sources)}",
            "روی هر مورد بزنید تا در پیشنهاد جلسه آینده لحاظ (✅) یا حذف (▫️) شود.",
        ])

    return "\n".join([
        f"📋 Active History Sources · {class_name}",
        "",
        f"Active records: {included_count} of {len(sources)}",
        "Tap any record to include (✅) or exclude (▫️) it from the next lesson proposal.",
    ])


def _active_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    state = context.user_data.get("active_class")
    return state if isinstance(state, dict) else None


async def _recover(query: Any, context: ContextTypes.DEFAULT_TYPE, lang: str = "en") -> None:
    context.user_data.clear()
    msg = (
        "⚠️ این صفحه کلاس تغییر کرده یا منقضی شده است.\n\n"
        "تغییری اعمال نشد. لطفاً فهرست کلاس‌های خود را بررسی کرده یا به منوی اصلی بازگردید."
        if lang == "fa"
        else (
            "⚠️ This class view changed, expired, or is no longer available.\n\n"
            "No change was made. Refresh your own class list or return home."
        )
    )
    await _safe_edit(
        query,
        msg,
        class_recovery_keyboard(lang=lang),
    )


async def _render_dashboard(
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    telegram_user_id: int,
    class_id: int,
    expected_revision: int | None,
) -> None:
    lang = resolve_lang(None, context, telegram_user_id=telegram_user_id)
    snapshot = class_dashboard_snapshot(
        telegram_user_id=telegram_user_id, class_id=class_id
    )
    if snapshot is None:
        await _recover(query, context, lang=lang)
        return
    class_record = snapshot["class"]
    if expected_revision and int(class_record["revision"]) != expected_revision:
        await _recover(query, context, lang=lang)
        return
    touch_class_activity(telegram_user_id=telegram_user_id, class_id=class_id)
    context.user_data.clear()
    context.user_data["lang"] = lang
    context.user_data["active_class"] = {
        "id": class_id,
        "display_name": str(class_record["display_name"]),
        "revision": int(class_record["revision"]),
    }
    if class_record["status"] == "archived":
        status_suffix = "\n\nوضعیت: بایگانی‌شده · فقط خواندنی" if lang == "fa" else "\n\nStatus: Archived · history preserved · read-only"
        text = _dashboard_text(snapshot, lang=lang) + status_suffix
        markup = archived_dashboard_keyboard(class_id, int(class_record["revision"]), lang=lang)
    else:
        text = _dashboard_text(snapshot, lang=lang)
        markup = class_hub_keyboard(class_id, int(class_record["revision"]), lang=lang)
    await _safe_edit(query, text, markup)


async def handle_dashboard_callback(
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
        if action == "today":
            items = today_queue(telegram_user_id=user.id)
            if lang == "fa":
                lines = ["☀️ کارهای مهم امروز", "", "مهم‌ترین موارد در انتظار اقدام شما:"]
                if items:
                    names_fa = {
                        "unfinished_setup": "تکمیل ثبت کلاس",
                        "missing_outcome": "ثبت بازخورد تدریس",
                        "pending_analysis": "بررسی تکالیف و شواهد",
                        "planned_lesson": "مشاهده طرح درس جاری",
                        "review_due": "مرور زمان‌بندی‌شده",
                    }
                    lines.extend(
                        [
                            "",
                            *[
                                f"{index}. {names_fa.get(item['kind'], item['kind'])}"
                                + (f" · {item['display_name']}" if item["class_id"] else "")
                                for index, item in enumerate(items, 1)
                            ],
                        ]
                    )
                else:
                    lines.extend(["", "همه کارها انجام شده و موردی در انتظار نیست! می‌توانید وارد کلاستان شوید و برای جلسه آینده برنامه‌ریزی کنید ✨"])
            else:
                lines = ["☀ Today", "", "Highest-value unfinished work appears first."]
                if items:
                    names = {
                        "unfinished_setup": "Finish class setup",
                        "missing_outcome": "Record missing outcome",
                        "pending_analysis": "Approve pending analysis",
                        "planned_lesson": "Planned lesson",
                        "review_due": "Review due",
                    }
                    lines.extend(
                        [
                            "",
                            *[
                                f"{index}. {names[item['kind']]}"
                                + (f" · {item['display_name']}" if item["class_id"] else "")
                                for index, item in enumerate(items, 1)
                            ],
                        ]
                    )
                else:
                    lines.extend(["", "Nothing is waiting. Open a class and plan the next lesson."])
            await _safe_edit(query, "\n".join(lines), today_queue_keyboard(items, lang=lang))
            return

        state = _active_state(context)
        lesson_record = None
        outcome_result_code = None
        outcome_mask = 0
        outcome_option_code = None
        outcome_completion_code = None
        reminder_choice = None
        if action in {
            "taught", "canask", "canyes", "ostart", "oedit", "onote",
            "onclear", "oskip", "oremind",
        }:
            lesson_id = _decode_positive_base36(object_id)
            lesson_record = get_owned_class_lesson(
                telegram_user_id=user.id, lesson_id=lesson_id
            )
            if lesson_record is None:
                await _recover(query, context, lang=lang)
                return
            class_id = int(lesson_record["class_id"])
        elif action == "ores":
            outcome_result_code = object_id[0]
            if outcome_result_code not in OUTCOME_RESULT_CODES:
                raise ValueError("Invalid outcome result.")
            lesson_id = _decode_positive_base36(object_id[1:])
            lesson_record = get_owned_class_lesson(
                telegram_user_id=user.id, lesson_id=lesson_id
            )
            if lesson_record is None:
                await _recover(query, context, lang=lang)
                return
            class_id = int(lesson_record["class_id"])
        elif action == "odiff":
            outcome_option_code = object_id[0]
            outcome_result_code = object_id[1]
            outcome_mask = int(object_id[2:4], 36)
            if outcome_option_code not in {"l", "i", "p", "t", "m", "a"} or outcome_result_code not in OUTCOME_RESULT_CODES:
                raise ValueError("Invalid difficulty selection.")
            lesson_id = _decode_positive_base36(object_id[4:])
            lesson_record = get_owned_class_lesson(
                telegram_user_id=user.id, lesson_id=lesson_id
            )
            if lesson_record is None:
                await _recover(query, context, lang=lang)
                return
            class_id = int(lesson_record["class_id"])
        elif action in {"odone", "odnext"}:
            outcome_result_code = object_id[0]
            outcome_mask = int(object_id[1:3], 36)
            if outcome_result_code not in OUTCOME_RESULT_CODES:
                raise ValueError("Invalid outcome result.")
            lesson_id = _decode_positive_base36(object_id[3:])
            lesson_record = get_owned_class_lesson(
                telegram_user_id=user.id, lesson_id=lesson_id
            )
            if lesson_record is None:
                await _recover(query, context, lang=lang)
                return
            class_id = int(lesson_record["class_id"])
        elif action == "ocomp":
            outcome_completion_code = object_id[0]
            outcome_result_code = object_id[1]
            outcome_mask = int(object_id[2:4], 36)
            if outcome_completion_code not in OUTCOME_COMPLETION_CODES or outcome_result_code not in OUTCOME_RESULT_CODES:
                raise ValueError("Invalid outcome completion.")
            lesson_id = _decode_positive_base36(object_id[4:])
            lesson_record = get_owned_class_lesson(
                telegram_user_id=user.id, lesson_id=lesson_id
            )
            if lesson_record is None:
                await _recover(query, context, lang=lang)
                return
            class_id = int(lesson_record["class_id"])
        elif action == "orsave":
            reminder_choice = OUTCOME_REMINDER_CODES.get(object_id[0])
            if reminder_choice is None:
                raise ValueError("Invalid reminder choice.")
            lesson_id = _decode_positive_base36(object_id[1:])
            lesson_record = get_owned_class_lesson(
                telegram_user_id=user.id, lesson_id=lesson_id
            )
            if lesson_record is None:
                await _recover(query, context, lang=lang)
                return
            class_id = int(lesson_record["class_id"])
        elif action in {"nlrec", "nlmode", "nlprio", "nlsrc", "nlwhy", "nlgen", "nlign", "nlman"}:
            rec_id = _decode_positive_base36(object_id)
            rec_record = get_recommendation(
                telegram_user_id=user.id, recommendation_id=rec_id
            )
            if rec_record is None:
                await _recover(query, context, lang=lang)
                return
            class_id = int(rec_record["class_id"])
        elif action == "nlmset":
            selected_mode_code = object_id[0]
            rec_id = _decode_positive_base36(object_id[1:])
            rec_record = get_recommendation(
                telegram_user_id=user.id, recommendation_id=rec_id
            )
            if rec_record is None or selected_mode_code not in NEXT_LESSON_MODE_CODES:
                await _recover(query, context, lang=lang)
                return
            class_id = int(rec_record["class_id"])
        elif action == "nlpset":
            selected_prio_code = object_id[0]
            rec_id = _decode_positive_base36(object_id[1:])
            rec_record = get_recommendation(
                telegram_user_id=user.id, recommendation_id=rec_id
            )
            if rec_record is None or selected_prio_code not in NEXT_LESSON_PRIO_CODES:
                await _recover(query, context, lang=lang)
                return
            class_id = int(rec_record["class_id"])
        elif action == "nltog":
            source_link_id = _decode_positive_base36(object_id)
            rec_record = toggle_recommendation_source(
                telegram_user_id=user.id, source_link_id=source_link_id
            )
            if rec_record is None:
                await _recover(query, context, lang=lang)
                return
            class_id = int(rec_record["class_id"])
        elif action == "nlfa":
            followup_accepted = object_id[0] == "1"
            plan_id = _decode_positive_base36(object_id[1:])
            plan_row = record_next_lesson_followup(
                telegram_user_id=user.id, plan_id=plan_id, accepted=followup_accepted
            )
            if not plan_row:
                await _recover(query, context, lang=lang)
                return
            revision = int(revision_text, 36)
            class_id = int(state["id"]) if state else 0
            if class_id == 0:
                snapshot = class_dashboard_snapshot(telegram_user_id=user.id, class_id=int(object_id[1:], 36) if len(object_id) > 1 else 0)
                if snapshot:
                    class_id = int(snapshot["class"]["id"])
            feedback_msg = (
                "✅ سپاس از بازخورد شما! این نظر برای بهبود پیشنهادات درس‌های آینده ثبت شد."
                if lang == "fa"
                else (
                    "✅ Thank you! Your feedback on this lesson recommendation was saved.\n\n"
                    "TeacherOS uses this to improve future suggestions."
                )
            )
            done_btn = "تایید · بازگشت به کلاس" if lang == "fa" else "Done · Class Home"
            await _safe_edit(
                query,
                feedback_msg,
                InlineKeyboardMarkup([[InlineKeyboardButton(done_btn, callback_data=_cb("open", class_id or 1, revision))]]),
            )
            return
        elif action in {"edset", "edmulti", "edsave"}:
            edit_state = context.user_data.get("class_edit")
            if not isinstance(edit_state, dict):
                await _recover(query, context, lang=lang)
                return
            class_id = int(edit_state["class_id"])
        elif action == "pfedit" and state:
            class_id = int(state["id"])
        elif object_id == "0" and state:
            class_id = int(state["id"])
        else:
            class_id = int(object_id, 36)
        revision = int(revision_text, 36)

        if action == "open":
            await _render_dashboard(
                query, context, telegram_user_id=user.id, class_id=class_id,
                expected_revision=revision or None,
            )
            return

        if action == "m_cls":
            snapshot = class_dashboard_snapshot(telegram_user_id=user.id, class_id=class_id)
            if snapshot is None:
                await _recover(query, context, lang=lang)
                return
            class_record = snapshot["class"]
            context.user_data.clear()
            context.user_data["lang"] = lang
            context.user_data["active_class"] = {
                "id": class_id,
                "display_name": str(class_record["display_name"]),
                "revision": int(class_record["revision"]),
            }
            await _safe_edit(
                query,
                _menu_class_text(str(class_record["display_name"]), lang=lang),
                class_menu_class_keyboard(class_id, int(class_record["revision"]), lang=lang),
            )
            return

        if action == "m_pln":
            snapshot = class_dashboard_snapshot(telegram_user_id=user.id, class_id=class_id)
            if snapshot is None:
                await _recover(query, context, lang=lang)
                return
            class_record = snapshot["class"]
            context.user_data.clear()
            context.user_data["lang"] = lang
            context.user_data["active_class"] = {
                "id": class_id,
                "display_name": str(class_record["display_name"]),
                "revision": int(class_record["revision"]),
            }
            await _safe_edit(
                query,
                _menu_planning_text(str(class_record["display_name"]), lang=lang),
                class_menu_planning_keyboard(class_id, int(class_record["revision"]), lang=lang),
            )
            return

        if action == "m_ass":
            snapshot = class_dashboard_snapshot(telegram_user_id=user.id, class_id=class_id)
            if snapshot is None:
                await _recover(query, context, lang=lang)
                return
            class_record = snapshot["class"]
            context.user_data.clear()
            context.user_data["lang"] = lang
            context.user_data["active_class"] = {
                "id": class_id,
                "display_name": str(class_record["display_name"]),
                "revision": int(class_record["revision"]),
            }
            await _safe_edit(
                query,
                _menu_assessment_text(str(class_record["display_name"]), lang=lang),
                class_menu_assessment_keyboard(class_id, int(class_record["revision"]), lang=lang),
            )
            return

        if action == "m_tls":
            snapshot = class_dashboard_snapshot(telegram_user_id=user.id, class_id=class_id)
            if snapshot is None:
                await _recover(query, context, lang=lang)
                return
            class_record = snapshot["class"]
            context.user_data.clear()
            context.user_data["lang"] = lang
            context.user_data["active_class"] = {
                "id": class_id,
                "display_name": str(class_record["display_name"]),
                "revision": int(class_record["revision"]),
            }
            await _safe_edit(
                query,
                _advanced_tools_text(snapshot, lang=lang),
                class_menu_tools_keyboard(class_id, int(class_record["revision"]), lang=lang),
            )
            return

        if action == "adv":
            snapshot = class_dashboard_snapshot(telegram_user_id=user.id, class_id=class_id)
            if snapshot is None:
                await _recover(query, context, lang=lang)
                return
            class_record = snapshot["class"]
            context.user_data.clear()
            context.user_data["lang"] = lang
            context.user_data["active_class"] = {
                "id": class_id,
                "display_name": str(class_record["display_name"]),
                "revision": int(class_record["revision"]),
            }
            text = _advanced_tools_text(snapshot, lang=lang)
            markup = class_advanced_tools_keyboard(class_id, int(class_record["revision"]), lang=lang)
            await _safe_edit(query, text, markup)
            return

        snapshot = class_dashboard_snapshot(telegram_user_id=user.id, class_id=class_id)
        if snapshot is None or int(snapshot["class"]["revision"]) != revision:
            await _recover(query, context, lang=lang)
            return
        class_record = snapshot["class"]
        context.user_data["active_class"] = {
            "id": class_id,
            "display_name": str(class_record["display_name"]),
            "revision": revision,
        }

        if action == "details":
            await _safe_edit(
                query, _details_text(snapshot, lang=lang),
                class_details_keyboard(class_id, revision, archived=class_record["status"] == "archived", lang=lang),
            )
            return
        if action == "hist":
            lessons = list_lesson_history(
                telegram_user_id=user.id, class_id=class_id
            )
            metrics = lesson_conversion_metrics(
                telegram_user_id=user.id, class_id=class_id
            )
            await _safe_edit(
                query,
                _history_text(str(class_record["display_name"]), lessons, metrics, lang=lang),
                lesson_history_keyboard(lessons, class_id, revision, lang=lang),
            )
            return
        if action == "outcome":
            if class_record["status"] != "active":
                await _recover(query, context, lang=lang)
                return
            outcome_lessons = list_outcome_lessons(
                telegram_user_id=user.id, class_id=class_id
            )
            outcome_metrics = outcome_recording_metrics(
                telegram_user_id=user.id, class_id=class_id
            )
            await _safe_edit(
                query,
                _outcome_picker_text(
                    str(class_record["display_name"]), outcome_lessons, outcome_metrics, lang=lang
                ),
                outcome_lesson_picker_keyboard(outcome_lessons, class_id, revision, lang=lang),
            )
            return
        if action in {
            "ostart", "ores", "odiff", "odone", "odnext", "ocomp", "oedit",
            "onote", "onclear", "oskip", "oremind", "orsave",
        }:
            if (
                lesson_record is None
                or lesson_record.get("lifecycle_state") != "taught"
                or class_record["status"] != "active"
            ):
                await _recover(query, context, lang=lang)
                return
        if action in {"ostart", "oedit"}:
            existing_outcome = get_lesson_outcome(
                telegram_user_id=user.id, lesson_id=int(lesson_record["id"])
            )
            notice = (
                ("حالت ویرایش: نتیجه این جلسه به‌روزرسانی می‌شود." if lang == "fa" else "Correction mode: the next save updates the same outcome and keeps a fact revision.")
                if existing_outcome is not None else None
            )
            await _safe_edit(
                query,
                _outcome_result_text(lesson_record, notice=notice, lang=lang),
                outcome_result_keyboard(int(lesson_record["id"]), revision, lang=lang),
            )
            return
        if action == "ores":
            await _safe_edit(
                query,
                _outcome_difficulty_text(lesson_record, 0, lang=lang),
                outcome_difficulty_keyboard(
                    int(lesson_record["id"]), str(outcome_result_code), 0, revision, lang=lang
                ),
            )
            return
        if action == "odiff":
            bit = OUTCOME_DIFFICULTY_OPTION_BITS[str(outcome_option_code)]
            outcome_mask ^= 1 << bit
            await _safe_edit(
                query,
                _outcome_difficulty_text(lesson_record, outcome_mask, lang=lang),
                outcome_difficulty_keyboard(
                    int(lesson_record["id"]), str(outcome_result_code), outcome_mask, revision, lang=lang
                ),
            )
            return
        if action in {"odone", "odnext"}:
            if action == "odnext" and outcome_mask == 0:
                hint = "لطفاً حداقل یک مورد را انتخاب کنید یا گزینه بدون چالش را بزنید." if lang == "fa" else "Choose at least one category, or tap No major difficulty."
                await _safe_edit(
                    query,
                    _outcome_difficulty_text(
                        lesson_record, 0,
                        notice=hint,
                        lang=lang,
                    ),
                    outcome_difficulty_keyboard(
                        int(lesson_record["id"]), str(outcome_result_code), 0, revision, lang=lang
                    ),
                )
                return
            difficulties = _difficulty_values(outcome_mask)
            await _safe_edit(
                query,
                _outcome_completion_text(lesson_record, difficulties, lang=lang),
                outcome_completion_keyboard(
                    int(lesson_record["id"]), str(outcome_result_code), outcome_mask, revision, lang=lang
                ),
            )
            return
        if action == "ocomp":
            outcome, changed = save_outcome_facts(
                telegram_user_id=user.id,
                lesson_id=int(lesson_record["id"]),
                result=OUTCOME_RESULT_CODES[str(outcome_result_code)],
                difficulty_categories=_difficulty_values(outcome_mask),
                completion_status=OUTCOME_COMPLETION_CODES[str(outcome_completion_code)],
            )
            if outcome is None:
                await _recover(query, context, lang=lang)
                return
            metrics = outcome_recording_metrics(
                telegram_user_id=user.id, class_id=class_id
            )
            if lang == "fa":
                notice = "نتیجه ذخیره شد. در صورت تمایل می‌توانید یادداشت اضافه کنید." if changed else "این نتیجه قبلاً ثبت شده بود."
            else:
                notice = (
                    "Saved before asking for prose. Add a note only if it helps."
                    if changed else "No duplicate was created; these facts were already saved."
                )
            await _safe_edit(
                query,
                _outcome_summary_text(outcome, metrics, notice=notice, lang=lang),
                outcome_summary_keyboard(
                    int(lesson_record["id"]), class_id, revision,
                    has_note=bool(outcome.get("notes")),
                    lang=lang,
                ),
            )
            return
        if action == "onote":
            outcome = get_lesson_outcome(
                telegram_user_id=user.id, lesson_id=int(lesson_record["id"])
            )
            if outcome is None:
                await _recover(query, context, lang=lang)
                return
            context.user_data["outcome_note"] = {
                "state": "text", "lesson_id": int(lesson_record["id"]),
                "class_id": class_id, "revision": revision,
            }
            note_prompt = (
                "📝 یادداشت معلم (اختیاری)\n\nمی‌توانید نکته یا بازخوردی بنویسید (حداکثر ۱۰۰۰ کاراکتر) یا دکمه رد شدن را بزنید.\n\n💡 نکته: از وارد کردن نام یا اطلاعات شخصی زبان‌آموزان خودداری فرمایید."
                if lang == "fa"
                else (
                    "📝 Optional teacher note\n\nType up to 1,000 characters, or skip. "
                    "Do not include student names, email addresses, phone numbers, health, or disability information."
                )
            )
            await _safe_edit(
                query,
                note_prompt,
                outcome_note_keyboard(
                    int(lesson_record["id"]), class_id, revision,
                    has_note=bool(outcome.get("notes")),
                    lang=lang,
                ),
            )
            return
        if action == "onclear":
            outcome, changed = update_outcome_note(
                telegram_user_id=user.id, lesson_id=int(lesson_record["id"]), note=None
            )
            if outcome is None:
                await _recover(query, context, lang=lang)
                return
            context.user_data.pop("outcome_note", None)
            metrics = outcome_recording_metrics(
                telegram_user_id=user.id, class_id=class_id
            )
            clear_notice = ("یادداشت حذف شد." if changed else "یادداشتی ثبت نشده بود.") if lang == "fa" else ("Optional note cleared." if changed else "The optional note was already empty.")
            await _safe_edit(
                query,
                _outcome_summary_text(
                    outcome, metrics,
                    notice=clear_notice,
                    lang=lang,
                ),
                outcome_summary_keyboard(
                    int(lesson_record["id"]), class_id, revision, has_note=False, lang=lang
                ),
            )
            return
        if action == "oskip":
            context.user_data.pop("outcome_note", None)
            outcome = get_lesson_outcome(
                telegram_user_id=user.id, lesson_id=int(lesson_record["id"])
            )
            if outcome is None:
                await _render_dashboard(
                    query, context, telegram_user_id=user.id, class_id=class_id,
                    expected_revision=revision,
                )
                return
            metrics = outcome_recording_metrics(
                telegram_user_id=user.id, class_id=class_id
            )
            skip_notice = "یادداشت ثبت نشد." if lang == "fa" else "Optional note skipped."
            await _safe_edit(
                query,
                _outcome_summary_text(outcome, metrics, notice=skip_notice, lang=lang),
                outcome_summary_keyboard(
                    int(lesson_record["id"]), class_id, revision,
                    has_note=bool(outcome.get("notes")),
                    lang=lang,
                ),
            )
            return
        if action == "oremind":
            existing_outcome = get_lesson_outcome(
                telegram_user_id=user.id, lesson_id=int(lesson_record["id"])
            )
            if existing_outcome is not None:
                metrics = outcome_recording_metrics(
                    telegram_user_id=user.id, class_id=class_id
                )
                already_notice = "نتیجه این جلسه قبلاً ثبت شده است." if lang == "fa" else "This outcome is already recorded; no reminder is needed."
                await _safe_edit(
                    query,
                    _outcome_summary_text(
                        existing_outcome, metrics,
                        notice=already_notice,
                        lang=lang,
                    ),
                    outcome_summary_keyboard(
                        int(lesson_record["id"]), class_id, revision,
                        has_note=bool(existing_outcome.get("notes")),
                        lang=lang,
                    ),
                )
                return
            remind_prompt = (
                f"⏰ یادآوری ثبت بازخورد\n\nجلسه #{lesson_record['id']}: "
                f"{_short(lesson_record['title'], 52)}\n\nیک زمان را انتخاب کنید تا دستیار هوشمند به شما یادآوری ارسال کند:"
                if lang == "fa"
                else (
                    f"⏰ One-shot outcome reminder\n\nLesson #{lesson_record['id']}: "
                    f"{_short(lesson_record['title'], 52)}\n\nChoose a local time. "
                    "TeacherOS sends only this explicit reminder; it does not repeat automatically."
                )
            )
            await _safe_edit(
                query,
                remind_prompt,
                outcome_reminder_keyboard(int(lesson_record["id"]), revision, lang=lang),
            )
            return
        if action == "orsave":
            reminder_result = schedule_outcome_reminder(
                telegram_user_id=user.id, lesson_id=int(lesson_record["id"]),
                choice=str(reminder_choice),
            )
            reminder = reminder_result.get("reminder") or {}
            if reminder_result["status"] in {"scheduled", "already_scheduled"}:
                due_text = str(reminder.get("next_prompt_at_utc") or "")
                try:
                    due_local = datetime.fromisoformat(due_text.replace("Z", "+00:00")).astimezone(get_usage_timezone())
                    due_text = due_local.strftime("%Y-%m-%d %H:%M") + f" ({USAGE_TIMEZONE})"
                except ValueError:
                    due_text = _short(due_text, 32)
                if lang == "fa":
                    notice = "یادآوری از قبل تنظیم شده بود." if reminder_result["status"] == "already_scheduled" else "یادآوری با موفقیت تنظیم شد."
                    rem_msg = f"✅ {notice}\n\nزمان: {due_text}\nجلسه: {_short(lesson_record['title'], 52)}"
                else:
                    notice = (
                        "Reminder already scheduled; duplicate callback ignored."
                        if reminder_result["status"] == "already_scheduled"
                        else "One reminder scheduled. It will not repeat unless you explicitly snooze it."
                    )
                    rem_msg = f"✅ {notice}\n\nDue: {due_text}\nLesson: {_short(lesson_record['title'], 52)}"
                await _safe_edit(
                    query,
                    rem_msg,
                    outcome_reminder_keyboard(int(lesson_record["id"]), revision, lang=lang),
                )
                return
            if lang == "fa":
                message = "این جلسه از قبل دارای نتیجه ثبت‌شده است." if reminder_result["status"] == "completed" else "سقف مجاز یادآوری پر شده است."
            else:
                message = (
                    "This lesson already has an outcome; no reminder was created."
                    if reminder_result["status"] == "completed"
                    else "Reminder limit reached. Open the class when you are ready; no more prompts will be sent."
                )
            await _safe_edit(
                query, f"ℹ {message}",
                outcome_result_keyboard(int(lesson_record["id"]), revision, lang=lang),
            )
            return
        if action == "canask":
            if lesson_record is None or lesson_record.get("lifecycle_state") != "planned":
                await _recover(query, context, lang=lang)
                return
            if lang == "fa":
                cancel_prompt = f"طرح درس جلسه #{lesson_record['id']} لغو شود؟\n\n{lesson_record['title']}\n\nاین طرح به عنوان لغوشده ثبت می‌شود و محتوای تولیدشده آن در کتابخانه باقی می‌ماند."
            else:
                cancel_prompt = (
                    f"Cancel planned lesson #{lesson_record['id']}?\n\n"
                    f"{lesson_record['title']}\n\n"
                    "The plan becomes Cancelled and remains auditable. Its generated resource stays in the library."
                )
            await _safe_edit(
                query,
                cancel_prompt,
                lesson_cancel_confirmation_keyboard(
                    int(lesson_record["id"]), class_id, revision, lang=lang
                ),
            )
            return
        if action in {"taught", "canyes"}:
            if lesson_record is None:
                await _recover(query, context, lang=lang)
                return
            if action == "taught":
                updated_lesson, changed = mark_lesson_taught(
                    telegram_user_id=user.id, lesson_id=int(lesson_record["id"])
                )
                if lang == "fa":
                    notice = "✅ به عنوان تدریس‌شده ثبت شد. اکنون می‌توانید بازخورد جلسه را ثبت کنید." if changed else "این جلسه قبلاً به عنوان تدریس‌شده علامت‌گذاری شده بود."
                else:
                    notice = (
                        "✅ Marked as taught. Outcome and review workflows may now use this fact."
                        if changed else
                        "ℹ No duplicate was created. This lesson was already taught or was not planned."
                    )
            else:
                updated_lesson, changed = cancel_planned_lesson(
                    telegram_user_id=user.id, lesson_id=int(lesson_record["id"])
                )
                if lang == "fa":
                    notice = "✅ این طرح درس لغو شد. محتوای آموزشی آن در کتابخانه حفظ شد." if changed else "این طرح درس قبلاً لغو شده بود."
                else:
                    notice = (
                        "✅ Plan cancelled. The generated resource and audit record were kept."
                        if changed else
                        "ℹ No duplicate change was made. This plan was already cancelled or was not active."
                    )
            if updated_lesson is None:
                await _recover(query, context, lang=lang)
                return
            if action == "taught" and updated_lesson.get("lifecycle_state") == "taught":
                await _safe_edit(
                    query,
                    _outcome_result_text(updated_lesson, notice=notice, lang=lang),
                    outcome_result_keyboard(int(updated_lesson["id"]), revision, lang=lang),
                )
                return
            lessons = list_lesson_history(
                telegram_user_id=user.id, class_id=class_id
            )
            metrics = lesson_conversion_metrics(
                telegram_user_id=user.id, class_id=class_id
            )
            await _safe_edit(
                query,
                _history_text(
                    str(class_record["display_name"]), lessons, metrics, notice=notice, lang=lang
                ),
                lesson_history_keyboard(lessons, class_id, revision, lang=lang),
            )
            return
        if action == "profile":
            context.user_data.pop("class_edit", None)
            prof_title = "پروفایل کلاس" if lang == "fa" else "Class Profile"
            text = "\n".join([f"👤 {prof_title} · {class_record['display_name']}", "", *_profile_lines(class_record, lang=lang)])
            if class_record["status"] == "archived":
                text += "\n\nپروفایل کلاس‌های بایگانی‌شده فقط خواندنی است." if lang == "fa" else "\n\nArchived profiles are read-only until restored."
            await _safe_edit(
                query, text,
                class_profile_keyboard(class_id, revision, archived=class_record["status"] == "archived", lang=lang),
            )
            return
        if action in {"archask", "restask"}:
            archive = action == "archask"
            if archive != (class_record["status"] == "active"):
                await _recover(query, context, lang=lang)
                return
            if lang == "fa":
                verb = "بایگانی کلاس" if archive else "بازیابی کلاس"
                effect = (
                    "این کلاس از صفحه کلاس‌های فعال خارج می‌شود، اما کلیه محتواها و سوابق آن کاملاً حفظ خواهد شد."
                    if archive else "این کلاس مجدداً به فهرست کلاس‌های فعال بازمی‌گردد."
                )
                conf_msg = f"{verb} {class_record['display_name']}؟\n\n{effect}"
            else:
                verb = "Archive" if archive else "Restore"
                effect = (
                    "It leaves the active workspace, but every linked material, lesson, outcome, and action item stays intact."
                    if archive else "It returns to the active workspace with all linked history intact."
                )
                conf_msg = f"{verb} {class_record['display_name']}?\n\n{effect}"
            await _safe_edit(
                query, conf_msg,
                confirmation_keyboard(class_id, revision, archive=archive, lang=lang),
            )
            return
        if action in {"archyes", "restyes"}:
            updated = set_class_archived(
                telegram_user_id=user.id,
                class_id=class_id,
                archive=action == "archyes",
                expected_revision=revision,
            )
            if updated is None:
                await _recover(query, context, lang=lang)
                return
            context.user_data.clear()
            context.user_data["lang"] = lang
            if lang == "fa":
                arch_msg = ("✅ کلاس بایگانی شد" if action == "archyes" else "✅ کلاس با موفقیت بازیابی شد") + f" · {updated['display_name']}\n\nکلیه سوابق و محتواهای کلاس حفظ شده است."
            else:
                arch_msg = (
                    ("✅ Class archived" if action == "archyes" else "✅ Class restored")
                    + f" · {updated['display_name']}\n\nAll linked materials and history were preserved."
                )
            await _safe_edit(
                query,
                arch_msg,
                (
                    archived_dashboard_keyboard(class_id, int(updated["revision"]), lang=lang)
                    if action == "archyes"
                    else class_dashboard_keyboard(class_id, int(updated["revision"]), lang=lang)
                ),
            )
            return
        if action == "pfedit":
            if class_record["status"] != "active" or object_id not in FIELD_CODES:
                await _recover(query, context, lang=lang)
                return
            field_code = object_id
            field = FIELD_CODES[field_code]
            edit_state = {"class_id": class_id, "revision": revision, "field_code": field_code, "field": field}
            context.user_data["class_edit"] = edit_state
            if field_code in {"nm", "bk"}:
                edit_state["state"] = "text"
                if lang == "fa":
                    prompt = (
                        "یک عنوان یا برچسب کوتاه برای کلاس بنویسید (مثلاً «کلاس خصوصی آیلتس»). از نوشتن نام یا مشخصات خصوصی زبان‌آموزان خودداری فرمایید."
                        if field_code == "nm"
                        else "نام کتاب و درس را بنویسید (مثلاً «Touchstone 2 | Unit 3») یا دکمه پاک کردن را بزنید."
                    )
                    title_text = "نام کلاس" if field_code == "nm" else "کتاب و درس"
                else:
                    prompt = (
                        "Type one short private class label. Never enter student names or sensitive data."
                        if field_code == "nm"
                        else "Type Coursebook | Unit as one short phrase, or choose Clear."
                    )
                    title_text = field.replace('_', ' ').title()
                await _safe_edit(query, f"✏ Edit {title_text}\n\n{prompt}", edit_text_keyboard(class_id, revision, coursebook=field_code == "bk", lang=lang))
                return
            if field_code in SINGLE_CHOICES:
                choices, _ = SINGLE_CHOICES[field_code]
                encoded = tuple((field_code + code, label) for code, label in choices)
                sub_title = "یک گزینه را انتخاب کنید." if lang == "fa" else "Save one choice."
                await _safe_edit(query, f"✏ Edit {field.replace('_', ' ').title()}\n\n{sub_title}", edit_choice_keyboard(encoded, revision, lang=lang))
                return
            choices, profile_key = MULTI_CHOICES[field_code]
            selected = list(_profile_data(class_record).get(profile_key, []))
            edit_state["selected"] = selected
            sub_multi = "گزینه‌های مدنظر را انتخاب کرده و سپس دکمه ذخیره را بزنید." if lang == "fa" else "Choose options, then Save this field."
            await _safe_edit(query, f"✏ Edit {field.replace('_', ' ').title()}\n\n{sub_multi}", edit_multi_keyboard(field_code, choices, selected, revision, lang=lang))
            return
        if action == "edset":
            edit_state = context.user_data.get("class_edit")
            field_code = str(edit_state.get("field_code"))
            if not object_id.startswith(field_code) or field_code not in SINGLE_CHOICES:
                await _recover(query, context, lang=lang)
                return
            _, value_map = SINGLE_CHOICES[field_code]
            value = value_map.get(object_id[len(field_code):])
            updated = update_profile_field(
                telegram_user_id=user.id, class_id=class_id,
                field=FIELD_CODES[field_code], value=value, expected_revision=revision,
            )
            if updated is None:
                await _recover(query, context, lang=lang)
                return
            context.user_data.pop("class_edit", None)
            new_revision = int(updated["revision"])
            context.user_data["active_class"] = {"id": class_id, "display_name": updated["display_name"], "revision": new_revision}
            prof_updated_msg = "✅ مشخصات کلاس به‌روزرسانی شد\n\n" if lang == "fa" else "✅ Profile field updated\n\n"
            await _safe_edit(query, prof_updated_msg + "\n".join(_profile_lines(updated, lang=lang)), class_profile_keyboard(class_id, new_revision, archived=False, lang=lang))
            return
        if action == "edmulti":
            edit_state = context.user_data.get("class_edit")
            field_code = str(edit_state.get("field_code"))
            if not object_id.startswith(field_code) or field_code not in MULTI_CHOICES:
                await _recover(query, context, lang=lang)
                return
            code = object_id[len(field_code):]
            choices, _ = MULTI_CHOICES[field_code]
            allowed = {choice for choice, _ in choices}
            if code not in allowed:
                await _recover(query, context, lang=lang)
                return
            selected = list(edit_state.get("selected", []))
            if code in {"ns", "none"}:
                selected = [] if code in selected else [code]
            else:
                selected = [item for item in selected if item not in {"ns", "none"}]
                if code in selected:
                    selected.remove(code)
                else:
                    selected.append(code)
            edit_state["selected"] = selected
            sub_multi = "گزینه‌های مدنظر را انتخاب کرده و سپس دکمه ذخیره را بزنید." if lang == "fa" else "Choose options, then Save this field."
            await _safe_edit(query, f"✏ Edit {FIELD_CODES[field_code].replace('_', ' ').title()}\n\n{sub_multi}", edit_multi_keyboard(field_code, choices, selected, revision, lang=lang))
            return
        if action == "edsave":
            edit_state = context.user_data.get("class_edit")
            field_code = str(edit_state.get("field_code"))
            selected = list(edit_state.get("selected", []))
            if object_id != field_code or field_code not in MULTI_CHOICES or not selected:
                req_one = "لطفاً حداقل یک گزینه را انتخاب کنید." if lang == "fa" else "Choose at least one option, including Not sure if needed."
                await _safe_edit(query, req_one, edit_multi_keyboard(field_code, MULTI_CHOICES[field_code][0], selected, revision, lang=lang))
                return
            updated = update_profile_field(
                telegram_user_id=user.id, class_id=class_id,
                field=FIELD_CODES[field_code], value=selected, expected_revision=revision,
            )
            if updated is None:
                await _recover(query, context, lang=lang)
                return
            context.user_data.pop("class_edit", None)
            new_revision = int(updated["revision"])
            context.user_data["active_class"] = {"id": class_id, "display_name": updated["display_name"], "revision": new_revision}
            prof_updated_msg = "✅ مشخصات کلاس به‌روزرسانی شد\n\n" if lang == "fa" else "✅ Profile field updated\n\n"
            await _safe_edit(query, prof_updated_msg + "\n".join(_profile_lines(updated, lang=lang)), class_profile_keyboard(class_id, new_revision, archived=False, lang=lang))
            return
        if action == "edclear":
            edit_state = context.user_data.get("class_edit")
            if not isinstance(edit_state, dict) or edit_state.get("field_code") != "bk":
                await _recover(query, context, lang=lang)
                return
            updated = update_profile_field(
                telegram_user_id=user.id, class_id=class_id, field="coursebook",
                value={"coursebook_state": "skipped"}, expected_revision=revision,
            )
            if updated is None:
                await _recover(query, context, lang=lang)
                return
            context.user_data.pop("class_edit", None)
            new_revision = int(updated["revision"])
            book_clr_msg = "✅ کتاب و سرفصل پاک شد\n\n" if lang == "fa" else "✅ Coursebook cleared\n\n"
            await _safe_edit(query, book_clr_msg + "\n".join(_profile_lines(updated, lang=lang)), class_profile_keyboard(class_id, new_revision, archived=False, lang=lang))
            return

        if action == "library":
            records = list_class_materials(
                telegram_user_id=user.id, class_id=class_id, limit=20
            )
            lines = [f"• #{item['id']} · {item['title']}" for item in records]
            if lang == "fa":
                lib_text = f"📁 کتابخانه منابع · {class_record['display_name']}\n\n" + ("\n".join(lines) if lines else "هنوز محتوایی برای این کلاس تولید نشده است.")
            else:
                lib_text = f"📁 {class_record['display_name']} Library\n\n" + ("\n".join(lines) if lines else "No class-linked materials yet.")
            await _safe_edit(
                query,
                lib_text,
                class_library_keyboard(records, class_id, revision, lang=lang),
            )
            return
        if action == "diff":
            materials = list_class_materials(
                telegram_user_id=user.id, class_id=class_id, limit=10
            )
            if not materials:
                if lang == "fa":
                    diff_empty_msg = (
                        f"╭─ 🎯 تطبیق و شخصی‌سازی محتوا ─╮\n"
                        f"│ 🏫 {class_record['display_name']}\n"
                        f"╰────────────────────────────╯\n\n"
                        "موتور تطبیق محتوا به شما امکان می‌دهد برای سطوح مختلف، زبان‌آموزان نیازمند تمرین بیشتر، یا پیشتازان، محتوا را شخصی‌سازی کنید.\n\n"
                        "⚠️ هنوز محتوایی برای این کلاس تولید نشده است. ابتدا یک طرح درس آماده کنید!"
                    )
                else:
                    diff_empty_msg = (
                        f"╭─ 🎯 Differentiate & Adapt ─╮\n"
                        f"│ 🏫 {class_record['display_name']}\n"
                        f"╰────────────────────────────╯\n\n"
                        "The Differentiation Engine addresses mixed-ability classes, fast finishers, "
                        "struggling learners, and accessibility needs with 3-tier routes and 1-tap adaptations.\n\n"
                        "⚠️ No materials generated for this class yet. Plan a lesson or create materials first!"
                    )
                await _safe_edit(
                    query,
                    diff_empty_msg,
                    class_action_keyboard(class_id, revision, "create", class_aware=True, lang=lang),
                )
                return

            rows = []
            for mat in materials[:6]:
                mat_id = int(mat["id"])
                mat_title = str(mat.get("title", f"Material #{mat_id}"))[:28]
                mat_b36 = _base36(mat_id)
                tier_btn = f"🎯 سطح‌بندی: {mat_title}" if lang == "fa" else f"🎯 3-Tier: {mat_title}"
                adapt_btn = "⚡ تطبیق" if lang == "fa" else "⚡ Adapt"
                rows.append([
                    InlineKeyboardButton(tier_btn, callback_data=f"v1|df|gen|{mat_b36}|sup"),
                    InlineKeyboardButton(adapt_btn, callback_data=f"v1|ad|menu|{mat_b36}"),
                ])
            ch_btn = "⬅ بازگشت به کلاس" if lang == "fa" else "⬅ Class Home"
            home_btn = "🏠 منوی اصلی" if lang == "fa" else "🏠 Main Menu"
            rows.append([
                InlineKeyboardButton(ch_btn, callback_data=_cb("open", class_id, revision)),
                InlineKeyboardButton(home_btn, callback_data="v1|cl|home|0|0"),
            ])
            if lang == "fa":
                diff_menu_msg = (
                    f"╭─ 🎯 تطبیق و شخصی‌سازی محتوا ─╮\n"
                    f"│ 🏫 {class_record['display_name']}\n"
                    f"╰────────────────────────────╯\n\n"
                    "یک محتوا را برای شخصی‌سازی انتخاب کنید:\n"
                    "• 🟢 پشتیبان: داربست آموزشی و راهنمای گام‌به‌گام\n"
                    "• 🟡 استاندارد: سطح پایه و اصلی کلاس\n"
                    "• 🟣 چالشی: تمرین‌های تکمیلی و پیشرفته‌تر\n"
                    "• ⚡ تطبیق سریع: کلاس شلوغ، کم‌امکانات، یا زبان‌آموزان سریع"
                )
            else:
                diff_menu_msg = (
                    f"╭─ 🎯 Differentiate & Adapt ─╮\n"
                    f"│ 🏫 {class_record['display_name']}\n"
                    f"╰────────────────────────────╯\n\n"
                    "Select a class material below to generate:\n"
                    "• 🟢 Support: Guided scaffolding & sentence frames\n"
                    "• 🟡 Core: Standard benchmark standard\n"
                    "• 🟣 Challenge: Higher-order extension\n"
                    "• ⚡ Adapt: 1-tap fast finisher, low-tech, large class, exam adaptations"
                )
            await _safe_edit(
                query,
                diff_menu_msg,
                InlineKeyboardMarkup(rows),
            )
            return
        if action in {"analyze", "evid"} and feature_enabled("evidence"):
            from evidence_keyboards import evidence_inbox_keyboard
            from evidence_service import list_evidence_batches
            batches = list_evidence_batches(telegram_user_id=user.id, class_id=class_id)
            if lang == "fa":
                text = (
                    f"📥 مدیریت شواهد یادگیری و تکالیف · {class_record['display_name']}\n\n"
                    "ثبت و بررسی نمونه تکالیف و فعالیت‌های کلاسی به صورت بی‌نام.\n\n"
                    "🔒 حریم خصوصی و امنیت:\n"
                    "• ثبت بدون نام حقیقی (زبان‌آموز الف، دانش‌آموز ۱)\n"
                    "• امکان حذف در هر زمان توسط معلم\n"
                    "• حذف خودکار پس از ۳۰ روز"
                )
            else:
                text = (
                    f"📥 Evidence Inbox · {class_record['display_name']}\n\n"
                    "Submit and manage anonymized student work (writing, speaking notes, quizzes).\n\n"
                    "🔒 Privacy Safeguards:\n"
                    "• Anonymous labels only (Student A, Student 1)\n"
                    "• Deletable at any time by teacher\n"
                    "• Automated privacy retention (30 days default)"
                )
            await _safe_edit(query, text, evidence_inbox_keyboard(class_id, revision, batches))
            return
        if action == "plan" and feature_enabled("continuity"):
            touch_class_activity(telegram_user_id=user.id, class_id=class_id)
            rec = get_or_create_recommendation(telegram_user_id=user.id, class_id=class_id)
            if rec is None:
                await _recover(query, context, lang=lang)
                return
            await _safe_edit(
                query,
                _next_lesson_rec_text(str(class_record["display_name"]), rec, lang=lang),
                next_lesson_recommendation_keyboard(rec, class_id, revision, lang=lang),
            )
            return
        if action == "nlrec":
            if rec_record is None:
                await _recover(query, context, lang=lang)
                return
            await _safe_edit(
                query,
                _next_lesson_rec_text(str(class_record["display_name"]), rec_record, lang=lang),
                next_lesson_recommendation_keyboard(rec_record, class_id, revision, lang=lang),
            )
            return
        if action == "nlwhy":
            if rec_record is None:
                await _recover(query, context, lang=lang)
                return
            await _safe_edit(
                query,
                _next_lesson_why_text(str(class_record["display_name"]), rec_record, lang=lang),
                next_lesson_why_keyboard(int(rec_record["id"]), revision, lang=lang),
            )
            return
        if action == "nlmode":
            if rec_record is None:
                await _recover(query, context, lang=lang)
                return
            await _safe_edit(
                query,
                _next_lesson_modes_text(str(class_record["display_name"]), rec_record, lang=lang),
                next_lesson_modes_keyboard(
                    int(rec_record["id"]), rec_record.get("selected_mode"), revision, lang=lang
                ),
            )
            return
        if action == "nlmset":
            mode_str = NEXT_LESSON_MODE_CODES[str(selected_mode_code)]
            updated_rec = select_recommendation_mode(
                telegram_user_id=user.id,
                recommendation_id=int(rec_record["id"]),
                mode=mode_str,
            )
            if updated_rec is None:
                await _recover(query, context, lang=lang)
                return
            mode_lbl = MODE_LABELS.get(mode_str, mode_str) if lang != "fa" else _human(mode_str, lang=lang)
            notice_m = f"✅ حالت تدریس روی «{mode_lbl}» تنظیم شد." if lang == "fa" else f"✅ Mode set to {mode_lbl}."
            await _safe_edit(
                query,
                _next_lesson_rec_text(
                    str(class_record["display_name"]),
                    updated_rec,
                    notice=notice_m,
                    lang=lang,
                ),
                next_lesson_recommendation_keyboard(updated_rec, class_id, revision, lang=lang),
            )
            return
        if action == "nlprio":
            if rec_record is None:
                await _recover(query, context, lang=lang)
                return
            await _safe_edit(
                query,
                _next_lesson_priorities_text(str(class_record["display_name"]), rec_record, lang=lang),
                next_lesson_priorities_keyboard(
                    int(rec_record["id"]),
                    str(rec_record.get("priority_mode", "balanced")),
                    revision,
                    lang=lang,
                ),
            )
            return
        if action == "nlpset":
            prio_str = NEXT_LESSON_PRIO_CODES[str(selected_prio_code)]
            updated_rec = set_recommendation_priority(
                telegram_user_id=user.id,
                recommendation_id=int(rec_record["id"]),
                priority=prio_str,
            )
            if updated_rec is None:
                await _recover(query, context, lang=lang)
                return
            prio_lbl = prio_str.title() if lang != "fa" else _human(prio_str, lang=lang)
            notice_p = f"✅ اولویت پیشنهاد روی «{prio_lbl}» تنظیم شد." if lang == "fa" else f"✅ Priority set to {prio_lbl}."
            await _safe_edit(
                query,
                _next_lesson_rec_text(
                    str(class_record["display_name"]),
                    updated_rec,
                    notice=notice_p,
                    lang=lang,
                ),
                next_lesson_recommendation_keyboard(updated_rec, class_id, revision, lang=lang),
            )
            return
        if action == "nlsrc":
            if rec_record is None:
                await _recover(query, context, lang=lang)
                return
            await _safe_edit(
                query,
                _next_lesson_sources_text(str(class_record["display_name"]), rec_record, lang=lang),
                next_lesson_sources_keyboard(
                    int(rec_record["id"]), rec_record.get("sources", []), revision, lang=lang
                ),
            )
            return
        if action == "nltog":
            if rec_record is None:
                await _recover(query, context, lang=lang)
                return
            await _safe_edit(
                query,
                _next_lesson_sources_text(str(class_record["display_name"]), rec_record, lang=lang),
                next_lesson_sources_keyboard(
                    int(rec_record["id"]), rec_record.get("sources", []), revision, lang=lang
                ),
            )
            return
        if action == "nlign":
            if rec_record is None:
                await _recover(query, context, lang=lang)
                return
            ignore_recommendation(telegram_user_id=user.id, recommendation_id=int(rec_record["id"]))
            await _render_dashboard(
                query, context, telegram_user_id=user.id, class_id=class_id, expected_revision=revision
            )
            return
        if action == "nlman":
            if rec_record is None:
                await _recover(query, context, lang=lang)
                return
            context.user_data["next_lesson_topic"] = {
                "rec_id": int(rec_record["id"]),
                "class_id": class_id,
                "revision": revision,
                "state": "text",
            }
            if lang == "fa":
                man_prompt = (
                    f"✏ انتخاب دستی موضوع درس · {class_record['display_name']}\n\n"
                    "موضوع یا مبحث مدنظرتان را تایپ کنید (۲ تا ۳۰۰ کاراکتر).\n\n"
                    "لطفاً از وارد کردن اطلاعات شخصی و هویتی زبان‌آموزان خودداری فرمایید."
                )
            else:
                man_prompt = (
                    f"✏ Choose Manually · {class_record['display_name']}\n\n"
                    "Type your custom lesson topic (2 to 300 characters).\n\n"
                    "Do not include student names, email addresses, phone numbers, or sensitive data."
                )
            await _safe_edit(
                query,
                man_prompt,
                next_lesson_why_keyboard(int(rec_record["id"]), revision, lang=lang),
            )
            return
        if action == "nlgen":
            if rec_record is None:
                await _recover(query, context, lang=lang)
                return
            if (
                rec_record.get("selected_mode") == "manual"
                and not str(rec_record.get("teacher_request") or "").strip()
            ):
                context.user_data["next_lesson_topic"] = {
                    "rec_id": int(rec_record["id"]),
                    "class_id": class_id,
                    "revision": revision,
                    "state": "text",
                }
                type_msg = "لطفاً ابتدا موضوع سفارشی درس را تایپ کنید." if lang == "fa" else "Type your custom lesson topic before generating."
                await _safe_edit(
                    query,
                    f"✏ Choose Manually · {class_record['display_name']}\n\n{type_msg}",
                    next_lesson_why_keyboard(int(rec_record["id"]), revision, lang=lang),
                )
                return

            access = generation_access_for_user(user.id)
            if not bool(access.get("allowed")):
                await _safe_edit(
                    query,
                    generation_block_message(access),
                    subscription_limit_keyboard(),
                )
                return

            rec_id = int(rec_record["id"])
            claimed = claim_recommendation_generation(
                telegram_user_id=user.id, recommendation_id=rec_id
            )
            if claimed is None:
                await _recover(query, context, lang=lang)
                return

            gen_wait_msg = (
                "🧠 در حال طراحی و تولید طرح درس جلسه آینده...\n\n"
                "TeacherOS در حال آماده‌سازی طرح درس آماده تدریس برای کلاس شماست ✨"
                if lang == "fa"
                else (
                    "🧠 Generating your next lesson plan...\n\n"
                    "TeacherOS is synthesizing approved class history into a classroom-ready lesson."
                )
            )
            await _safe_edit(
                query,
                gen_wait_msg,
                None,
            )

            effective_mode = str(claimed.get("effective_mode") or claimed.get("recommended_mode") or "new_topic")
            level = str(class_record.get("level") or "B1")
            duration = int(claimed.get("duration_minutes") or class_record.get("lesson_duration_minutes") or 60)
            topic = str(claimed.get("teacher_request") or f"Next lesson based on {effective_mode.replace('_', ' ')}")
            objectives_text = ", ".join(claimed.get("objective_labels", [])) or "Demonstrate lesson can-do objective."
            replacements = {
                "{LEVEL}": level,
                "{TOPIC}": topic,
                "{GRAMMAR}": "Target structure aligned to lesson objectives",
                "{VOCABULARY}": "Not specified",
                "{DURATION}": str(duration),
                "{GOALS}": f"Next lesson ({effective_mode}). Rationale: {claimed['rationale']}. Objectives: {objectives_text}",
            }

            try:
                generation = await generate_artifact(
                    feature="lesson",
                    telegram_user_id=user.id,
                    model=selected_openrouter_model(access),
                    current_request=(
                        f"Create a {duration}-minute {level} next lesson in {effective_mode} mode. "
                        f"Topic: {topic}. Objectives: {objectives_text}. "
                        f"Context: {claimed['rationale']}."
                    ),
                    prompt_replacements=replacements,
                    class_id=class_id,
                    quality_requirements={
                        "level": level,
                        "duration_minutes": str(duration),
                    },
                )
                result_text = generation.content
            except Exception:
                logger.exception("Next lesson generation failed")
                release_recommendation_generation(
                    telegram_user_id=user.id,
                    recommendation_id=rec_id,
                    error_code="generation_exception",
                )
                refreshed = get_recommendation(telegram_user_id=user.id, recommendation_id=rec_id)
                err_gen_msg = (
                    "❌ در حال حاضر امکان تولید طرح درس وجود نداشت.\n\n"
                    "انتخاب‌های شما ذخیره شده است. اتصال خود را بررسی کرده و مجدداً دکمه تولید را لمس کنید."
                    if lang == "fa"
                    else (
                        "❌ I could not generate the next lesson right now.\n\n"
                        "Your choices are saved. Check your connection, then tap Generate to retry."
                    )
                )
                await _safe_edit(
                    query,
                    err_gen_msg,
                    next_lesson_recommendation_keyboard(refreshed or rec_record, class_id, revision, lang=lang),
                )
                return

            material_id = None
            try:
                material_id = save_generated_material(
                    telegram_user=user,
                    material_type="lesson",
                    subtype=f"Next Lesson ({MODE_LABELS.get(effective_mode, effective_mode)})",
                    title=f"{topic} Lesson Plan ({level})",
                    level=level,
                    topic=topic,
                    content=result_text,
                    metadata={
                        "next_lesson_recommendation_id": rec_id,
                        "duration_minutes": duration,
                        "mode": effective_mode,
                        "ai_provenance": generation_provenance(generation),
                    },
                    class_id=class_id,
                    objective_ids=generation.source_record_ids.get("class_objectives", []),
                    ai_provenance=generation_provenance(generation),
                    quality_scores=generation.quality_scores,
                )
                plan = complete_next_lesson_plan(
                    telegram_user_id=user.id,
                    recommendation_id=rec_id,
                    material_id=material_id,
                    validation=generation.quality_scores,
                )
                plan_id = int(plan["id"]) if plan else 0
            except Exception:
                logger.exception("Next lesson material/plan could not be completed")
                plan_id = 0

            mode_disp = MODE_LABELS.get(effective_mode, effective_mode) if lang != "fa" else _human(effective_mode, lang=lang)
            if lang == "fa":
                summary_lines = [
                    f"✅ طرح درس با موفقیت تولید و ذخیره شد · {class_record['display_name']}",
                    f"حالت: {mode_disp} · سطح: {level} · {duration} دقیقه",
                    "",
                    "آیا این طرح درس با هدف مورد نظر شما همخوانی دارد؟",
                ]
            else:
                summary_lines = [
                    f"✅ Next lesson plan generated & saved · {class_record['display_name']}",
                    f"Mode: {mode_disp} · Level: {level} · {duration} mins",
                    "",
                    "Did this lesson address the intended target?",
                ]
            await _safe_edit(
                query,
                "\n".join(summary_lines),
                next_lesson_followup_keyboard(plan_id, class_id, revision, lang=lang)
                if plan_id
                else class_details_keyboard(class_id, revision, archived=False, lang=lang),
            )
            if query.message is not None:
                for start in range(0, len(result_text), 4000):
                    await query.message.reply_text(result_text[start : start + 4000])
            return

        if action in {"plan", "analyze", "create", "outcome", "progress"}:
            touch_class_activity(telegram_user_id=user.id, class_id=class_id)
            if lang == "fa":
                headings = {
                    "plan": "🎯 برنامه‌ریزی درس جلسه آینده",
                    "analyze": "🔬 تحلیل و شواهد یادگیری",
                    "create": "🧰 تولید محتوای آموزشی",
                    "outcome": "✅ ثبت بازخورد تدریس",
                    "progress": "📈 پیشرفت و آمار کلاس",
                }
                body = {
                    "plan": "پروفایل و سوابق این کلاس به صورت خودکار در برنامه‌ریزی لحاظ می‌شود. می‌توانید جزئیات جلسه آینده را تنظیم کنید.",
                    "analyze": "بررسی نمونه کارها و تکالیف زبان‌آموزان به صورت امن و بدون نام انجام می‌شود.",
                    "create": "ابزار مورد نظر را انتخاب کنید. مشخصات کلاس به صورت خودکار برای تولید محتوا استفاده خواهد شد.",
                    "outcome": "پس از تدریس جلسه، نتیجه و میزان پیشرفت تدریس را برای بهبود پیشنهادات بعدی ثبت نمایید.",
                    "progress": f"جلسات: {snapshot['history_counts'].get('lessons', 0)} · نتایج ثبت‌شده: {snapshot['history_counts'].get('outcomes', 0)} · مرورهای موعدرسیده: {snapshot['due_review_count']}",
                }
                class_label = "کلاس فعال"
            else:
                headings = {
                    "plan": "🎯 Plan Next Lesson",
                    "analyze": "🔬 Analyze Work",
                    "create": "🧰 Create Materials",
                    "outcome": "✅ Record Outcome",
                    "progress": "📈 Progress",
                }
                body = {
                    "plan": (
                        "The class and its saved profile are selected. The planner asks only lesson-specific questions; any override is clearly ONE-TIME."
                        if feature_enabled("continuity") else
                        "Class-aware generation is not enabled yet. The one-off planner below remains available."
                    ),
                    "analyze": "Analysis is linked to this verified class. Evidence processing and approval remain behind their own rollout gates, so no finding is inferred here.",
                    "create": (
                        "Choose a generator. Saved class context is inherited, and temporary overrides never edit the class profile."
                        if feature_enabled("continuity") else
                        "Choose a one-off generator. It will not silently change class history."
                    ),
                    "outcome": "Record an outcome only after a lesson is explicitly marked taught. No taught lesson is changed from this navigation screen.",
                    "progress": f"Lessons: {snapshot['history_counts'].get('lessons', 0)} · Outcomes: {snapshot['history_counts'].get('outcomes', 0)} · Reviews due: {snapshot['due_review_count']}. Details are recorded facts, never guessed mastery.",
                }
                class_label = "Active class"
            await _safe_edit(
                query,
                f"{headings[action]}\n🏫 {class_label}: {class_record['display_name']}\n\n{body[action]}",
                class_action_keyboard(
                    class_id, revision, action,
                    class_aware=feature_enabled("continuity"),
                    lang=lang,
                ),
            )
            return
        await _recover(query, context, lang=lang)
    except Exception:
        logger.exception("Could not continue class dashboard")
        await _recover(query, context, lang=lang)


async def get_class_dashboard_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    telegram_user_id = update.effective_user.id if update.effective_user else None
    lang = resolve_lang(update, context, telegram_user_id=telegram_user_id)
    topic_state = context.user_data.get("next_lesson_topic")
    if (
        isinstance(topic_state, dict)
        and topic_state.get("state") == "text"
        and update.message is not None
        and update.effective_user is not None
    ):
        rec_id = int(topic_state["rec_id"])
        class_id = int(topic_state["class_id"])
        revision = int(topic_state["revision"])
        try:
            snapshot = class_dashboard_snapshot(
                telegram_user_id=update.effective_user.id, class_id=class_id
            )
            if snapshot is None or int(snapshot["class"]["revision"]) != revision:
                context.user_data.pop("next_lesson_topic", None)
                changed_msg = "⚠️ اطلاعات این کلاس تغییر یافته است. موضوع ذخیره نشد." if lang == "fa" else "⚠️ This class changed. Topic was not saved. Refresh the class."
                await update.message.reply_text(
                    changed_msg,
                    reply_markup=class_recovery_keyboard(lang=lang),
                )
                return
            rec = set_manual_next_lesson_request(
                telegram_user_id=update.effective_user.id,
                recommendation_id=rec_id,
                request=update.message.text or "",
            )
            if rec is None:
                context.user_data.pop("next_lesson_topic", None)
                rec_unavail_msg = "⚠️ این پیش‌نویس دیگر در دسترس نیست." if lang == "fa" else "⚠️ The recommendation draft is no longer available."
                await update.message.reply_text(
                    rec_unavail_msg,
                    reply_markup=class_recovery_keyboard(lang=lang),
                )
                return
            context.user_data.pop("next_lesson_topic", None)
            saved_man_notice = "✅ موضوع سفارشی با موفقیت ذخیره شد." if lang == "fa" else "✅ Custom manual topic saved."
            await update.message.reply_text(
                _next_lesson_rec_text(
                    str(snapshot["class"]["display_name"]), rec,
                    notice=saved_man_notice,
                    lang=lang,
                ),
                reply_markup=next_lesson_recommendation_keyboard(rec, class_id, revision, lang=lang),
            )
        except ValueError as exc:
            err_man_prompt = f"⚠️ {exc}\n\nلطفاً یک موضوع کوتاه وارد کنید (۲ تا ۳۰۰ کاراکتر)." if lang == "fa" else f"⚠️ {exc}\n\nType a short, non-sensitive topic (2 to 300 characters), or return to the plan."
            await update.message.reply_text(
                err_man_prompt,
                reply_markup=next_lesson_why_keyboard(rec_id, revision, lang=lang),
            )
        return
    note_state = context.user_data.get("outcome_note")
    if (
        isinstance(note_state, dict)
        and note_state.get("state") == "text"
        and update.message is not None
        and update.effective_user is not None
    ):
        lesson_id = int(note_state["lesson_id"])
        class_id = int(note_state["class_id"])
        revision = int(note_state["revision"])
        try:
            snapshot = class_dashboard_snapshot(
                telegram_user_id=update.effective_user.id, class_id=class_id
            )
            if snapshot is None or int(snapshot["class"]["revision"]) != revision:
                context.user_data.pop("outcome_note", None)
                changed_note_msg = "⚠️ این کلاس تغییر یافته است. یادداشت ذخیره نشد." if lang == "fa" else "⚠️ This class changed. The note was not saved. Refresh the class."
                await update.message.reply_text(
                    changed_note_msg,
                    reply_markup=class_recovery_keyboard(lang=lang),
                )
                return
            outcome, _ = update_outcome_note(
                telegram_user_id=update.effective_user.id,
                lesson_id=lesson_id,
                note=update.message.text or "",
            )
            if outcome is None:
                context.user_data.pop("outcome_note", None)
                unavail_msg = "⚠️ جلسه تدریس‌شده در دسترس نیست. یادداشتی ذخیره نشد." if lang == "fa" else "⚠️ The taught lesson or saved outcome is no longer available. No note was saved."
                await update.message.reply_text(
                    unavail_msg,
                    reply_markup=class_recovery_keyboard(lang=lang),
                )
                return
            context.user_data.pop("outcome_note", None)
            metrics = outcome_recording_metrics(
                telegram_user_id=update.effective_user.id, class_id=class_id
            )
            saved_note_notice = "یادداشت با موفقیت ثبت شد." if lang == "fa" else "Optional note saved."
            await update.message.reply_text(
                _outcome_summary_text(outcome, metrics, notice=saved_note_notice, lang=lang),
                reply_markup=outcome_summary_keyboard(
                    lesson_id, class_id, revision, has_note=bool(outcome.get("notes")), lang=lang
                ),
            )
        except ValueError as exc:
            outcome = get_lesson_outcome(
                telegram_user_id=update.effective_user.id, lesson_id=lesson_id
            )
            short_note_msg = f"⚠️ {exc}\n\nلطفاً یک یادداشت کوتاه بدون اطلاعات شخصی بنویسید یا دکمه رد شدن را بزنید." if lang == "fa" else f"⚠️ {exc}\n\nUse a short, non-sensitive teaching note, or skip it."
            await update.message.reply_text(
                short_note_msg,
                reply_markup=outcome_note_keyboard(
                    lesson_id, class_id, revision,
                    has_note=bool(outcome and outcome.get("notes")),
                    lang=lang,
                ),
            )
        return

    edit_state = context.user_data.get("class_edit")
    if (
        not isinstance(edit_state, dict)
        or edit_state.get("state") != "text"
        or update.message is None
        or update.effective_user is None
    ):
        return
    text = " ".join((update.message.text or "").split())
    field_code = str(edit_state["field_code"])
    value: Any = text
    if field_code == "bk":
        parts = [part.strip() for part in text.split("|", 1)]
        value = {
            "coursebook_state": "provided",
            "coursebook": parts[0],
            "coursebook_unit": parts[1] if len(parts) == 2 else None,
        }
    try:
        updated = update_profile_field(
            telegram_user_id=update.effective_user.id,
            class_id=int(edit_state["class_id"]),
            field=FIELD_CODES[field_code],
            value=value,
            expected_revision=int(edit_state["revision"]),
        )
        if updated is None:
            context.user_data.pop("class_edit", None)
            prof_fail_msg = "⚠️ این پروفایل تغییر یافته است. تغییری ذخیره نشد." if lang == "fa" else "⚠️ This profile changed. No edit was saved. Refresh the class."
            await update.message.reply_text(
                prof_fail_msg,
                reply_markup=class_recovery_keyboard(lang=lang),
            )
            return
        context.user_data.pop("class_edit", None)
        class_id = int(updated["id"])
        revision = int(updated["revision"])
        context.user_data["active_class"] = {
            "id": class_id,
            "display_name": updated["display_name"],
            "revision": revision,
        }
        prof_done_msg = "✅ مشخصات کلاس به‌روزرسانی شد\n\n" if lang == "fa" else "✅ Profile field updated\n\n"
        await update.message.reply_text(
            prof_done_msg + "\n".join(_profile_lines(updated, lang=lang)),
            reply_markup=class_profile_keyboard(class_id, revision, archived=False, lang=lang),
        )
    except ValueError:
        val_err_msg = "لطفاً از یک عبارت کوتاه و بدون اطلاعات هویتی و حساس استفاده کنید." if lang == "fa" else "Use one short, non-sensitive phrase. Do not include student names, email addresses, phone numbers, health, or disability information."
        await update.message.reply_text(
            val_err_msg,
            reply_markup=edit_text_keyboard(
                int(edit_state["class_id"]),
                int(edit_state["revision"]),
                coursebook=field_code == "bk",
                lang=lang,
            ),
        )
