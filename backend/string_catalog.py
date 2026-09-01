"""TeacherOS Centralized String Catalog and Localization Engine (Day 24).

Standardizes English product copy and provides isolated Persian billing/support strings:
- Navigation verbs, action labels, and screen-reader accessibility annotations.
- Active class context badges and progress indicators.
- Onboarding walkthrough strings for first-run teachers.
- Structured fallbacks ensuring missing keys never crash runtime.
"""
from __future__ import annotations

import string
from typing import Any

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = frozenset({"en", "fa"})

# ---------------------------------------------------------------------------
# String Dictionaries
# ---------------------------------------------------------------------------

STRINGS_EN: dict[str, str] = {
    # Navigation & Verbs
    "nav_back": "⬅ Back",
    "nav_home": "🏠 Main Menu",
    "nav_cancel": "❌ Cancel",
    "nav_save": "💾 Save",
    "nav_edit": "✏ Edit",
    "nav_delete": "🗑 Delete",
    "nav_approve": "✅ Approve",
    "nav_export": "📥 Export",
    "nav_retry": "🔄 Retry",
    "nav_close": "✖ Close",
    "nav_next": "➡️ Next",
    "nav_previous": "⬅️ Previous",
    "nav_search": "🔍 Search",
    "nav_pin": "📌 Pin to Class",
    "nav_unpin": "📍 Unpin",
    "nav_favorites": "⭐ Favorites",

    # Status & Accessibility Badges (Screen-reader clear without emoji dependency)
    "badge_approved": "[Status: Approved]",
    "badge_draft": "[Status: Draft]",
    "badge_needs_review": "[Status: Needs Review]",
    "badge_active": "[Status: Active]",
    "badge_archived": "[Status: Archived]",
    "badge_secure": "[Status: Secure]",
    "badge_needs_support": "[Status: Needs Support]",

    # Header & Class Context
    "header_active_class": "🏫 Active Class: {class_name} · Level: {level}",
    "header_no_active_class": "🏫 No Class Selected",
    "header_class_dashboard": "📊 Class Intelligence Dashboard · {class_name}",
    "header_main_menu": "🤖 TeacherOS · English Teaching Copilot",

    # UI Feedback & States
    "state_loading": "⏳ Processing request, please wait...",
    "state_empty_materials": "No materials generated yet for this class.",
    "state_empty_search": "No matching materials found for '{query}'.",
    "state_empty_pinned": "No pinned materials yet. Tap 'Pin to Class' on any material for fast reuse.",
    "state_success_saved": "✅ Successfully saved.",
    "state_success_approved": "✅ Successfully approved and marked final.",
    "state_success_pinned": "📌 Material pinned to class favorites.",
    "state_success_unpinned": "📍 Material unpinned from class favorites.",
    "state_error_generic": "⚠️ An error occurred. Please try again.",
    "state_error_not_found": "⚠️ Requested item not found or access denied.",
    "state_error_stale_session": "⚠️ Session expired. Returning to main menu.",

    # Onboarding Walkthrough (3 Concise Steps)
    "onboarding_welcome_title": "🎉 Welcome to TeacherOS!",
    "onboarding_welcome_body": (
        "TeacherOS helps English teachers remember class progress, generate level-calibrated "
        "materials, and turn lesson evidence into targeted instruction."
    ),
    "onboarding_step1_title": "Step 1: Set Up Your Class 🏫",
    "onboarding_step1_body": (
        "Create a class profile with CEFR level, age group, and learning goals. "
        "TeacherOS reuses this context automatically so you never re-enter class details."
    ),
    "onboarding_step2_title": "Step 2: Plan & Teach 📚",
    "onboarding_step2_body": (
        "Generate classroom-ready lesson plans, activities, and worksheets. "
        "After teaching, log a 30-second outcome check-in to keep class memory up to date."
    ),
    "onboarding_step3_title": "Step 3: Evidence to Action 🎯",
    "onboarding_step3_body": (
        "Submit student writing or notes to get approved diagnoses, 1-tap differentiated follow-ups, "
        "spaced retrieval queues, and Word/PDF progress reports."
    ),
    "onboarding_finish_btn": "🚀 Start Teaching",

    # Language Switcher
    "lang_switched": "🌐 Language set to English.",
    "lang_choose": "🌐 Choose Display Language / انتخاب زبان:",
}

STRINGS_FA: dict[str, str] = {
    # Navigation & Verbs
    "nav_back": "⬅ بازگشت",
    "nav_home": "🏠 منوی اصلی",
    "nav_cancel": "❌ انصراف",
    "nav_save": "💾 ذخیره",
    "nav_edit": "✏ ویرایش",
    "nav_delete": "🗑 حذف",
    "nav_approve": "✅ تایید نهایی",
    "nav_export": "📥 خروجی",
    "nav_retry": "🔄 تلاش مجدد",
    "nav_close": "✖ بستن",
    "nav_next": "➡️ بعدی",
    "nav_previous": "⬅️ قبلی",
    "nav_search": "🔍 جستجو",
    "nav_pin": "📌 سنجاق به کلاس",
    "nav_unpin": "📍 برداشتن سنجاق",
    "nav_favorites": "⭐ علاقه‌مندی‌ها",

    # Status & Accessibility Badges
    "badge_approved": "[وضعیت: تایید شده]",
    "badge_draft": "[وضعیت: پیش‌نویس]",
    "badge_needs_review": "[وضعیت: نیازمند بررسی]",
    "badge_active": "[وضعیت: فعال]",
    "badge_archived": "[وضعیت: بایگانی]",
    "badge_secure": "[وضعیت: تثبیت شده]",
    "badge_needs_support": "[وضعیت: نیازمند تقویت]",

    # Header & Class Context
    "header_active_class": "🏫 کلاس فعال: {class_name} · سطح: {level}",
    "header_no_active_class": "🏫 کلاسی انتخاب نشده است",
    "header_class_dashboard": "📊 داشبورد هوشمند کلاس · {class_name}",
    "header_main_menu": "🤖 TeacherOS · دستیار هوشمند تدریس زبان",

    # UI Feedback & States
    "state_loading": "⏳ در حال پردازش، لطفاً شکیبا باشید...",
    "state_empty_materials": "هنوز محتوایی برای این کلاس ایجاد نشده است.",
    "state_empty_search": "محتوایی برای '{query}' یافت نشد.",
    "state_empty_pinned": "محتوای سنجاق‌شده‌ای وجود ندارد. برای دسترسی سریع، از گزینه 'سنجاق به کلاس' استفاده کنید.",
    "state_success_saved": "✅ با موفقیت ذخیره شد.",
    "state_success_approved": "✅ تایید شد و به عنوان نسخه نهایی ثبت گردید.",
    "state_success_pinned": "📌 محتوا به علاقه‌مندی‌های کلاس افزوده شد.",
    "state_success_unpinned": "📍 محتوا از علاقه‌مندی‌های کلاس برداشته شد.",
    "state_error_generic": "⚠️ خطایی رخ داد. لطفاً مجدداً تلاش کنید.",
    "state_error_not_found": "⚠️ مورد درخواستی یافت نشد یا دسترسی مجاز نیست.",
    "state_error_stale_session": "⚠️ جلسه کاری منقضی شد. انتقال به منوی اصلی.",

    # Onboarding Walkthrough
    "onboarding_welcome_title": "🎉 به TeacherOS خوش آمدید!",
    "onboarding_welcome_body": (
        "دستیار TeacherOS به شما کمک می‌کند روند یادگیری هر کلاس را ثبت کنید، محتوای متناسب با سطح بسازید "
        "و شواهد یادگیری را به تمرینات هدفمند تبدیل نمایید."
    ),
    "onboarding_step1_title": "گام ۱: تعریف کلاس 🏫",
    "onboarding_step1_body": (
        "مشخصات کلاس خود از قبیل سطح CEFR، رده سنی و اهداف آموزشی را ثبت کنید تا در تمام مراحل تدریس از آن استفاده شود."
    ),
    "onboarding_step2_title": "گام ۲: طرح درس و تدریس 📚",
    "onboarding_step2_body": (
        "طرح درس‌ها، فعالیت‌ها و کاربرگ‌های آماده بسازید و پس از تدریس با یک ثبت بازخورد ۳۰ ثانیه‌ای حافظه کلاس را به‌روز نگه دارید."
    ),
    "onboarding_step3_title": "گام ۳: تبدیل شواهد به اقدام 🎯",
    "onboarding_step3_body": (
        "متن‌های نوشتاری یا نکات کلاسی را ثبت کنید تا تحلیل‌های تاییدشده، تدریس تمایزیافته، مرورهای دوره‌ای و گزارش پیشرفت دریافت کنید."
    ),
    "onboarding_finish_btn": "🚀 شروع تدریس",

    # Language Switcher
    "lang_switched": "🌐 زبان برنامه به فارسی تغییر یافت.",
    "lang_choose": "🌐 Choose Display Language / انتخاب زبان:",

    # Persian Billing & Support Isolated Strings
    "billing_plan_pro": "طرح حرفه‌ای (Pro): ۱۴۹,۰۰۰ تومان / ۳۰ روزه",
    "billing_plan_premium": "طرح ویژه (Premium): ۴۲۰,۰۰۰ تومان / ۹۰ روزه",
    "billing_zarinpal_notice": "پرداخت امن از طریق درگاه زرین‌پال",
    "support_contact_prompt": "ارتباط با پشتیبانی و ارسال انتقادات و پیشنهادات:",
}


CATALOGS: dict[str, dict[str, str]] = {
    "en": STRINGS_EN,
    "fa": STRINGS_FA,
}


def tr(key: str, lang: str = "en", **kwargs: Any) -> str:
    """Retrieve a localized string with safe fallback to English."""
    norm_lang = lang.lower() if isinstance(lang, str) else "en"
    if norm_lang not in SUPPORTED_LANGUAGES:
        norm_lang = DEFAULT_LANGUAGE

    catalog = CATALOGS.get(norm_lang, STRINGS_EN)
    template = catalog.get(key) or STRINGS_EN.get(key, f"[{key}]")

    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template
