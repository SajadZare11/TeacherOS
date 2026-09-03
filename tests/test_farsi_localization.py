from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

from string_catalog import STRINGS_EN, STRINGS_FA, tr
from home_ui import teacheros_home_text
from ui_service import resolve_lang
from keyboards import (
    account_home_keyboard,
    activity_confirm_keyboard,
    activity_type_keyboard,
    analyze_picker_keyboard,
    class_intro_keyboard,
    class_list_keyboard,
    duration_keyboard,
    generated_material_export_keyboard,
    grammar_keyboard,
    lesson_confirm_keyboard,
    level_keyboard,
    quick_create_keyboard,
    quiz_assessment_type_keyboard,
    quiz_confirm_keyboard,
    quiz_format_keyboard,
    quiz_question_count_keyboard,
    start_menu_keyboard,
    worksheet_confirm_keyboard,
    worksheet_type_keyboard,
)
from class_dashboard_keyboards import class_dashboard_keyboard
from evidence_keyboards import evidence_inbox_keyboard


class TestFarsiLocalization(unittest.TestCase):
    def test_catalog_completeness(self) -> None:
        """Every English string key has a non-empty Persian translation."""
        for key in STRINGS_EN:
            self.assertIn(key, STRINGS_FA, f"Missing Persian translation for key: {key}")
            self.assertTrue(len(STRINGS_FA[key]) > 0, f"Empty Persian string for key: {key}")

    def test_tr_function(self) -> None:
        self.assertEqual(tr("menu_my_classes", "en"), "🏫 My Classes")
        self.assertEqual(tr("menu_my_classes", "fa"), "🏫 کلاس‌های من")
        self.assertEqual(tr("menu_quick_create", "fa"), "⚡ ساخت سریع")
        self.assertEqual(tr("nav_home", "fa"), "🏠 منوی اصلی")
        self.assertEqual(tr("nav_back", "fa"), "⬅ بازگشت")
        self.assertEqual(tr("nav_cancel", "fa"), "❌ انصراف")

    def test_home_ui_farsi(self) -> None:
        text_en = teacheros_home_text("Plan: Free", lang="en")
        text_fa = teacheros_home_text("طرح: رایگان", lang="fa")
        self.assertIn("Welcome to TeacherOS", text_en)
        self.assertIn("به TeacherOS خوش آمدید", text_fa)
        self.assertIn("دستیار هوشمند شما برای تدریس زبان انگلیسی", text_fa)
        self.assertIn("طرح: رایگان", text_fa)

    def test_start_menu_keyboard_farsi(self) -> None:
        markup = start_menu_keyboard(lang="fa")
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        self.assertIn("🏫 کلاس‌های من", buttons)
        self.assertIn("⚡ ساخت سریع", buttons)
        self.assertIn("🔍 تحلیل تکالیف", buttons)
        self.assertIn("🔎 جستجو", buttons)
        self.assertIn("👤 حساب کاربری", buttons)

    def test_start_menu_keyboard_english_fallback(self) -> None:
        markup = start_menu_keyboard(lang="en")
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        self.assertIn("🏫 My Classes", buttons)
        self.assertIn("⚡ Quick Create", buttons)
        self.assertIn("🔍 Analyze Work", buttons)
        self.assertIn("🔎 Search", buttons)
        self.assertIn("👤 Account", buttons)

    def test_quick_create_keyboard_farsi(self) -> None:
        markup = quick_create_keyboard(lang="fa")
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        self.assertIn("📚 طرح درس", buttons)
        self.assertIn("🎲 فعالیت‌ها", buttons)
        self.assertIn("📝 کاربرگ‌ها", buttons)
        self.assertIn("✅ آزمون‌ها", buttons)
        self.assertIn("🏠 منوی اصلی", buttons)

    def test_account_home_keyboard_farsi(self) -> None:
        markup = account_home_keyboard(lang="fa")
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        self.assertIn("📊 مصرف من", buttons)
        self.assertIn("🪪 طرح من", buttons)
        self.assertIn("📁 کتابخانه عمومی", buttons)
        self.assertIn("⭐ امتیاز به بات", buttons)
        self.assertIn("🌐 Language / زبان", buttons)
        self.assertIn("🧭 راهنما", buttons)
        self.assertIn("ℹ️ راهنما و قوانین", buttons)
        self.assertIn("🏠 منوی اصلی", buttons)

    def test_class_list_keyboard_farsi(self) -> None:
        classes = [{"id": 1, "revision": 1, "display_name": "IELTS Prep"}]
        markup = class_list_keyboard(classes, archived=False, has_draft=True, lang="fa")
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        self.assertIn("🏫 IELTS Prep", buttons)
        self.assertIn("☀ تدریس امروز", buttons)
        self.assertIn("▶ ادامه ثبت کلاس", buttons)
        self.assertIn("➕ کلاس جدید", buttons)
        self.assertIn("🗃 کلاس‌های بایگانی", buttons)
        self.assertIn("💡 چرا کلاس بسازیم؟", buttons)
        self.assertIn("🏠 منوی اصلی", buttons)

    def test_class_intro_keyboard_farsi(self) -> None:
        markup = class_intro_keyboard(lang="fa")
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        self.assertIn("⬅ کلاس‌های من", buttons)
        self.assertIn("⚡ ساخت سریع محتوا", buttons)
        self.assertIn("🏠 منوی اصلی", buttons)

    def test_analyze_picker_keyboard_farsi(self) -> None:
        classes = [{"id": 1, "revision": 1, "display_name": "General English"}]
        markup = analyze_picker_keyboard(classes, lang="fa")
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        self.assertIn("🏫 کلاس‌های من", buttons)
        self.assertIn("🏠 منوی اصلی", buttons)

    def test_class_dashboard_keyboard_farsi(self) -> None:
        markup = class_dashboard_keyboard(1, 1, lang="fa")
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        self.assertIn("🎯 طرح درس", buttons)
        self.assertIn("🔬 تحلیل تکالیف", buttons)
        self.assertIn("🧰 تولید محتوا", buttons)
        self.assertIn("✅ ثبت نتیجه تدریس", buttons)
        self.assertIn("🔁 مرور دوره‌ای", buttons)
        self.assertIn("📈 روند پیشرفت", buttons)
        self.assertIn("📚 سرفصل آموزشی", buttons)
        self.assertIn("📁 کتابخانه کلاس", buttons)
        self.assertIn("👤 مشخصات کلاس", buttons)
        self.assertIn("🎯 تدریس تمایزیافته", buttons)
        self.assertIn("جزئیات بیشتر", buttons)
        self.assertIn("📚 تاریخچه تدریس", buttons)
        self.assertIn("⬅ کلاس‌های من", buttons)
        self.assertIn("☀ تدریس امروز", buttons)

    def test_generator_keyboards_farsi(self) -> None:
        lvl = level_keyboard("lesson", "back_cb", lang="fa")
        lvl_btns = [btn.text for row in lvl.inline_keyboard for btn in row]
        self.assertIn("⬅ بازگشت", lvl_btns)
        self.assertIn("❌ انصراف", lvl_btns)

        dur = duration_keyboard(lang="fa")
        dur_btns = [btn.text for row in dur.inline_keyboard for btn in row]
        self.assertIn("۳۰ دقیقه", dur_btns)
        self.assertIn("۴۵ دقیقه", dur_btns)
        self.assertIn("۶۰ دقیقه", dur_btns)
        self.assertIn("۹۰ دقیقه", dur_btns)

        grm = grammar_keyboard(lang="fa")
        grm_btns = [btn.text for row in grm.inline_keyboard for btn in row]
        self.assertIn("رد شدن از گرامر", grm_btns)

        les_conf = lesson_confirm_keyboard(class_mode=True, lang="fa")
        les_btns = [btn.text for row in les_conf.inline_keyboard for btn in row]
        self.assertIn("🚀 تولید طرح درس", les_btns)
        self.assertIn("✏ تغییر موقت سطح/مدت", les_btns)

        act = activity_type_keyboard(lang="fa")
        act_btns = [btn.text for row in act.inline_keyboard for btn in row]
        self.assertTrue(any("مکالمه" in b for b in act_btns))
        self.assertTrue(any("ایفای نقش" in b for b in act_btns))

        wks = worksheet_type_keyboard(lang="fa")
        wks_btns = [btn.text for row in wks.inline_keyboard for btn in row]
        self.assertTrue(any("واژگان" in b for b in wks_btns))
        self.assertTrue(any("گرامر" in b for b in wks_btns))
        self.assertTrue(any("درک مطلب" in b for b in wks_btns))

        quiz = quiz_assessment_type_keyboard(lang="fa")
        quiz_btns = [btn.text for row in quiz.inline_keyboard for btn in row]
        self.assertTrue(any("کوئیز کلاسی" in b for b in quiz_btns))
        self.assertTrue(any("آزمون درس" in b for b in quiz_btns))

        quiz_fmt = quiz_format_keyboard(lang="fa")
        quiz_fmt_btns = [btn.text for row in quiz_fmt.inline_keyboard for btn in row]
        self.assertTrue(any("چندگزینه‌ای" in b for b in quiz_fmt_btns))

        quiz_cnt = quiz_question_count_keyboard(lang="fa")
        quiz_cnt_btns = [btn.text for row in quiz_cnt.inline_keyboard for btn in row]
        self.assertIn("۵ سوال", quiz_cnt_btns)
        self.assertIn("۱۰ سوال", quiz_cnt_btns)
        self.assertIn("✍️ تعداد دلخواه", quiz_cnt_btns)

    def test_export_keyboard_farsi(self) -> None:
        markup = generated_material_export_keyboard(101, material_type="lesson", class_id=1, lang="fa")
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        self.assertIn("💾 ذخیره", buttons)
        self.assertIn("🎯 تدریس تمایزیافته", buttons)
        self.assertIn("⚡ تطبیق محتوا", buttons)
        self.assertIn("✏ ویرایش دلخواه", buttons)
        self.assertIn("📄 دانلود نسخه Word", buttons)
        self.assertIn("🧾 دانلود نسخه PDF", buttons)
        self.assertIn("🔁 بازتولید با تغییرات", buttons)
        self.assertIn("🚩 گزارش مشکل", buttons)
        self.assertIn("➡ استفاده به عنوان درس بعدی", buttons)
        self.assertIn("📁 باز کردن کتابخانه", buttons)
        self.assertIn("🏠 منوی اصلی", buttons)

    def test_evidence_inbox_keyboard_farsi(self) -> None:
        markup = evidence_inbox_keyboard(1, 1, [], lang="fa")
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        self.assertIn("➕ ثبت تکلیف و شواهد", buttons)
        self.assertIn("✍️ تصحیح و بازخورد رایتینگ", buttons)
        self.assertIn("◀ بازگشت به داشبورد", buttons)

    def test_resolve_lang_caching(self) -> None:
        context = SimpleNamespace(user_data={"lang": "fa"})
        self.assertEqual(resolve_lang(None, context), "fa")

        context_en = SimpleNamespace(user_data={"lang": "en"})
        self.assertEqual(resolve_lang(None, context_en), "en")

        context_empty = SimpleNamespace(user_data={})
        self.assertEqual(resolve_lang(None, context_empty), "en")

    def test_class_setup_keyboards_farsi(self) -> None:
        from class_setup_keyboards import (
            setup_entry_keyboard,
            choice_keyboard,
            multi_keyboard,
            review_keyboard,
            saved_keyboard,
        )
        entry_markup = setup_entry_keyboard(has_draft=True, can_template=False, lang="fa")
        entry_btns = [btn.text for row in entry_markup.inline_keyboard for btn in row]
        self.assertIn("▶ ادامه ثبت کلاس", entry_btns)
        self.assertIn("🗑 حذف پیش‌نویس ذخیره‌شده", entry_btns)
        self.assertIn("⬅ کلاس‌های من", entry_btns)

        options = (("b1", "B1 Intermediate"), ("b2", "B2 Upper Intermediate"))
        choice_markup = choice_keyboard("lvl", options, 1, lang="fa")
        choice_btns = [btn.text for row in choice_markup.inline_keyboard for btn in row]
        self.assertIn("B1 Intermediate", choice_btns)
        self.assertIn("⬅ بازگشت", choice_btns)
        self.assertIn("💾 ذخیره پیش‌نویس", choice_btns)
        self.assertIn("❌ انصراف", choice_btns)

        rev_markup = review_keyboard(1, 1, lang="fa")
        rev_btns = [btn.text for row in rev_markup.inline_keyboard for btn in row]
        self.assertIn("✅ ساخت و ثبت کلاس", rev_btns)
        self.assertIn("✏ نام کلاس", rev_btns)

        saved_markup = saved_keyboard(lang="fa")
        saved_btns = [btn.text for row in saved_markup.inline_keyboard for btn in row]
        self.assertIn("▶ ادامه ثبت کلاس", saved_btns)
        self.assertIn("⬅ کلاس‌های من", saved_btns)

    def test_class_dashboard_keyboards_farsi(self) -> None:
        from class_dashboard_keyboards import (
            class_details_keyboard,
            class_profile_keyboard,
            lesson_history_keyboard,
            outcome_result_keyboard,
            outcome_difficulty_keyboard,
            outcome_completion_keyboard,
            outcome_summary_keyboard,
            next_lesson_recommendation_keyboard,
            next_lesson_modes_keyboard,
            next_lesson_priorities_keyboard,
        )
        det_markup = class_details_keyboard(1, 1, archived=False, lang="fa")
        det_btns = [btn.text for row in det_markup.inline_keyboard for btn in row]
        self.assertIn("⬅ صفحه اصلی کلاس", det_btns)
        self.assertIn("👤 ویرایش مشخصات", det_btns)

        prof_markup = class_profile_keyboard(1, 1, archived=False, lang="fa")
        prof_btns = [btn.text for row in prof_markup.inline_keyboard for btn in row]
        self.assertIn("✏ نام کلاس", prof_btns)
        self.assertIn("✏ سطح (CEFR)", prof_btns)
        self.assertIn("⬅ صفحه اصلی کلاس", prof_btns)

        hist_markup = lesson_history_keyboard([], 1, 1, lang="fa")
        hist_btns = [btn.text for row in hist_markup.inline_keyboard for btn in row]
        self.assertIn("⬅ صفحه اصلی کلاس", hist_btns)

        res_markup = outcome_result_keyboard(1, 1, lang="fa")
        res_btns = [btn.text for row in res_markup.inline_keyboard for btn in row]
        self.assertIn("✅ کاملاً محقق شد", res_btns)
        self.assertIn("⚠️ تا حدی محقق شد", res_btns)
        self.assertIn("🔄 نیاز به تدریس مجدد", res_btns)

        diff_markup = outcome_difficulty_keyboard(1, "a", 0, 1, lang="fa")
        diff_btns = [btn.text for row in diff_markup.inline_keyboard for btn in row]
        self.assertIn("بدون چالش خاص", diff_btns)
        self.assertIn("ثبت موارد چالش‌برانگیز", diff_btns)

        comp_markup = outcome_completion_keyboard(1, "a", 0, 1, lang="fa")
        comp_btns = [btn.text for row in comp_markup.inline_keyboard for btn in row]
        self.assertIn("کامل تدریس شد", comp_btns)
        self.assertIn("بخشی از درس تدریس شد", comp_btns)

        sum_markup = outcome_summary_keyboard(1, 1, 1, has_note=False, lang="fa")
        sum_btns = [btn.text for row in sum_markup.inline_keyboard for btn in row]
        self.assertIn("📝 افزودن یادداشت", sum_btns)
        self.assertIn("تایید و بازگشت به کلاس", sum_btns)

        rec_markup = next_lesson_recommendation_keyboard({"id": 1, "effective_mode": "recommendation", "priority_mode": "balanced"}, 1, 1, lang="fa")
        rec_btns = [btn.text for row in rec_markup.inline_keyboard for btn in row]
        self.assertIn("🚀 ۱. ساخت فوری همین طرح درس", rec_btns)
        self.assertIn("✏️ ۲. تغییر به موضوع دلخواه", rec_btns)
        self.assertIn("📖 ۳. انتخاب از کتاب درسی", rec_btns)

        modes_markup = next_lesson_modes_keyboard(1, "recommendation", 1, lang="fa")
        modes_btns = [btn.text for row in modes_markup.inline_keyboard for btn in row]
        self.assertIn("✅ 🎯 بر اساس پیشنهاد هوشمند", modes_btns)
        self.assertIn("🔄 تکمیل مطالب قبلی", modes_btns)
        self.assertIn("🔁 مرور و بازآموزی چالش‌ها", modes_btns)

        prio_markup = next_lesson_priorities_keyboard(1, "balanced", 1, lang="fa")
        prio_btns = [btn.text for row in prio_markup.inline_keyboard for btn in row]
        self.assertIn("✅ ⚖ بهینه و متعادل (خودکار)", prio_btns)
        self.assertIn("🔁 اولویت با رفع چالش‌ها", prio_btns)

    def test_class_dashboard_panel_farsi_texts(self) -> None:
        from class_dashboard_panel import (
            _dashboard_text,
            _details_text,
            _outcome_picker_text,
            _outcome_result_text,
            _outcome_difficulty_text,
            _outcome_completion_text,
            _outcome_summary_text,
            _next_lesson_rec_text,
            _next_lesson_why_text,
        )
        snapshot = {
            "class": {
                "id": 1,
                "display_name": "کلاس خصوصی آیلتس",
                "level": "B2",
                "age_group": "adults",
                "learner_count_band": "one_to_one",
                "lesson_duration_minutes": 60,
                "goal": "exam_preparation",
                "status": "active",
                "revision": 1,
                "setup_profile_json": "{}",
                "last_active_at": "2026-09-02T12:00:00Z",
            },
            "next_planned_lesson": None,
            "last_outcome": {"result": "achieved"},
            "unresolved_difficulty": None,
            "outcome_recording_rate_percent": 100,
            "due_review_count": 0,
            "pending_analysis_count": 0,
            "no_history": False,
            "history_counts": {"lessons": 3, "outcomes": 3, "materials": 2, "generated": 1, "planned": 1, "taught": 2, "cancelled": 0},
        }
        dash_fa = _dashboard_text(snapshot, lang="fa")
        self.assertIn("کلاس فعال: کلاس خصوصی آیلتس", dash_fa)
        self.assertIn("بزرگسالان", dash_fa)
        self.assertIn("تک‌نفره (خصوصی)", dash_fa)
        self.assertIn("کاملاً محقق شد", dash_fa)
        self.assertNotIn("Profile uses explicit Not sure values", dash_fa)

        det_fa = _details_text(snapshot, lang="fa")
        self.assertIn("جزئیات و آمار کلاس", det_fa)
        self.assertIn("تعداد طرح درس‌ها: 3", det_fa)
        self.assertIn("تدریس‌شده", det_fa)

        picker_fa = _outcome_picker_text("کلاس خصوصی آیلتس", [], {"outcomes_recorded": 0, "taught": 0, "recording_rate_percent": 0}, lang="fa")
        self.assertIn("ثبت بازخورد و نتیجه تدریس", picker_fa)
        self.assertNotIn("pilot target is 60%", picker_fa)

        res_fa = _outcome_result_text({"id": 1, "display_name": "کلاس آیلتس", "title": "Speaking Practice"}, lang="fa")
        self.assertIn("مرحله ۱ از ۳", res_fa)

        diff_fa = _outcome_difficulty_text({"id": 1, "display_name": "کلاس آیلتس", "title": "Speaking Practice"}, 0, lang="fa")
        self.assertIn("مرحله ۲ از ۳", diff_fa)

        comp_fa = _outcome_completion_text({"id": 1, "display_name": "کلاس آیلتس", "title": "Speaking Practice"}, ["none"], lang="fa")
        self.assertIn("مرحله ۳ از ۳", comp_fa)

        rec = {
            "effective_mode": "recommendation",
            "priority_mode": "balanced",
            "duration_minutes": 60,
            "rationale": "مرور مباحث گذشته و آماده‌سازی برای آزمون",
            "sources": [],
            "objective_labels": ["تمرین ساختار شرطی نوع دوم"],
        }
        rec_fa = _next_lesson_rec_text("کلاس آیلتس", rec, lang="fa")
        self.assertIn("آماده‌سازی طرح درس", rec_fa)
        self.assertIn("تمرین ساختار شرطی نوع دوم", rec_fa)

        why_fa = _next_lesson_why_text("کلاس آیلتس", rec, lang="fa")
        self.assertIn("چرا این مبحث پیشنهاد شد؟", why_fa)


if __name__ == "__main__":
    unittest.main()

