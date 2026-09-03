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

    # Billing & Support
    "billing_plan_pro": "Pro Plan: 149,000 Tomans / 30 days",
    "billing_plan_premium": "Premium Plan: 420,000 Tomans / 90 days",
    "billing_zarinpal_notice": "Secure payment via Zarinpal gateway",
    "support_contact_prompt": "Contact support and share your feedback:",

    # Main Workspace & Home Copy
    "menu_my_classes": "🏫 My Classes",
    "menu_quick_create": "⚡ Quick Create",
    "menu_analyze_work": "🔍 Analyze Work",
    "menu_search": "🔎 Search",
    "menu_account": "👤 Account",
    "menu_lesson_planner": "📚 Lesson Planner",
    "menu_activities": "🎲 Activities",
    "menu_worksheets": "📝 Worksheets",
    "menu_assessments": "✅ Assessments",

    "home_welcome_title": "👋 Welcome to TeacherOS",
    "home_welcome_subtitle": "Your AI assistant for English teachers.",
    "home_welcome_classes_choice": "Choose My Classes for recurring teaching, or Quick Create for one-off work.",
    "home_quick_title": "⚡ Quick Create",
    "home_quick_body": "Create a one-off resource without setting up a class. Your four existing tools work exactly as before.",
    "home_analyze_title": "🔬 Analyze Work",
    "home_analyze_body": "Evidence analysis is linked to a class so progress carries forward. Choose an active class first.",
    "home_analyze_prompt": "Choose an active class first.",
    "home_analyze_no_classes": "You do not have any active classes yet. Create one from My Classes, or use Quick Create for one-off work.",

    # Account Hub Copy & Buttons
    "account_title": "👤 TeacherOS Account & Settings",
    "account_plan_label": "Plan:",
    "account_remaining_label": "Remaining Today:",
    "account_manage_prompt": "Manage your usage, plan, general library, and settings below.",
    "btn_my_usage": "📊 My Usage",
    "btn_my_plan": "🪪 My Plan",
    "btn_general_library": "📁 General Library",
    "btn_rate_teacheros": "⭐ Rate TeacherOS",
    "btn_language": "🌐 Language / زبان",
    "btn_guide": "🧭 Guide",
    "btn_help_policies": "ℹ️ Help & Policies",
    "btn_admin": "🛡 Admin Panel",

    # Generator Options (Levels, Durations, Types)
    "level_a1": "A1 · Beginner",
    "level_a2": "A2 · Elementary",
    "level_b1": "B1 · Intermediate",
    "level_b2": "B2 · Upper-Intermediate",
    "level_c1": "C1 · Advanced",
    "level_c2": "C2 · Mastery",
    "dur_45": "45 mins",
    "dur_60": "60 mins",
    "dur_90": "90 mins",
    "dur_other": "Other",
    "gram_tenses": "Tenses",
    "gram_modals": "Modals",
    "gram_conditionals": "Conditionals",
    "gram_passive": "Passive",
    "gram_questions": "Questions",
    "gram_custom": "Custom...",
    "act_warmup": "Warm-up Game",
    "act_drill": "Communicative Drill",
    "act_roleplay": "Roleplay",
    "act_icebreaker": "Icebreaker",
    "act_vocab": "Vocabulary Race",
    "act_grammar": "Grammar Game",
    "ws_blanks": "Fill in the Blanks",
    "ws_mc": "Multiple Choice",
    "ws_matching": "Matching",
    "ws_transformation": "Sentence Transformation",
    "ws_reading": "Reading Comprehension",
    "ws_mixed": "Mixed Revision",
    "quiz_diag": "Diagnostic Quiz",
    "quiz_unit": "Unit Review Test",
    "quiz_progress": "Progress Check",
    "quiz_exit": "Exit Ticket",
    "quiz_mc_only": "Multiple Choice Only",
    "quiz_mixed": "Mixed Question Types",
    "quiz_gap": "Open Cloze / Gap Fill",
    "quiz_error": "Error Identification",
    "quiz_5q": "5 Questions",
    "quiz_10q": "10 Questions",
    "quiz_15q": "15 Questions",
    "quiz_20q": "20 Questions",
    "quiz_custom_count": "Custom...",

    # Generator Action Buttons
    "btn_gen_lesson": "✨ Generate Lesson Plan",
    "btn_gen_activity": "🎲 Generate Activity",
    "btn_gen_worksheet": "📝 Generate Worksheet",
    "btn_gen_assessment": "✅ Generate Assessment",
    "btn_change_type": "🔄 Change Type",
    "btn_change_level": "🔄 Change Level",
    "btn_change_duration": "🔄 Change Duration",
    "btn_change_grammar": "🔄 Change Grammar",
    "btn_change_topic": "🔄 Change Topic",
    "btn_change_format": "🔄 Change Format",
    "btn_change_count": "🔄 Change Count",
    "btn_export_word": "📥 Export to Word (.docx)",
    "btn_export_pdf": "📄 Export to PDF",

    # Class Dashboard & Intelligence Buttons
    "btn_plan_next_lesson": "🎯 Lesson Plan",
    "btn_analyze_work": "🔬 Analyze Work",
    "btn_create_materials": "🧰 Create Materials",
    "btn_record_outcome": "✅ Record Outcome",
    "btn_spaced_review": "🔁 Spaced Review",
    "btn_progress": "📈 Progress",
    "btn_curriculum": "📚 Curriculum",
    "btn_class_library": "📁 Library",
    "btn_class_profile": "👤 Profile",
    "btn_differentiate": "🎯 Differentiate",
    "btn_more_details": "More details",
    "btn_lesson_history": "📚 Lesson History",
    "btn_my_classes": "⬅ My Classes",
    "btn_active_classes": "⬅ Active Classes",
    "btn_today": "☀ Today",
    "btn_new_class": "➕ Create a Class",
    "btn_archived_classes": "🗃 Archived",
    "btn_why_classes": "💡 Why Classes?",
    "btn_resume_draft": "▶ Resume Class Draft",
    "btn_submit_evidence": "➕ Submit Evidence",
    "btn_writing_feedback": "✍️ Writing Feedback",
    "btn_back_to_dashboard": "◀ Back to Dashboard",
    "btn_advanced_tools": "✨ Advanced Teaching Tools ➡️",
    "btn_adv_analyze": "🔍 Check Homework & Writing",
    "btn_adv_writing": "✍️ Student Writing Feedback",
    "btn_adv_review": "🧠 Spaced Review Games",
    "btn_adv_diff": "👥 Differentiate (Fast & Slow Learners)",
    "btn_adv_curriculum": "📖 Coursebook & Syllabus Tracker",
    "btn_adv_reports": "📊 Student Progress Reports",
    "btn_adv_library": "📁 Class Library & Files",
    "btn_adv_history": "📚 Past Lesson History",
    "btn_adv_profile": "⚙️ Class Settings & Profile",
    "btn_fast_setup": "⚡ Quick 30-Second Setup ✨",
    "btn_detailed_setup": "🎨 Detailed Setup (All details)",
    "btn_back_to_class_hub": "⬅️ Back to Class Hub",
    "btn_class_students": "👤 Class Students",
    "btn_class_assessments": "📝 Assess Class (Exams)",
    "hub_cat_class": "🏫 1. Class & Students",
    "hub_cat_planning": "📝 2. Planning & Prep",
    "hub_cat_assessment": "📊 3. Assessment & Feedback",
    "hub_cat_tools": "🧰 4. TeacherOS Tools",
    "btn_menu_back": "🔙 Back",

    # Class Navigation, Setup & Detail Buttons
    "btn_class_home": "⬅ Class Home",
    "btn_edit_profile": "👤 Edit Profile",
    "btn_restore_class": "♻ Restore Class",
    "btn_archive_class": "🗃 Archive Class",
    "btn_save_field": "Save this field",
    "btn_cancel_edit": "⬅ Cancel edit",
    "btn_clear_coursebook": "Clear / no coursebook",
    "btn_yes_archive": "Yes, archive",
    "btn_yes_restore": "Yes, restore",
    "btn_no_keep_status": "No, keep current status",
    "btn_start_blank": "➕ Start blank",
    "btn_use_template": "♻ Use my last class as template",
    "btn_discard_draft": "🗑 Discard saved draft",
    "btn_save_draft": "💾 Save Draft",
    "btn_skip": "Skip",
    "btn_continue": "Continue",
    "btn_create_class_confirm": "✅ Create Class",
    "btn_continue_setup": "Continue setup",
    "btn_save_finish_later": "💾 Save and finish later",
    "btn_yes_discard": "Yes, discard",
    "btn_keep_draft": "Keep draft",
    "btn_resume_setup": "▶ Resume setup",
    "btn_refresh_classes": "🔄 Refresh My Classes",
    "btn_back_to_class": "⬅ Back to Class",
    "btn_analyze_for_class": "🔬 Analyze Work for this Class",
    "btn_quick_create_oneoff": "⚡ Quick Create (one-off)",
    "btn_quick_create_instead": "⚡ Quick Create instead",

    # Outcome & Next Lesson Buttons
    "btn_outcome_result_met": "✅ Achieved",
    "btn_outcome_result_partly": "⚠️ Partly achieved",
    "btn_outcome_result_not_met": "🔄 Needs reteaching",
    "btn_outcome_no_difficulty": "No major difficulty",
    "btn_outcome_diff_language": "Language / concept",
    "btn_outcome_diff_instructions": "Instructions",
    "btn_outcome_diff_pace": "Pace / time",
    "btn_outcome_diff_participation": "Participation",
    "btn_outcome_diff_materials": "Materials",
    "btn_outcome_diff_assessment": "Assessment check",
    "btn_outcome_done_diff": "Done with difficulties",
    "btn_outcome_comp_completed": "Full lesson completed",
    "btn_outcome_comp_partly": "Partly completed",
    "btn_outcome_comp_not": "Little / not completed",
    "btn_outcome_add_note": "✏ Add/Edit Note",
    "btn_outcome_skip_note": "Skip note",
    "btn_outcome_clear_note": "Clear note",
    "btn_outcome_set_reminder": "⏰ Set reminder",
    "btn_remind_1h": "In 1 hour",
    "btn_remind_18": "Today 18:00",
    "btn_remind_20": "Today 20:00",
    "btn_remind_tmrw": "Tomorrow 09:00",
    "btn_nl_generate": "🚀 1. Generate This Lesson Now",
    "btn_nl_custom_topic": "✏️ 2. Custom Topic",
    "btn_nl_coursebook": "📖 3. From Coursebook",
    "btn_nl_advanced_settings": "⚙️ Advanced Settings",
    "btn_nl_change_mode": "🔄 Change Mode",
    "btn_nl_change_priority": "⚖ Change Priority",
    "btn_nl_filter_sources": "📋 Filter Sources",
    "btn_nl_why": "💡 Why This Next?",
    "btn_nl_ignore": "🗑 Dismiss Proposal",
    "btn_nl_use_as_next": "➡ Use as Next Lesson",

    # Profile & Attribute Labels
    "field_name": "Name",
    "field_level": "Level",
    "field_age": "Age group",
    "field_size": "Class size",
    "field_duration": "Duration",
    "field_goal": "Goal",
    "field_weak": "Weak areas",
    "field_book": "Coursebook",
    "field_equipment": "Equipment",
    "field_preference": "Preference",
    "val_not_sure": "Not sure",
    "val_none": "None",
    "val_skipped": "Skipped",
    "val_date_not_set": "Date not set",
    "val_none_planned": "None planned",
    "val_none_recorded": "None recorded",
    "val_none_unresolved": "None unresolved",
    "val_active_class": "Active class",
    "val_archived_class": "Archived class",

    # Friendly Prompts & Explanations
    "prompt_why_classes_title": "💡 Why Use My Classes?",
    "prompt_why_classes_body": (
        "When you create a class profile, TeacherOS remembers your group's CEFR level, "
        "age band, learning goals, coursebook, and lesson history.\n\n"
        "This means future lesson planning and evidence analysis build upon your previous sessions "
        "seamlessly, rather than starting from scratch every time!\n\n"
        "Use Quick Create for one-off resources. Class setup is fast and never asks for student names."
    ),
    "prompt_class_recovery": (
        "⚠️ This view changed, expired, or is no longer available.\n\n"
        "No changes were made. Refresh your class list or return to the main menu."
    ),
    "classes_list_friendly_title": "🏫 My Classes",
    "classes_list_friendly_intro": (
        "Manage your classes below. TeacherOS remembers your students' level, goals, "
        "and lesson history so every future session is tailored and continuous ✨"
    ),
    "classes_list_empty_friendly": (
        "You don't have any active classes yet! Tap '➕ Create a Class' below to set up "
        "your first class in under a minute, or use '⚡ Quick Create' for instant one-off tools 🌱"
    ),
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

    # Main Workspace & Home Copy (Persian)
    "menu_my_classes": "🏫 کلاس‌های من",
    "menu_quick_create": "⚡ ساخت سریع",
    "menu_analyze_work": "🔍 تحلیل تکالیف",
    "menu_search": "🔎 جستجو",
    "menu_account": "👤 حساب کاربری",
    "menu_lesson_planner": "📚 طرح درس",
    "menu_activities": "🎲 فعالیت‌ها",
    "menu_worksheets": "📝 کاربرگ‌ها",
    "menu_assessments": "✅ آزمون‌ها",

    "home_welcome_title": "👋 به TeacherOS خوش آمدید",
    "home_welcome_subtitle": "دستیار هوشمند شما برای تدریس زبان انگلیسی.",
    "home_welcome_classes_choice": "برای مدیریت کلاس‌های مستمر گزینه «کلاس‌های من» یا برای ابزارهای سریع گزینه «ساخت سریع» را انتخاب کنید.",
    "home_quick_title": "⚡ ساخت سریع",
    "home_quick_body": "تولید سریع محتوای آموزشی بدون نیاز به تعریف کلاس. ابزارهای چهارگانه به صورت آماده در اختیار شما هستند.",
    "home_analyze_title": "🔬 تحلیل تکالیف",
    "home_analyze_body": "تحلیل تکالیف مربوط به هر کلاس انجام می‌شود تا پیشینه و وضعیت زبان‌آموزان به طور دقیق مشخص باشد. لطفاً ابتدا یک کلاس فعال را انتخاب کنید.",
    "home_analyze_prompt": "لطفاً ابتدا یک کلاس فعال را انتخاب کنید.",
    "home_analyze_no_classes": "هنوز کلاسی تعریف نکرده‌اید. با انتخاب «کلاس‌های من» می‌توانید اولین کلاس خود را بسازید، یا از «ساخت سریع» برای ابزارهای فوری استفاده کنید.",

    # Account Hub Copy & Buttons (Persian)
    "account_title": "👤 حساب کاربری و تنظیمات TeacherOS",
    "account_plan_label": "طرح:",
    "account_remaining_label": "اعتبار باقیمانده امروز:",
    "account_manage_prompt": "مدیریت مصرف، طرح اشتراک، کتابخانه عمومی و تنظیمات در زیر در دسترس است.",
    "btn_my_usage": "📊 مصرف من",
    "btn_my_plan": "🪪 طرح من",
    "btn_general_library": "📁 کتابخانه عمومی",
    "btn_rate_teacheros": "⭐ امتیاز به بات",
    "btn_language": "🌐 Language / زبان",
    "btn_guide": "🧭 راهنما",
    "btn_help_policies": "ℹ️ راهنما و قوانین",
    "btn_admin": "🛡 پنل مدیریت",

    # Generator Options (Persian)
    "level_a1": "سطح A1 (مبتدی)",
    "level_a2": "سطح A2 (پایه)",
    "level_b1": "سطح B1 (متوسط)",
    "level_b2": "سطح B2 (فوق متوسط)",
    "level_c1": "سطح C1 (پیشرفته)",
    "level_c2": "سطح C2 (تسلط کامل)",
    "dur_45": "۴۵ دقیقه",
    "dur_60": "۶۰ دقیقه",
    "dur_90": "۹۰ دقیقه",
    "dur_other": "سایر زمان‌ها",
    "gram_tenses": "زمان‌های افعال (Tenses)",
    "gram_modals": "افعال کمکی (Modals)",
    "gram_conditionals": "جملات شرطی (Conditionals)",
    "gram_passive": "مجهول (Passive)",
    "gram_questions": "ساختار سوالی (Questions)",
    "gram_custom": "موضوع دلخواه...",
    "act_warmup": "بازی گرم‌کردن (Warm-up)",
    "act_drill": "تمرین مکالمه (Drill)",
    "act_roleplay": "ایفای نقش (Roleplay)",
    "act_icebreaker": "یخ‌شکن (Icebreaker)",
    "act_vocab": "مسابقه واژگان",
    "act_grammar": "بازی گرامر",
    "ws_blanks": "جای خالی (Fill in the blanks)",
    "ws_mc": "چهارگزینه‌ای (Multiple Choice)",
    "ws_matching": "وصل‌کردنی (Matching)",
    "ws_transformation": "تبدیل جمله (Transformation)",
    "ws_reading": "درک مطلب (Reading)",
    "ws_mixed": "مرور ترکیبی (Mixed Revision)",
    "quiz_diag": "کوئیز تعیین سطح / تشخیصی",
    "quiz_unit": "آزمون مرور درس",
    "quiz_progress": "ارزیابی پیشرفت",
    "quiz_exit": "بلیط خروج (Exit Ticket)",
    "quiz_mc_only": "فقط چهارگزینه‌ای",
    "quiz_mixed": "انواع سوالات ترکیبی",
    "quiz_gap": "جای خالی / کلوز",
    "quiz_error": "شناسایی و تصحیح خطا",
    "quiz_5q": "۵ سوال",
    "quiz_10q": "۱۰ سوال",
    "quiz_15q": "۱۵ سوال",
    "quiz_20q": "۲۰ سوال",
    "quiz_custom_count": "تعداد دلخواه...",

    # Generator Action Buttons (Persian)
    "btn_gen_lesson": "✨ تولید طرح درس",
    "btn_gen_activity": "🎲 تولید فعالیت",
    "btn_gen_worksheet": "📝 تولید کاربرگ",
    "btn_gen_assessment": "✅ تولید آزمون",
    "btn_change_type": "🔄 تغییر نوع",
    "btn_change_level": "🔄 تغییر سطح",
    "btn_change_duration": "🔄 تغییر زمان",
    "btn_change_grammar": "🔄 تغییر گرامر",
    "btn_change_topic": "🔄 تغییر موضوع",
    "btn_change_format": "🔄 تغییر قالب",
    "btn_change_count": "🔄 تغییر تعداد",
    "btn_export_word": "📥 خروجی ورد (.docx)",
    "btn_export_pdf": "📄 خروجی پی‌دی‌اف (.pdf)",

    "btn_plan_next_lesson": "🎯 طرح درس",
    "btn_analyze_work": "🔬 تحلیل تکالیف",
    "btn_create_materials": "🧰 تولید محتوا",
    "btn_record_outcome": "✅ ثبت نتیجه تدریس",
    "btn_spaced_review": "🔁 مرور دوره‌ای",
    "btn_progress": "📈 روند پیشرفت",
    "btn_curriculum": "📚 سرفصل آموزشی",
    "btn_class_library": "📁 کتابخانه کلاس",
    "btn_class_profile": "👤 مشخصات کلاس",
    "btn_differentiate": "🎯 تدریس تمایزیافته",
    "btn_more_details": "جزئیات بیشتر",
    "btn_lesson_history": "📚 تاریخچه تدریس",
    "btn_my_classes": "⬅ کلاس‌های من",
    "btn_active_classes": "⬅ کلاس‌های فعال",
    "btn_today": "☀ تدریس امروز",
    "btn_new_class": "➕ کلاس جدید",
    "btn_archived_classes": "🗃 کلاس‌های بایگانی",
    "btn_why_classes": "💡 چرا کلاس بسازیم؟",
    "btn_resume_draft": "▶ ادامه ثبت کلاس",
    "btn_submit_evidence": "➕ ثبت تکلیف و شواهد",
    "btn_writing_feedback": "✍️ تصحیح و بازخورد رایتینگ",
    "btn_back_to_dashboard": "◀ بازگشت به داشبورد",
    "btn_advanced_tools": "✨ ابزارهای پیشرفته و تخصصی تدریس ➡️",
    "btn_adv_analyze": "🔍 تصحیح و بررسی تکالیف",
    "btn_adv_writing": "✍️ بازخورد رایتینگ زبان‌آموزان",
    "btn_adv_review": "🧠 بازی‌های مرور طلایی",
    "btn_adv_diff": "👥 کمک به شاگردان ضعیف و قوی",
    "btn_adv_curriculum": "📖 دفتر پیشرفت کتاب و ترم",
    "btn_adv_reports": "📊 گزارش پیشرفت کلاسی",
    "btn_adv_library": "📁 کتابخانه فایل‌های کلاس",
    "btn_adv_history": "📚 تاریخچه درس‌های قبل",
    "btn_adv_profile": "⚙️ مشخصات و تنظیمات کلاس",
    "btn_fast_setup": "⚡ راه‌اندازی سریع (۳۰ ثانیه) ✨",
    "btn_detailed_setup": "🎨 ثبت کلاس با تمام جزئیات",
    "btn_back_to_class_hub": "⬅️ بازگشت به صفحه اصلی کلاس",
    "btn_class_students": "👤 دانش‌آموزان",
    "btn_class_assessments": "📝 ارزیابی کلاسی (آزمون‌ها)",
    "hub_cat_class": "🏫 ۱. کلاس و دانش‌آموزان",
    "hub_cat_planning": "📝 ۲. طراحی و آماده‌سازی درس",
    "hub_cat_assessment": "📊 ۳. ارزیابی و بازخورد",
    "hub_cat_tools": "🧰 ۴. ابزارهای TeacherOS",
    "btn_menu_back": "🔙 بازگشت",

    # Class Navigation, Setup & Detail Buttons (Persian)
    "btn_class_home": "⬅ صفحه اصلی کلاس",
    "btn_edit_profile": "👤 ویرایش مشخصات",
    "btn_restore_class": "♻ بازیابی کلاس",
    "btn_archive_class": "🗃 بایگانی کلاس",
    "btn_save_field": "ذخیره این بخش",
    "btn_cancel_edit": "⬅ انصراف از ویرایش",
    "btn_clear_coursebook": "حذف کتاب / بدون کتاب",
    "btn_yes_archive": "بله، بایگانی شود",
    "btn_yes_restore": "بله، بازیابی شود",
    "btn_no_keep_status": "خیر، بدون تغییر بماند",
    "btn_start_blank": "➕ شروع کلاس جدید",
    "btn_use_template": "♻ استفاده از مشخصات آخرین کلاس",
    "btn_discard_draft": "🗑 حذف پیش‌نویس ذخیره‌شده",
    "btn_save_draft": "💾 ذخیره پیش‌نویس",
    "btn_skip": "رد شدن",
    "btn_continue": "ادامه",
    "btn_create_class_confirm": "✅ ساخت و ثبت کلاس",
    "btn_continue_setup": "ادامه فرآیند ثبت",
    "btn_save_finish_later": "💾 ذخیره و تکمیل بعداً",
    "btn_yes_discard": "بله، حذف شود",
    "btn_keep_draft": "نگه‌داشتن پیش‌نویس",
    "btn_resume_setup": "▶ ادامه ثبت کلاس",
    "btn_refresh_classes": "🔄 به‌روزرسانی کلاس‌های من",
    "btn_back_to_class": "⬅ بازگشت به کلاس",
    "btn_analyze_for_class": "🔬 تحلیل تکالیف این کلاس",
    "btn_quick_create_oneoff": "⚡ ساخت سریع (بدون کلاس)",
    "btn_quick_create_instead": "⚡ ساخت سریع محتوا",

    # Outcome & Next Lesson Buttons (Persian)
    "btn_outcome_result_met": "✅ کاملاً محقق شد",
    "btn_outcome_result_partly": "⚠️ تا حدی محقق شد",
    "btn_outcome_result_not_met": "🔄 نیاز به تدریس مجدد",
    "btn_outcome_no_difficulty": "بدون چالش خاص",
    "btn_outcome_diff_language": "مفهوم / زبان",
    "btn_outcome_diff_instructions": "شفافیت دستورالعمل",
    "btn_outcome_diff_pace": "مدیریت زمان / سرعت",
    "btn_outcome_diff_participation": "مشارکت زبان‌آموزان",
    "btn_outcome_diff_materials": "محتوا و منابع",
    "btn_outcome_diff_assessment": "سنجش و ارزیابی",
    "btn_outcome_done_diff": "ثبت موارد چالش‌برانگیز",
    "btn_outcome_comp_completed": "کامل تدریس شد",
    "btn_outcome_comp_partly": "بخشی از درس تدریس شد",
    "btn_outcome_comp_not": "بخش کمی تدریس شد",
    "btn_outcome_add_note": "✏ افزودن / ویرایش یادداشت",
    "btn_outcome_skip_note": "رد شدن از یادداشت",
    "btn_outcome_clear_note": "حذف یادداشت",
    "btn_outcome_set_reminder": "⏰ تنظیم یادآوری",
    "btn_remind_1h": "۱ ساعت بعد",
    "btn_remind_18": "امروز ساعت ۱۸",
    "btn_remind_20": "امروز ساعت ۲۰",
    "btn_remind_tmrw": "فردا ساعت ۹ صبح",
    "btn_nl_generate": "🚀 ۱. ساخت فوری همین طرح درس",
    "btn_nl_custom_topic": "✏️ ۲. تغییر به موضوع دلخواه",
    "btn_nl_coursebook": "📖 ۳. انتخاب از کتاب درسی",
    "btn_nl_advanced_settings": "⚙️ تنظیمات پیشرفته (زمان و اولویت)",
    "btn_nl_change_mode": "🔄 تغییر حالت",
    "btn_nl_change_priority": "⚖ تغییر اولویت",
    "btn_nl_filter_sources": "📋 انتخاب سوابق موثر",
    "btn_nl_why": "💡 چرا این درس؟",
    "btn_nl_ignore": "🗑 رد این پیشنهاد",
    "btn_nl_use_as_next": "➡ استفاده به عنوان درس بعدی",

    # Profile & Attribute Labels (Persian)
    "field_name": "نام کلاس",
    "field_level": "سطح (CEFR)",
    "field_age": "رده سنی",
    "field_size": "تعداد زبان‌آموزان",
    "field_duration": "مدت زمان جلسه",
    "field_goal": "هدف اصلی آموزشی",
    "field_weak": "مهارت‌های نیازمند تمرین",
    "field_book": "کتاب و سرفصل آموزشی",
    "field_equipment": "تجهیزات و امکانات",
    "field_preference": "سبک تدریس",
    "val_not_sure": "مشخص نشده / مطمئن نیستم",
    "val_none": "هیچ‌کدام",
    "val_skipped": "رد شده",
    "val_date_not_set": "تاریخ تعیین نشده",
    "val_none_planned": "هنوز برنامه‌ریزی نشده",
    "val_none_recorded": "هنوز ثبت نشده",
    "val_none_unresolved": "بدون چالش حل‌نشده",
    "val_active_class": "کلاس فعال",
    "val_archived_class": "کلاس بایگانی‌شده",

    # Friendly Prompts & Explanations (Persian)
    "prompt_why_classes_title": "💡 چرا از «کلاس‌های من» استفاده کنیم؟",
    "prompt_why_classes_body": (
        "وقتی برای گروه آموزشی خود کلاس تعریف می‌کنید، TeacherOS سطح CEFR، رده سنی، "
        "اهداف آموزشی، کتاب درسی و تاریخچه جلسات را به خاطر می‌سپارد.\n\n"
        "این یعنی در جلسات آینده، طرح درس‌ها و تحلیل تکالیف دقیقاً بر اساس پیشرفت کلاس "
        "طراحی می‌شوند و نیازی به توضیح دوباره از صفر نیست! ✨\n\n"
        "اگر تدریس شما مقطعی یا تک‌جلسه‌ای است، می‌توانید از «⚡ ساخت سریع» استفاده کنید. "
        "فرآیند ساخت کلاس نیز بسیار سریع است و هرگز نام واقعی زبان‌آموزان را درخواست نمی‌کند."
    ),
    "prompt_class_recovery": (
        "⚠️ این بخش به‌روز شده یا منقضی شده است.\n\n"
        "هیچ تغییری اعمال نشد. لطفاً فهرست کلاس‌ها را به‌روزرسانی کنید یا به منوی اصلی بازگردید."
    ),
    "classes_list_friendly_title": "🏫 کلاس‌های من",
    "classes_list_friendly_intro": (
        "سلام همکار گرامی! اینجا می‌توانید کلاس‌های آموزشی خود را مدیریت کنید. TeacherOS با یادآوری سطح، اهداف و سوابق هر کلاس، به شما کمک می‌کند تدریسی منسجم و هدفمند داشته باشید ✨"
    ),
    "classes_list_empty_friendly": (
        "هنوز کلاسی ثبت نکرده‌اید! با زدن دکمه «➕ کلاس جدید» می‌توانید در کمتر از یک دقیقه اولین کلاس خود را بسازید، یا از «⚡ ساخت سریع» برای ابزارهای فوری استفاده نمایید 🌱"
    ),
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
