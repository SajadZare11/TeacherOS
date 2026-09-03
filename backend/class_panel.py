from __future__ import annotations

import json
import logging
import re
from typing import Any

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from class_service import ClassFeatureDisabledError, get_class, list_classes
from class_dashboard_panel import DASHBOARD_ACTIONS, handle_dashboard_callback
from class_setup_panel import CHOICE_LABELS, SETUP_ACTIONS, handle_setup_callback
from class_setup_service import get_setup_draft
from feature_flags import feature_enabled
from home_ui import teacheros_home_text
from database import register_telegram_user
from string_catalog import tr
from ui_service import resolve_lang, set_active_class
from keyboards import (
    analyze_picker_keyboard,
    class_detail_keyboard,
    class_intro_keyboard,
    class_linked_back_keyboard,
    class_list_keyboard,
    class_recovery_keyboard,
    quick_create_keyboard,
    start_menu_keyboard,
)


logger = logging.getLogger(__name__)

_CLASS_CALLBACK = re.compile(
    r"^v1\|(?P<domain>cl|rc)\|(?P<action>[a-z0-9_]{1,12})\|"
    r"(?P<object_id>[0-9a-z]{1,13})\|(?P<revision>[0-9a-z]{1,6})$"
)


async def _safe_edit(query: Any, text: str, *, reply_markup: Any) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


def _decode_base36(value: str) -> int:
    decoded = int(value, 36)
    if decoded < 1:
        raise ValueError("Expected a positive callback identifier.")
    return decoded


def _profile_lines(class_record: dict[str, Any], lang: str = "en") -> list[str]:
    try:
        setup_profile = json.loads(str(class_record.get("setup_profile_json") or "{}"))
    except json.JSONDecodeError:
        setup_profile = {}
    if not isinstance(setup_profile, dict):
        setup_profile = {}
    level = class_record.get("level") or setup_profile.get("level_choice")
    age_group = class_record.get("age_group") or setup_profile.get("age_group_choice")
    class_size = class_record.get("learner_count_band") or setup_profile.get(
        "learner_count_band_choice"
    )
    duration = class_record.get("lesson_duration_minutes")
    if isinstance(duration, int):
        duration = f"{duration} دقیقه" if lang == "fa" else f"{duration} minutes"
    coursebook = class_record.get("coursebook")
    if coursebook and class_record.get("coursebook_unit"):
        coursebook = f"{coursebook} · {class_record['coursebook_unit']}"
    elif not coursebook:
        coursebook = setup_profile.get("coursebook_state")
        if coursebook == "skipped" and lang == "fa":
            coursebook = "ثبت نشده"

    def choice_text(field: str) -> str:
        choices = setup_profile.get(field)
        if not isinstance(choices, list):
            return ""
        labels = CHOICE_LABELS.get(field, {})
        if lang == "fa":
            val_map = {
                "spk": "مکالمه", "lst": "شنیداری", "read": "خواندن", "write": "نوشتاری", "gram": "گرامر", "vocab": "واژگان", "pron": "تلفظ",
                "board": "تخته", "proj": "پروژکتور", "audio": "صوت", "print": "پرینتر", "net": "اینترنت", "none": "هیچ‌کدام",
                "comm": "مکالمه‌محور", "struct": "ساختاریافته", "task": "تکلیف‌محور", "game": "بازی و تعامل", "exam": "آزمون‌محور", "balanced": "متعادل",
            }
            return ", ".join(val_map.get(str(choice), str(choice)) for choice in choices)
        return ", ".join(
            labels.get(str(choice), str(choice).replace("_", " ").title())
            for choice in choices
        )

    def disp_val(v: Any) -> str:
        if v in {None, "not_sure", "ns"}:
            return "مطمئن نیستم" if lang == "fa" else "Not sure"
        if lang == "fa":
            val_map = {
                "young_learners": "کودکان", "teens": "نوجوانان", "adults": "بزرگسالان", "mixed": "سنین مختلف",
                "one_to_one": "تک‌نفره", "2_5": "۲ تا ۵ نفر", "6_12": "۶ تا ۱۲ نفر", "13_20": "۱۳ تا ۲۰ نفر", "21_plus": "بیش از ۲۱ نفر",
                "general_english": "انگلیسی عمومی", "conversation": "مکالمه", "exam_preparation": "آمادگی آزمون",
                "business_english": "انگلیسی تجاری", "academic_english": "انگلیسی آکادمیک", "travel_english": "انگلیسی سفر",
            }
            if str(v) in val_map:
                return val_map[str(v)]
        return str(v).replace("_", " ").title()

    if lang == "fa":
        values = (
            ("سطح (CEFR)", disp_val(level) if level else None),
            ("رده سنی", disp_val(age_group) if age_group else None),
            ("تعداد زبان‌آموزان", disp_val(class_size) if class_size else None),
            ("هدف اصلی", disp_val(class_record.get("goal")) if class_record.get("goal") else None),
            ("مدت جلسه", duration),
            ("مهارت‌های نیازمند تمرین", choice_text("weak_areas")),
            ("کتاب و درس", coursebook),
            ("امکانات کلاس", choice_text("equipment")),
            ("سبک تدریس", choice_text("teaching_preferences")),
        )
        return [f"{label}: {value}" for label, value in values if value]

    values = (
        ("Level", disp_val(level) if level else None),
        ("Age group", disp_val(age_group) if age_group else None),
        ("Class size", disp_val(class_size) if class_size else None),
        ("Cadence", class_record.get("cadence")),
        ("Goal", class_record.get("goal")),
        ("Usual duration", duration),
        ("Weak areas", choice_text("weak_areas")),
        ("Coursebook", coursebook),
        ("Equipment", choice_text("equipment")),
        ("Teaching preference", choice_text("teaching_preferences")),
    )
    return [
        f"{label}: {str(value).replace('_', ' ').title()}"
        for label, value in values
        if value
    ]


async def _recover(query: Any, context: ContextTypes.DEFAULT_TYPE, lang: str = "en") -> None:
    context.user_data.clear()
    context.user_data["lang"] = lang
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
        reply_markup=class_recovery_keyboard(lang=lang),
    )


async def _show_class_list(
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    telegram_user_id: int,
    archived: bool,
) -> None:
    context.user_data.pop("active_class", None)
    status = "archived" if archived else "active"
    records = list_classes(telegram_user_id=telegram_user_id, status=status, limit=50)
    draft = None if archived else get_setup_draft(telegram_user_id=telegram_user_id)
    lang = resolve_lang(None, context, telegram_user_id=telegram_user_id)
    if archived:
        if lang == "fa":
            text = "🗃 کلاس‌های بایگانی‌شده\n\nکلاس‌های بایگانی از فضای اصلی پنهان هستند. برای مشاهده سوابق، روی نام کلاس بزنید."
            if not records:
                text += "\n\nهیچ کلاس بایگانی‌شده‌ای ندارید."
        else:
            text = (
                "🗃 Archived Classes\n\n"
                "Archived classes are kept out of your active workspace. "
                "Open one to review its saved context."
            )
            if not records:
                text += "\n\nYou do not have any archived classes."
    else:
        if lang == "fa":
            text = (
                "🏫 کلاس‌های من\n\n"
                "اینجا لیست کلاس‌های شماست! 🎒 من سطح، درس‌های قبلی و چالش‌های زبان‌آموزان را به خاطر می‌سپارم تا هر جلسه کارتان راحت‌تر باشد."
            )
            if records:
                text += "\n\nکلاس مورد نظرتان را انتخاب کنید یا گزینه «➕ کلاس جدید» را بزنید:"
            else:
                text += (
                    "\n\nهنوز کلاسی ثبت نکرده‌اید! با زدن «➕ کلاس جدید» ظرف ۳۰ ثانیه اولین کلاستان را بسازید، یا برای دریافت سریع محتوا از «ساخت سریع» استفاده کنید ✨"
                )
        else:
            text = (
                "🏫 My Classes\n\n"
                "Here are your recurring teaching groups! 🎒 I remember their level, previous lessons, "
                "and what they struggled with, so you don't have to start from scratch each time."
            )
            if records:
                text += "\n\nChoose your class below to start planning, or tap '+ Create a Class':"
            else:
                text += (
                    "\n\nYou have no active classes yet. Tap '+ Create a Class' to get started in 30 seconds, "
                    "or use Quick Create for instant one-off materials!"
                )
    await _safe_edit(
        query,
        text,
        reply_markup=class_list_keyboard(
            records,
            archived=archived,
            has_draft=draft is not None,
            lang=lang,
        ),
    )


async def home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open a class-aware home utility while keeping legacy generator routes intact."""
    query = update.callback_query
    user = update.effective_user
    if query is None:
        return
    await query.answer()
    context.user_data.clear()
    lang = resolve_lang(update, context)

    if not feature_enabled("classes"):
        await _safe_edit(
            query,
            "TeacherOS Quick Create is ready. Choose a tool below." if lang == "en" else "بخش ساخت سریع آماده است. یکی از ابزارهای زیر را انتخاب کنید.",
            reply_markup=start_menu_keyboard(lang=lang),
        )
        return

    data = query.data or ""
    if data == "home_quick":
        if lang == "fa":
            text = f"{tr('home_quick_title', 'fa')}\n\n{tr('home_quick_body', 'fa')}"
        else:
            text = (
                "⚡ Quick Create\n\n"
                "Create a one-off resource without setting up a class. "
                "Your four existing tools work exactly as before."
            )
        await _safe_edit(
            query,
            text,
            reply_markup=quick_create_keyboard(lang=lang),
        )
        return

    if data == "home_analyze" and user is not None and isinstance(user.id, int):
        try:
            records = list_classes(
                telegram_user_id=user.id,
                status="active",
                limit=50,
            )
        except Exception:
            logger.exception("Could not load classes for Analyze Work")
            await _recover(query, context)
            return
        if lang == "fa":
            text = (
                f"{tr('home_analyze_title', 'fa')}\n\n"
                f"{tr('home_analyze_body', 'fa')}"
            )
            if not records:
                text += f"\n\n{tr('home_analyze_no_classes', 'fa')}"
        else:
            text = (
                "🔬 Analyze Work\n\n"
                "Analysis belongs to a class so TeacherOS never guesses which learners or "
                "teaching history you mean. Choose an active class first."
            )
            if not records:
                text += (
                    "\n\nYou have no active classes yet. My Classes explains what a class "
                    "remembers; Quick Create remains available for one-off work."
                )
        await _safe_edit(query, text, reply_markup=analyze_picker_keyboard(records, lang=lang))
        return

    await _recover(query, context)


async def classes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open My Classes directly from Telegram command /classes or /class."""
    if update.message is None:
        return
    user = update.effective_user
    if user is None or not isinstance(getattr(user, "id", None), int):
        return
    context.user_data.pop("active_class", None)
    records = list_classes(telegram_user_id=user.id, status="active", limit=50)
    draft = get_setup_draft(telegram_user_id=user.id)
    lang = resolve_lang(update, context)
    if lang == "fa":
        text = (
            "🏫 کلاس‌های من\n\n"
            "اینجا لیست کلاس‌های شماست! 🎒 من سطح، درس‌های قبلی و چالش‌های زبان‌آموزان را به خاطر می‌سپارم تا هر جلسه کارتان راحت‌تر باشد."
        )
        if records:
            text += "\n\nکلاس مورد نظرتان را انتخاب کنید یا گزینه «➕ کلاس جدید» را بزنید:"
        else:
            text += (
                "\n\nهنوز کلاسی ثبت نکرده‌اید! با زدن «➕ کلاس جدید» ظرف ۳۰ ثانیه اولین کلاستان را بسازید، یا برای دریافت سریع محتوا از «ساخت سریع» استفاده کنید ✨"
            )
    else:
        text = (
            "🏫 My Classes\n\n"
            "Here are your recurring teaching groups! 🎒 I remember their level, previous lessons, "
            "and what they struggled with, so you don't have to start from scratch each time."
        )
        if records:
            text += "\n\nChoose your class below to start planning, or tap '+ Create a Class':"
        else:
            text += (
                "\n\nYou have no active classes yet. Tap '+ Create a Class' to get started in 30 seconds, "
                "or use Quick Create for instant one-off materials!"
            )
    await update.message.reply_text(
        text,
        reply_markup=class_list_keyboard(records, archived=False, has_draft=draft is not None, lang=lang),
    )


async def quick_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open Quick Create directly from Telegram command /create or /quick."""
    if update.message is None:
        return
    context.user_data.clear()
    lang = resolve_lang(update, context)
    text = (
        f"{tr('home_quick_title', 'fa')}\n\n{tr('home_quick_body', 'fa')}"
        if lang == "fa"
        else (
            "⚡ Quick Create\n\n"
            "Create a one-off resource without setting up a class. "
            "Your four existing tools work exactly as before."
        )
    )
    await update.message.reply_text(
        text,
        reply_markup=quick_create_keyboard(lang=lang),
    )


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open Analyze Work directly from Telegram command /analyze or /evidence."""
    if update.message is None:
        return
    user = update.effective_user
    if user is None or not isinstance(getattr(user, "id", None), int):
        return
    context.user_data.clear()
    records = list_classes(telegram_user_id=user.id, status="active", limit=50)
    lang = resolve_lang(update, context)
    if lang == "fa":
        text = (
            f"{tr('home_analyze_title', 'fa')}\n\n"
            f"{tr('home_analyze_body', 'fa')}"
        )
        if not records:
            text += f"\n\n{tr('home_analyze_no_classes', 'fa')}"
    else:
        text = (
            "🔬 Analyze Work\n\n"
            "Analysis belongs to a class so TeacherOS never guesses which learners or "
            "teaching history you mean. Choose an active class first."
        )
        if not records:
            text += (
                "\n\nYou have no active classes yet. My Classes explains what a class "
                "remembers; Quick Create remains available for one-off work."
            )
    await update.message.reply_text(
        text,
        reply_markup=analyze_picker_keyboard(records, lang=lang),
    )


async def class_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render owner-scoped class navigation and safe stale-callback recovery."""
    query = update.callback_query
    user = update.effective_user
    if query is None:
        return
    await query.answer()
    if user is None or not isinstance(getattr(user, "id", None), int):
        await _recover(query, context)
        return
    if not feature_enabled("classes"):
        context.user_data.clear()
        await _safe_edit(
            query,
            "My Classes is not enabled. Quick Create is still available.",
            reply_markup=start_menu_keyboard(),
        )
        return

    match = _CLASS_CALLBACK.fullmatch(query.data or "")
    if match is None:
        await _recover(query, context)
        return
    domain = match.group("domain")
    action = match.group("action")

    try:
        if domain == "cl" and action in SETUP_ACTIONS:
            await handle_setup_callback(
                update,
                context,
                action=action,
                object_id=match.group("object_id"),
                revision_text=match.group("revision"),
            )
            return
        if domain == "cl" and action in DASHBOARD_ACTIONS:
            await handle_dashboard_callback(
                update,
                context,
                action=action,
                object_id=match.group("object_id"),
                revision_text=match.group("revision"),
            )
            return
        if domain == "rc" and action == "home":
            context.user_data.clear()
            lang = resolve_lang(update, context)
            await _safe_edit(
                query,
                teacheros_home_text(lang=lang),
                reply_markup=start_menu_keyboard(lang=lang),
            )
            return
        if domain == "cl" and action == "home":
            context.user_data.clear()
            lang = resolve_lang(update, context)
            await _safe_edit(
                query,
                teacheros_home_text(lang=lang),
                reply_markup=start_menu_keyboard(lang=lang),
            )
            return
        if domain == "cl" and action == "list":
            await _show_class_list(
                query,
                context,
                telegram_user_id=user.id,
                archived=False,
            )
            return
        if domain == "cl" and action == "archive":
            await _show_class_list(
                query,
                context,
                telegram_user_id=user.id,
                archived=True,
            )
            return
        lang = resolve_lang(update, context, telegram_user_id=user.id)
        if domain == "cl" and action == "why":
            context.user_data.pop("active_class", None)
            if lang == "fa":
                text = (
                    "💡 چرا ساخت کلاس در TeacherOS مفید است؟\n\n"
                    "اگر گروهی را به صورت منظم تدریس می‌کنید، با ساخت کلاس، دستیار هوشمند سطح، اهداف، سرفصل‌ها و مباحث چالش‌برانگیز جلسات قبل را به خاطر می‌سپارد.\n\n"
                    "این پیوستگی باعث می‌شود برای جلسات آینده بدون نیاز به توضیح مکرر، طرح درس‌ها و تمرینات دقیقاً متناسب با پیشرفت کلاس تولید شوند ✨\n\n"
                    "💡 اگر تنها یک تمرین یا طرح درس تکی و موردی می‌خواهید، می‌توانید مستقیماً از بخش «ساخت سریع» استفاده کنید."
                )
            else:
                text = (
                    "💡 Why Use My Classes?\n\n"
                    "Use a class for recurring teaching: TeacherOS can remember the class "
                    "label, level, goals, and lesson history. This makes later planning and "
                    "work continuous instead of starting from zero.\n\n"
                    "Use Quick Create when the work is one-off. Class setup will ask only for "
                    "short teaching context—never student names."
                )
            await _safe_edit(
                query,
                text,
                reply_markup=class_intro_keyboard(lang=lang),
            )
            return
        if domain == "rc" and action == "class":
            object_id = _decode_base36(match.group("object_id"))
            class_record = get_class(telegram_user_id=user.id, class_id=object_id)
            if class_record is None:
                await _recover(query, context, lang=lang)
                return
        elif domain == "cl" and action in {"open", "analyze"}:
            object_id = _decode_base36(match.group("object_id"))
            expected_revision = _decode_base36(match.group("revision"))
            class_record = get_class(telegram_user_id=user.id, class_id=object_id)
            if class_record is None or int(class_record["revision"]) != expected_revision:
                await _recover(query, context, lang=lang)
                return
        else:
            await _recover(query, context, lang=lang)
            return

        context.user_data.clear()
        context.user_data["lang"] = lang
        context.user_data["active_class"] = {
            "id": int(class_record["id"]),
            "display_name": str(class_record["display_name"]),
            "revision": int(class_record["revision"]),
        }
        # Persist the verified active class for class-aware tools (favorites,
        # search, and quick return). Never trust a callback ID without the
        # ownership check already performed by get_class above.
        if class_record["status"] == "active":
            try:
                set_active_class(
                    register_telegram_user(user),
                    int(class_record["id"]),
                )
            except Exception:
                logger.exception("Could not persist active class preference")
        class_name = str(class_record["display_name"])
        if action == "analyze":
            if lang == "fa":
                analyze_text = (
                    "🔬 تحلیل و شواهد یادگیری\n"
                    f"🏫 کلاس فعال: {class_name}\n\n"
                    "این قابلیت به زودی برای بررسی تکالیف، آزمون‌ها و ارزیابی نقاط قوت و ضعف کلاسی فعال خواهد شد."
                )
            else:
                analyze_text = (
                    "🔬 Analyze Work\n"
                    f"🏫 Active class: {class_name}\n\n"
                    "The class context is explicit and verified. The evidence-analysis workflow "
                    "is controlled by its own rollout flag and is not enabled on this screen yet."
                )
            await _safe_edit(
                query,
                analyze_text,
                reply_markup=class_linked_back_keyboard(
                    int(class_record["id"]),
                    int(class_record["revision"]),
                    lang=lang,
                ),
            )
            return

        if lang == "fa":
            context_label = (
                "کلاس بایگانی‌شده" if class_record["status"] == "archived" else "کلاس فعال"
            )
            lines = [
                f"🏫 {context_label}: {class_name}",
                "",
                "مشخصات و ابزارهای مرتبط با این کلاس:",
            ]
            profile = _profile_lines(class_record, lang=lang)
            if profile:
                lines.extend(["", *profile])
            if class_record["status"] == "archived":
                lines.extend(["", "وضعیت: بایگانی‌شده (فقط خواندنی)"])
        else:
            context_label = (
                "Archived class" if class_record["status"] == "archived" else "Active class"
            )
            lines = [
                f"🏫 {context_label}: {class_name}",
                "",
                "This screen is linked to the class named above.",
            ]
            profile = _profile_lines(class_record, lang=lang)
            if profile:
                lines.extend(["", *profile])
            if class_record["status"] == "archived":
                lines.extend(["", "Status: Archived (read-only context)"])
        await _safe_edit(
            query,
            "\n".join(lines),
            reply_markup=class_detail_keyboard(
                int(class_record["id"]),
                int(class_record["revision"]),
                archived=class_record["status"] == "archived",
                lang=lang,
            ),
        )
    except (ClassFeatureDisabledError, ValueError):
        await _recover(query, context)
    except Exception:
        logger.exception("Could not render TeacherOS class navigation")
        await _recover(query, context)
