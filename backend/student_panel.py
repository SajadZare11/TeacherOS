from __future__ import annotations

import json
import logging
from typing import Any
from telegram import Update
from telegram.ext import ContextTypes

from student_diagnostic_service import (
    SKILLS,
    SKILL_LABELS_FA,
    SKILL_LABELS_EN,
    create_student,
    get_student,
    list_students_by_class,
    update_student_identity,
    update_learning_profile,
    update_student_goals,
    update_student_preferences,
    record_skill_score,
    get_student_strengths,
    get_student_areas_for_development,
    add_student_error,
    list_student_errors,
    update_error_status,
    create_class_assessment,
    list_class_assessments,
    record_student_assessment_result,
    get_student_assessment_results,
    get_student_longitudinal_progress,
    log_student_engagement,
    get_latest_engagement_and_confidence,
    construct_student_ai_context,
    save_student_recommendation,
    get_latest_student_recommendation,
)
from student_keyboards import (
    class_students_list_keyboard,
    student_hub_keyboard,
    student_category1_keyboard,
    student_category2_keyboard,
    student_category3_keyboard,
    class_assessments_keyboard,
)
from ui_service import resolve_lang

logger = logging.getLogger(__name__)


def _from_b36(text: str) -> int:
    try:
        return int(text, 36)
    except Exception:
        return 0


async def _safe_edit(query: Any, text: str, reply_markup: Any = None) -> None:
    try:
        await query.edit_message_text(text=text, reply_markup=reply_markup)
    except Exception:
        if query.message:
            await query.message.reply_text(text=text, reply_markup=reply_markup)


# ---------------------------------------------------------------------------
# Visual Formatting Functions
# ---------------------------------------------------------------------------

def _student_hub_text(student: dict[str, Any], strengths: dict[str, float], areas: list[dict[str, Any]], lang: str = "fa") -> str:
    name = student["full_name"]
    age = f"{student['age']} ساله" if student.get("age") else "ثبت‌نشده"
    lang_native = student.get("native_language", "فارسی")
    cls_name = student.get("class_name", "")

    if lang == "fa":
        lines = [
            f"👤 پرونده جامع آموزشی · {name}",
            f"🎒 کلاس: {cls_name} · سن: {age} · زبان مادری: {lang_native}",
            "",
            "✨ همکار گرامی، اطلاعات این زبان‌آموز در ۳ بخش زیر سازمان‌دهی شده است:",
            "",
            "۱. 📋 پروفایل و هویت (Profile):",
            "   • هویت، سن و زبان مادری",
            "   • سطوح مهارتی CEFR و اعتمادبه‌نفس (۷ مهارت)",
            "   • اهداف بلندمدت و کوتاه‌مدت",
            "   • ترجیحات و رفتارهای یادگیری",
            "",
            "۲. ⚡ وضعیت فعلی و مهارت‌ها (Current State):",
            "   • نقاط قوت (میانگین نمرات بالای ۱۰ از ۲۰)",
            "   • نقاط نیازمند تقویت (نمرات زیر ۱۰ + یادداشت تشخیصی)",
            "   • پروفایل خطاهای زبانی ثبت‌شده",
            "   • سطح اعتمادبه‌نفس مهارتی و ابعاد انگیزه",
            "",
            "۳. 📈 سوابق، آزمون‌ها و پیشرفت (History & Progress):",
            "   • کارنامه آزمون‌های کلاسی (رسمی و غیررسمی)",
            "   • روند طولی رشد مهارت‌ها",
            "   • تعامل، نظم و پویایی کلاسی",
            "   • 🤖 پیشنهاد هوشمند گام بعدی (AI Co-Teacher)",
            "",
            "برای مشاهده جزئیات یا ویرایش هر بخش، دکمه مربوطه را لمس کنید 👇",
        ]
        return "\n".join(lines)

    lines = [
        f"👤 Student Diagnostic Hub · {name}",
        f"🎒 Class: {cls_name} · Age: {student.get('age') or 'N/A'} · Native: {lang_native}",
        "",
        "Organized into 3 pedagogical categories:",
        "",
        "1. 📋 Profile & Identity (CEFR, Goals, Preferences)",
        "2. ⚡ Current State (Strengths, Development Areas, Errors, Confidence)",
        "3. 📈 History & Progress (Class Assessments, Trajectory, Engagement, AI Next-Step)",
        "",
        "Select a category below to view or update 👇",
    ]
    return "\n".join(lines)


def _category1_profile_text(student: dict[str, Any], lang: str = "fa") -> str:
    name = student["full_name"]
    profile = json.loads(student.get("learning_profile_json") or "{}")
    goals = json.loads(student.get("goals_json") or "{}")
    prefs = json.loads(student.get("preferences_json") or "{}")

    if lang == "fa":
        lines = [
            f"📋 دسته‌بندی ۱: پروفایل و هویت · {name}",
            "",
            "📌 بخش ۱: مشخصات فردی (هویت)",
            f"• نام: {name}",
            f"• سن: {student.get('age') or 'ثبت نشده'}",
            f"• زبان مادری: {student.get('native_language', 'فارسی')}",
            "",
            "📊 بخش ۲: سطوح مهارتی CEFR و اعتمادبه‌نفس:",
        ]
        if profile:
            for sk, data in profile.items():
                lbl = SKILL_LABELS_FA.get(sk, sk)
                lines.append(f"• {lbl}: سطح {data.get('cefr', 'B1')} (اعتماد: {data.get('confidence', 'متوسط')})")
        else:
            lines.append("• هنوز سطحی برای مهارت‌ها ثبت نشده است (پیش‌فرض B1).")

        lines.extend([
            "",
            "🎯 بخش ۳: اهداف آموزشی:",
            f"• اهداف بلندمدت: {', '.join(goals.get('long_term', [])) or 'ثبت نشده'}",
            f"• هدف کوتاه‌مدت: {goals.get('short_term', 'ثبت نشده')}",
            "",
            "🧩 بخش ۴: ترجیحات و رفتارهای یادگیری:",
            f"• فعالیت‌های مورد علاقه: {', '.join(prefs.get('preferred_activities', [])) or 'ثبت نشده'}",
            f"• ویژگی‌های یادگیری: {', '.join(prefs.get('learning_behaviors', [])) or 'ثبت نشده'}",
        ])
        return "\n".join(lines)

    lines = [
        f"📋 Category 1: Profile & Identity · {name}",
        "",
        f"Section 1: Identity · Name: {name} · Age: {student.get('age') or 'N/A'} · Native: {student.get('native_language', 'Persian')}",
        "",
        "Section 2: Learning Profile (CEFR & Confidence):",
    ]
    for sk, data in profile.items():
        lines.append(f"• {SKILL_LABELS_EN.get(sk, sk)}: {data.get('cefr')} · Confidence: {data.get('confidence')}")
    lines.extend([
        "",
        f"Section 3: Goals · Long-term: {', '.join(goals.get('long_term', [])) or 'None'} · Short-term: {goals.get('short_term') or 'None'}",
        "",
        f"Section 4: Preferences: {', '.join(prefs.get('preferred_activities', [])) or 'None'}",
    ])
    return "\n".join(lines)


def _category2_current_state_text(
    student: dict[str, Any],
    strengths: dict[str, float],
    areas: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    latest_conf: dict[str, Any] | None,
    lang: str = "fa",
) -> str:
    name = student["full_name"]
    if lang == "fa":
        lines = [
            f"⚡ دسته‌بندی ۲: وضعیت فعلی و مهارت‌ها · {name}",
            "",
            "🌟 بخش ۵: نقاط قوت مهارتی (میانگین نمرات جلسات از ۲۰):",
        ]
        if strengths:
            for sk, sc in strengths.items():
                lbl = SKILL_LABELS_FA.get(sk, sk)
                bar = "🟢" if sc >= 14 else ("🟡" if sc >= 10 else "🔴")
                lines.append(f"• {lbl}: {sc} از ۲۰ {bar}")
        else:
            lines.append("• هنوز نمره‌ای برای جلسات ثبت نشده است.")

        lines.extend([
            "",
            "⚠️ بخش ۶: نقاط نیازمند تقویت (نمرات زیر ۱۰ + یادداشت تشخیصی):",
        ])
        if areas:
            for a in areas[:4]:
                lbl = SKILL_LABELS_FA.get(a["skill"], a["skill"])
                lines.append(f"• {lbl} (نمره {a['score']} از ۲۰): {a['notes']}")
        else:
            lines.append("• موردی زیر ۱۰ ثبت نشده؛ تمام مهارت‌ها در سطح رضایت‌بخش هستند ✨")

        lines.extend([
            "",
            f"📝 بخش ۷: پروفایل خطاهای زبانی (تعداد کل: {len(errors)}):",
        ])
        active_errs = [e for e in errors if e["status"] != "solved"]
        if active_errs:
            for e in active_errs[:3]:
                lbl = SKILL_LABELS_FA.get(e["category"], e["category"])
                lines.append(f"• [{lbl}] «{e['example_text']}» (تکرار: {e['frequency']} · وضعیت: {e['status']})")
        else:
            lines.append("• خطای فعال یا ثبت‌شده‌ای وجود ندارد.")

        lines.extend([
            "",
            "🧘 بخش ۱۰ب: اعتمادبه‌نفس مهارتی و ابعاد انگیزه:",
        ])
        if latest_conf and latest_conf.get("confidence"):
            c_items = [f"{SKILL_LABELS_FA.get(k, k)}: {v}/5" for k, v in latest_conf["confidence"].items()]
            lines.append(f"• اعتمادبه‌نفس مهارت‌ها: {', '.join(c_items)}")
        else:
            lines.append("• اعتمادبه‌نفس مهارت‌ها: ثبت نشده (پیش‌فرض ۳ از ۵)")
        if latest_conf and latest_conf.get("motivation"):
            mot = latest_conf["motivation"]
            lines.append(f"• انگیزه فعلی: {mot.get('current_motivation', 'خوب')} · تعهد به هدف: {mot.get('goal_commitment', 'بالا')}")

        return "\n".join(lines)

    lines = [
        f"⚡ Category 2: Current State · {name}",
        "",
        "Section 5: Strengths (Mean Scores / 20):",
    ]
    for sk, sc in strengths.items():
        lines.append(f"• {SKILL_LABELS_EN.get(sk, sk)}: {sc}/20")
    lines.extend([
        "",
        f"Section 6: Areas for Development ({len(areas)} flagged):",
    ])
    for a in areas[:3]:
        lines.append(f"• {a['skill']} ({a['score']}/20): {a['notes']}")
    lines.extend([
        "",
        f"Section 7: Active Errors ({len(errors)} logged)",
        "",
        "Section 10b: Confidence & Motivation",
    ])
    return "\n".join(lines)


def _category3_history_text(
    student: dict[str, Any],
    assessments: list[dict[str, Any]],
    progress: dict[str, Any],
    latest_eng: dict[str, Any] | None,
    lang: str = "fa",
) -> str:
    name = student["full_name"]
    if lang == "fa":
        lines = [
            f"📈 دسته‌بندی ۳: سوابق، آزمون‌ها و پیشرفت · {name}",
            "",
            "📑 بخش ۸: نتایج آزمون‌های کلاسی (رسمی و غیررسمی):",
        ]
        if assessments:
            for a in assessments:
                t = "رسمی" if a.get("assessment_type") == "formal" else "غیررسمی"
                lines.append(f"• [{t}] {a['assessment_title']}: نمره {a['score']} از {a['max_score']}")
        else:
            lines.append("• هنوز نتیجه آزمونی برای این زبان‌آموز ثبت نشده است.")

        lines.extend([
            "",
            f"📈 بخش ۹: روند طولی پیشرفت مهارت‌ها:",
            f"• تعداد ارزیابی‌های ثبت‌شده جلسات: {len(progress.get('skill_history', []))} رکورد",
            f"• تعداد آزمون‌های گذرانده‌شده: {len(progress.get('assessment_history', []))} آزمون",
            "",
            "🤝 بخش ۱۰الف: تعامل، انگیزه و نظم کلاسی:",
        ])
        if latest_eng and latest_eng.get("engagement"):
            eng = latest_eng["engagement"]
            lines.extend([
                f"• حضور: {eng.get('attendance', 'حاضر')} · وقت‌شناسی: {eng.get('punctuality', 'به‌موقع')}",
                f"• مشارکت: {eng.get('participation', 'فعال')} · انجام تکالیف: {eng.get('homework_completion', 'کامل')}",
                f"• ریسک‌پذیری در صحبت: {eng.get('risk_taking', 'خوب')} · تعامل با همکلاسی‌ها: {eng.get('peer_interaction', 'مثبت')}",
            ])
        else:
            lines.append("• شاخص‌های تعاملی: مشارکت فعال، حضور منظم و انجام تکالیف (پیش‌فرض مثبت).")

        lines.extend([
            "",
            "🤖 بخش ۱۱: پیشنهاد هوشمند گام بعدی (AI Co-Teacher):",
            "برای تحلیل تمام سوابق و دریافت نسخه آموزشی جلسه آینده، دکمه پیشنهاد هوشمند را بزنید ✨",
        ])
        return "\n".join(lines)

    lines = [
        f"📈 Category 3: History & Progress · {name}",
        "",
        f"Section 8: Assessments ({len(assessments)} recorded)",
        f"Section 9: Longitudinal Progress ({len(progress.get('skill_history', []))} records)",
        "Section 10a: Engagement & Interaction",
        "Section 11: AI Next-Step Prescription",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Router for Student Callbacks (v1|st|... and v1|ca|...)
# ---------------------------------------------------------------------------

async def handle_student_dashboard_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, object_id: str, extra_id: str | None = None
) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await query.answer()

    lang = resolve_lang(update, context)
    user_id = update.effective_user.id

    # 1. List students of a class: v1|st|list|{class_id}|{revision}
    if action == "list":
        class_id = _from_b36(object_id)
        revision = _from_b36(extra_id or "1")
        students = list_students_by_class(user_id, class_id)
        text = (
            f"👥 دانش‌آموزان کلاس\n\n"
            f"تعداد زبان‌آموزان ثبت‌شده: {len(students)} نفر\n\n"
            "روی نام هر زبان‌آموز بزنید تا پرونده جامع و مهارت‌هایش را ببینید 👇"
            if lang == "fa"
            else f"👥 Class Students ({len(students)} enrolled)\n\nTap a student to open their file 👇"
        )
        await _safe_edit(query, text, class_students_list_keyboard(class_id, revision, students, lang=lang))
        return

    # 2. Add student prompt: v1|st|add|{class_id}|{revision}
    if action == "add":
        class_id = _from_b36(object_id)
        revision = _from_b36(extra_id or "1")
        context.user_data["student_input"] = {
            "mode": "add_student",
            "class_id": class_id,
            "revision": revision,
        }
        prompt = (
            "➕ افزودن دانش‌آموز جدید به کلاس\n\n"
            "لطفاً نام و نام خانوادگی زبان‌آموز را ارسال فرمایید (مثال: علی رضایی):\n\n"
            "نکته: می‌توانید سن را هم با خط فاصله اضافه کنید (مثال: علی رضایی - ۲۵)"
            if lang == "fa"
            else "➕ Add New Student\n\nEnter the student's full name (e.g. Ali Rezaei or Ali Rezaei - 25):"
        )
        await _safe_edit(query, prompt, None)
        return

    # 3. Student Hub: v1|st|hub|{student_id}|{class_id}
    if action == "hub":
        student_id = _from_b36(object_id)
        class_id = _from_b36(extra_id or "0")
        student = get_student(user_id, student_id)
        if not student:
            await query.answer("دانش‌آموز یافت نشد.", show_alert=True)
            return
        strengths = get_student_strengths(user_id, student_id)
        areas = get_student_areas_for_development(user_id, student_id)
        text = _student_hub_text(student, strengths, areas, lang=lang)
        await _safe_edit(query, text, student_hub_keyboard(student_id, class_id, lang=lang))
        return

    # 4. Category 1: Profile (Sections 1-4)
    if action == "cat1":
        student_id = _from_b36(object_id)
        class_id = _from_b36(extra_id or "0")
        student = get_student(user_id, student_id)
        if not student:
            return
        text = _category1_profile_text(student, lang=lang)
        await _safe_edit(query, text, student_category1_keyboard(student_id, class_id, lang=lang))
        return

    # 5. Category 2: Current State (Sections 5, 6, 7, 10b)
    if action == "cat2":
        student_id = _from_b36(object_id)
        class_id = _from_b36(extra_id or "0")
        student = get_student(user_id, student_id)
        if not student:
            return
        strengths = get_student_strengths(user_id, student_id)
        areas = get_student_areas_for_development(user_id, student_id)
        errors = list_student_errors(user_id, student_id)
        latest_conf = get_latest_engagement_and_confidence(user_id, student_id)
        text = _category2_current_state_text(student, strengths, areas, errors, latest_conf, lang=lang)
        await _safe_edit(query, text, student_category2_keyboard(student_id, class_id, lang=lang))
        return

    # 6. Category 3: History & Progress (Sections 8, 9, 10a, 11)
    if action == "cat3":
        student_id = _from_b36(object_id)
        class_id = _from_b36(extra_id or "0")
        student = get_student(user_id, student_id)
        if not student:
            return
        assessments = get_student_assessment_results(user_id, student_id)
        progress = get_student_longitudinal_progress(user_id, student_id)
        latest_eng = get_latest_engagement_and_confidence(user_id, student_id)
        text = _category3_history_text(student, assessments, progress, latest_eng, lang=lang)
        await _safe_edit(query, text, student_category3_keyboard(student_id, class_id, lang=lang))
        return

    # 7. Quick scoring: v1|st|rate|{student_id}|{class_id}
    if action == "rate":
        student_id = _from_b36(object_id)
        class_id = _from_b36(extra_id or "0")
        context.user_data["student_input"] = {
            "mode": "rate_skill",
            "student_id": student_id,
            "class_id": class_id,
        }
        prompt = (
            "➕ ثبت نمره مهارت‌های این جلسه (از ۲۰)\n\n"
            "لطفاً نام مهارت و نمره را با خط فاصله ارسال فرمایید:\n"
            "مهارت‌ها: speaking, listening, reading, writing, grammar, vocabulary, pronunciation\n\n"
            "مثال ۱: speaking - 18\n"
            "مثال ۲ (اگر نمره زیر ۱۰ باشد یادداشت الزامی است):\n"
            "listening - 8 - مشکل در تشخیص کلمات پیوسته"
            if lang == "fa"
            else "➕ Score Student Skills (0-20)\n\nFormat: skill - score - optional note\nExample: speaking - 17\nExample for <10: listening - 8 - struggles with fast connected speech"
        )
        await _safe_edit(query, prompt, None)
        return

    # 8. Add Error: v1|st|adderr|{student_id}|{class_id}
    if action == "adderr":
        student_id = _from_b36(object_id)
        class_id = _from_b36(extra_id or "0")
        context.user_data["student_input"] = {
            "mode": "add_error",
            "student_id": student_id,
            "class_id": class_id,
        }
        prompt = (
            "➕ ثبت خطای زبانی زبان‌آموز\n\n"
            "لطفاً نمونه خطا و دسته‌بندی را بفرستید:\n"
            "فرمت: نمونه خطا | دسته‌بندی | تکرار (low/medium/high)\n\n"
            "مثال: She don't like coffee | grammar | high"
            if lang == "fa"
            else "➕ Log a Language Error\n\nFormat: example error | category | frequency\nExample: She don't like coffee | grammar | high"
        )
        await _safe_edit(query, prompt, None)
        return

    # 9. Section 11: AI Next-Step Recommendation: v1|st|ai|{student_id}|{class_id}
    if action == "ai":
        student_id = _from_b36(object_id)
        class_id = _from_b36(extra_id or "0")
        student = get_student(user_id, student_id)
        if not student:
            return

        wait_msg = (
            "🤖 در حال تحلیل پرونده کامل و تدوین پیشنهاد آموزشی گام بعدی...\n\n"
            "TeacherOS تمام سوابق، نقاط قوت و ضعف، خطاها و آزمون‌ها را بررسی می‌کند ✨"
            if lang == "fa"
            else "🤖 Synthesizing full diagnostic history to generate next-step prescription..."
        )
        await _safe_edit(query, wait_msg, None)

        ctx = construct_student_ai_context(user_id, student_id)
        st_name = student["full_name"]
        strengths_txt = ", ".join(f"{k}: {v}/20" for k, v in ctx["strengths"].items()) or "هنوز نمره‌ای ثبت نشده"
        areas_txt = ", ".join(f"{a['skill']} ({a['score']}/20): {a['notes']}" for a in ctx["areas_for_dev"]) or "ندارد"
        errors_txt = ", ".join(f"{e['example_text']} ({e['category']})" for e in ctx["active_errors"]) or "ندارد"

        rec_text = (
            f"🎯 نسخه آموزشی اختصاصی برای جلسه آینده · {st_name}\n\n"
            f"۱. تمرکز اصلی یادگیری (Immediate Priority):\n"
            f"با توجه به ارزیابی‌ها، اولویت تقویت مهارت‌های {areas_txt} همراه با تثبیت نقاط قوت ({strengths_txt}) است.\n\n"
            f"۲. تمرین و فعالیت‌های پیشنهادی (Tailored Practice):\n"
            f"انجام فعالیت‌های مکالمه دونفره (Pair Work) با تمرکز روی اصلاح خطاهای پرتکرار مانند «{errors_txt}» در قالب سناریوهای روزمره.\n\n"
            f"۳. راهبرد تدریس معلم در کلاس (Scaffolding Strategy):\n"
            f"به این زبان‌آموز قبل از پاسخ‌گویی فرصت تفکر (Preparation Time) بدهید و از فیدبک اصلاحی غیرمستقیم (Recast) استفاده کنید ✨"
            if lang == "fa"
            else (
                f"🎯 Personalized Next-Step Prescription · {st_name}\n\n"
                f"1. Immediate Focus: Target areas for development ({areas_txt}) while anchoring strengths ({strengths_txt}).\n"
                f"2. Tailored Activities: Scaffolded communicative tasks addressing recurring patterns: {errors_txt}.\n"
                f"3. Teacher Strategy: Allow prep time before eliciting verbal production."
            )
        )
        save_student_recommendation(user_id, student_id, rec_text)
        await _safe_edit(query, rec_text, student_hub_keyboard(student_id, class_id, lang=lang))
        return


# ---------------------------------------------------------------------------
# Router for Class Assessments (v1|ca|...)
# ---------------------------------------------------------------------------

async def handle_class_assessment_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, object_id: str, extra_id: str | None = None
) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await query.answer()

    lang = resolve_lang(update, context)
    user_id = update.effective_user.id

    # View assessments list: v1|ca|list|{class_id}|{revision}
    if action == "list":
        class_id = _from_b36(object_id)
        revision = _from_b36(extra_id or "1")
        assessments = list_class_assessments(user_id, class_id)
        text = (
            f"📝 ارزیابی کلاسی و آزمون‌ها\n\n"
            f"در این بخش می‌توانید آزمون‌های رسمی (فاینال، میدترم، آیلتس) یا ارزیابی‌های غیررسمی (کوییز، مشاهده کلاسی) را برای کل کلاس تعریف کرده و نمرات زبان‌آموزان را ثبت نمایید."
            if lang == "fa"
            else "📝 Class Assessments & Tests\n\nSet up formal or informal assessments for this class."
        )
        await _safe_edit(query, text, class_assessments_keyboard(class_id, revision, assessments, lang=lang))
        return

    # Add formal: v1|ca|add_f|{class_id}
    if action == "add_f":
        class_id = _from_b36(object_id)
        context.user_data["assessment_input"] = {"class_id": class_id, "type": "formal"}
        prompt = (
            "➕ تعریف آزمون رسمی جدید\n\n"
            "لطفاً عنوان آزمون و نوع آن را ارسال فرمایید:\n"
            "انواع معتبر: placement, midterm, final, ielts, speaking\n\n"
            "مثال: فاینال ترم تابستان - final - 100"
            if lang == "fa"
            else "➕ Add Formal Assessment\n\nFormat: title - subtype (placement/midterm/final/ielts/speaking) - max score\nExample: Midterm Exam - midterm - 100"
        )
        await _safe_edit(query, prompt, None)
        return

    # Add informal: v1|ca|add_inf|{class_id}
    if action == "add_inf":
        class_id = _from_b36(object_id)
        context.user_data["assessment_input"] = {"class_id": class_id, "type": "informal"}
        prompt = (
            "➕ تعریف ارزیابی غیررسمی جدید\n\n"
            "لطفاً عنوان ارزیابی و نوع آن را ارسال فرمایید:\n"
            "انواع معتبر: observation, classroom_task, mini_quiz, writing_sample\n\n"
            "مثال: کوییز درس ۱ تا ۳ - mini_quiz - 20"
            if lang == "fa"
            else "➕ Add Informal Assessment\n\nFormat: title - subtype (observation/classroom_task/mini_quiz/writing_sample) - max score\nExample: Vocab Quiz 1 - mini_quiz - 20"
        )
        await _safe_edit(query, prompt, None)
        return


# ---------------------------------------------------------------------------
# Message Handler for Text Input
# ---------------------------------------------------------------------------

async def handle_student_message_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.message is None or update.effective_user is None or not update.message.text:
        return False

    lang = resolve_lang(update, context)
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # 1. Student text inputs
    st_input = context.user_data.get("student_input")
    if isinstance(st_input, dict):
        mode = st_input.get("mode")
        if mode == "add_student":
            class_id = int(st_input["class_id"])
            revision = int(st_input.get("revision", 1))
            parts = [p.strip() for p in text.split("-", 1)]
            name = parts[0]
            age = None
            if len(parts) > 1:
                try:
                    age = int("".join(c for c in parts[1] if c.isdigit()))
                except Exception:
                    pass
            try:
                st = create_student(user_id, class_id, full_name=name, age=age)
                context.user_data.pop("student_input", None)
                students = list_students_by_class(user_id, class_id)
                success_msg = f"✅ زبان‌آموز «{name}» با موفقیت اضافه شد." if lang == "fa" else f"✅ Student '{name}' added."
                await update.message.reply_text(
                    success_msg,
                    reply_markup=class_students_list_keyboard(class_id, revision, students, lang=lang),
                )
                return True
            except Exception as exc:
                await update.message.reply_text(f"⚠️ {exc}")
                return True

        if mode == "rate_skill":
            student_id = int(st_input["student_id"])
            class_id = int(st_input["class_id"])
            parts = [p.strip() for p in text.split("-")]
            if len(parts) >= 2:
                skill = parts[0].lower()
                try:
                    score = float(parts[1])
                    notes = parts[2] if len(parts) > 2 else None
                    record_skill_score(user_id, student_id, skill=skill, score=score, notes=notes)
                    context.user_data.pop("student_input", None)
                    success_msg = f"✅ نمره مهارت {skill} ({score} از ۲۰) با موفقیت ثبت شد." if lang == "fa" else f"✅ Score recorded."
                    await update.message.reply_text(
                        success_msg,
                        reply_markup=student_category2_keyboard(student_id, class_id, lang=lang),
                    )
                    return True
                except Exception as exc:
                    await update.message.reply_text(f"⚠️ {exc}")
                    return True

        if mode == "add_error":
            student_id = int(st_input["student_id"])
            class_id = int(st_input["class_id"])
            parts = [p.strip() for p in text.split("|")]
            if len(parts) >= 2:
                example = parts[0]
                cat = parts[1].lower()
                freq = parts[2].lower() if len(parts) > 2 else "medium"
                try:
                    add_student_error(user_id, student_id, example_text=example, category=cat, frequency=freq)
                    context.user_data.pop("student_input", None)
                    success_msg = f"✅ خطای زبانی ثبت شد." if lang == "fa" else "✅ Error logged."
                    await update.message.reply_text(
                        success_msg,
                        reply_markup=student_category2_keyboard(student_id, class_id, lang=lang),
                    )
                    return True
                except Exception as exc:
                    await update.message.reply_text(f"⚠️ {exc}")
                    return True

    # 2. Assessment text inputs
    ass_input = context.user_data.get("assessment_input")
    if isinstance(ass_input, dict):
        class_id = int(ass_input["class_id"])
        ass_type = ass_input["type"]
        parts = [p.strip() for p in text.split("-")]
        if len(parts) >= 2:
            title = parts[0]
            subtype = parts[1].lower().replace(" ", "_")
            max_sc = 100.0
            if len(parts) > 2:
                try:
                    max_sc = float(parts[2])
                except Exception:
                    pass
            try:
                create_class_assessment(user_id, class_id, assessment_type=ass_type, subtype=subtype, title=title, max_score=max_sc)
                context.user_data.pop("assessment_input", None)
                assessments = list_class_assessments(user_id, class_id)
                success_msg = f"✅ آزمون «{title}» با موفقیت ثبت شد." if lang == "fa" else f"✅ Assessment '{title}' created."
                await update.message.reply_text(
                    success_msg,
                    reply_markup=class_assessments_keyboard(class_id, 1, assessments, lang=lang),
                )
                return True
            except Exception as exc:
                await update.message.reply_text(f"⚠️ {exc}")
                return True

    return False
