from __future__ import annotations

import logging
import re
from typing import Any

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from class_service import list_classes
from class_dashboard_keyboards import class_dashboard_keyboard
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


logger = logging.getLogger(__name__)
SETUP_ACTIONS = {
    "new", "begin", "template", "resume", "back", "skip", "level", "age",
    "size", "duration", "goal", "weak", "equip", "prefer", "next", "edit",
    "save", "draft", "cancel", "discard", "dropyes",
}

LEVELS = (("a1", "A1"), ("a2", "A2"), ("b1", "B1"), ("b2", "B2"), ("c1", "C1"), ("c2", "C2"), ("ns", "Not sure"))
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


def _screen(draft: dict[str, Any]) -> tuple[str, Any]:
    step = draft["step"]
    rev = int(draft["revision"])
    p = draft["payload"]
    if step == "name":
        return (
            "1/10 · Private class label\n\nType one short label, such as ‘B1 Evening’. "
            "It helps you recognize the class. Do not enter student names or sensitive information.",
            typed_step_keyboard(rev),
        )
    if step == "level":
        return ("2/10 · CEFR level\n\nLevel helps TeacherOS control language difficulty. Choose Not sure rather than guessing.", choice_keyboard("level", LEVELS, rev))
    if step == "age":
        return ("3/10 · Age group\n\nAn age band improves activity style. Do not enter birthdays or learner profiles.", choice_keyboard("age", AGES, rev))
    if step == "size":
        return ("4/10 · Class-size range\n\nA range helps TeacherOS choose pair, group, or individual work.", choice_keyboard("size", SIZES, rev))
    if step == "duration":
        return ("5/10 · Usual lesson duration\n\nDuration keeps plans realistic. Choose Not sure if lessons vary.", choice_keyboard("duration", DURATIONS, rev))
    if step == "goal":
        return ("6/10 · Main goal\n\nThe main goal keeps future resources focused.", choice_keyboard("goal", GOALS, rev))
    if step == "weak":
        return ("7/10 · Weak areas\n\nSelect any areas that often need practice, then Continue. Use Not sure instead of guessing.", multi_keyboard("weak", WEAK, list(p.get("weak_areas", [])), rev))
    if step == "book":
        return ("8/10 · Coursebook and unit (optional)\n\nType a short phrase like ‘English File | Unit 4’, or Skip. This aligns future work with your syllabus. Do not enter student data.", typed_step_keyboard(rev, skip=True))
    if step == "equipment":
        return ("9/10 · Available equipment\n\nSelect what is normally available, then Continue. This prevents unusable activity suggestions.", multi_keyboard("equip", EQUIPMENT, list(p.get("equipment", [])), rev))
    if step == "preference":
        return ("10/10 · Teaching preference\n\nSelect the styles you prefer, then Continue. TeacherOS uses these as preferences, not assumptions.", multi_keyboard("prefer", PREFERENCES, list(p.get("teaching_preferences", [])), rev))
    return (_review_text(p), review_keyboard(int(draft["id"]), rev))


def _display(value: Any) -> str:
    if value in {None, "not_sure"}:
        return "Not sure"
    return str(value).replace("_", " ").title()


def _display_choices(field: str, value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "Missing"
    labels = CHOICE_LABELS[field]
    return ", ".join(labels.get(str(item), _display(item)) for item in value)


def _review_text(p: dict[str, Any]) -> str:
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


async def _render(query: Any, context: ContextTypes.DEFAULT_TYPE, draft: dict[str, Any]) -> None:
    text, markup = _screen(draft)
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
    try:
        draft = get_setup_draft(telegram_user_id=user.id)
        classes = list_classes(telegram_user_id=user.id, include_archived=True, limit=1)
        if action == "new":
            await _safe_edit(
                query,
                "➕ Create a Class\n\n"
                "Setup uses buttons and one short phrase at a time. You can save and finish later. "
                "Use classes for recurring teaching; use Quick Create for one-off work. "
                "Store class context, never student names, disabilities, health data, or sensitive profiles.",
                setup_entry_keyboard(can_template=bool(classes), has_draft=draft is not None),
            )
            return
        if action in {"begin", "template"}:
            if draft is None:
                template = classes[0] if action == "template" and classes else None
                draft = start_setup_draft(telegram_user=user, template=template)
            await _render(query, context, draft)
            return
        if action == "resume":
            if draft is None:
                await _safe_edit(query, "⚠️ No saved class draft is available. No change was made.", class_recovery_keyboard())
            else:
                await _render(query, context, draft)
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
            await _safe_edit(
                query,
                ("✅ Class created" if created else "✅ Class already created")
                + f"\n\n🏫 Active class: {class_record['display_name']}\n\nYour saved context is ready.",
                class_dashboard_keyboard(int(class_record["id"]), int(class_record["revision"])),
            )
            return
        if draft is None:
            await _safe_edit(query, "⚠️ This setup changed or expired. No change was made.", class_recovery_keyboard())
            return
        supplied_revision = _revision(revision_text)
        if supplied_revision not in {0, int(draft["revision"])}:
            await _safe_edit(query, "⚠️ This setup changed or expired. No change was made.", class_recovery_keyboard())
            return
        if action == "draft":
            context.user_data.clear()
            await _safe_edit(query, "💾 Class draft saved\n\nResume from My Classes whenever you are ready.", saved_keyboard())
            return
        if action == "cancel":
            await _safe_edit(query, "Pause setup?\n\nKeep the saved draft, continue now, or explicitly discard it.", cancel_keyboard(int(draft["revision"])))
            return
        if action == "discard":
            await _safe_edit(query, "Discard this class draft?\n\nThis cannot be undone. No completed class will be changed.", discard_keyboard(int(draft["revision"])))
            return
        if action == "dropyes":
            discard_setup_draft(telegram_user_id=user.id)
            context.user_data.clear()
            await _safe_edit(query, "🗑 Draft discarded. No class was created.", class_recovery_keyboard())
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
                await _safe_edit(query, "🏫 My Classes", class_recovery_keyboard())
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
                await _safe_edit(query, "Choose at least one option, including Not sure if needed.\n\n" + _screen(draft)[0], _screen(draft)[1])
                return
            updated = _advance(user.id, draft, payload, NEXT_STEP[draft["step"]])
        else:
            raise ValueError("Unknown setup action.")
        if updated is None:
            await _safe_edit(query, "⚠️ This setup changed or expired. No change was made.", class_recovery_keyboard())
        else:
            await _render(query, context, updated)
    except ClassLimitReachedError as exc:
        access = exc.access
        await _safe_edit(query, f"⛔ Active class limit reached\n\nPlan: {access['plan_name']}\nActive classes: {access['active_classes']}\nLimit: {access['class_limit']}\n\nYour draft is still saved.", saved_keyboard())
    except Exception:
        logger.exception("Could not continue class setup")
        await _safe_edit(query, "⚠️ Class setup could not continue. Your last saved draft is unchanged.", class_recovery_keyboard())


def _advance(user_id: int, draft: dict[str, Any], payload: dict[str, Any], normal_next: str) -> dict[str, Any] | None:
    next_step = "review" if payload.pop("_return_to_review", False) else normal_next
    return save_setup_draft(telegram_user_id=user_id, expected_revision=draft["revision"], step=next_step, payload=payload)


async def get_class_setup_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("class_setup")
    if not isinstance(state, dict) or update.message is None or update.effective_user is None:
        return
    user = update.effective_user
    text = " ".join((update.message.text or "").split())
    draft = get_setup_draft(telegram_user_id=user.id)
    if draft is None or draft["id"] != state.get("draft_id") or draft["revision"] != state.get("revision"):
        context.user_data.pop("class_setup", None)
        await update.message.reply_text("⚠️ This setup changed or expired. Resume it from My Classes.", reply_markup=saved_keyboard())
        return
    step = str(state.get("state"))
    maximum = 60 if step == "name" else 80
    word_limit = 10 if step == "name" else 14
    if not text or len(text) > maximum or len(text.split()) > word_limit or re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|\b\+?\d[\d -]{7,}\d\b", text):
        await update.message.reply_text(f"Please enter one short, non-sensitive phrase (up to {word_limit} words). Do not include names, email addresses, phone numbers, health, or disability information.", reply_markup=typed_step_keyboard(int(draft["revision"]), skip=step == "book"))
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
        await update.message.reply_text("⚠️ This setup changed. Resume the latest saved draft.", reply_markup=saved_keyboard())
        return
    screen_text, markup = _screen(updated)
    if updated["step"] in {"name", "book"}:
        context.user_data["class_setup"] = {"state": updated["step"], "revision": updated["revision"], "draft_id": updated["id"]}
    else:
        context.user_data.pop("class_setup", None)
    await update.message.reply_text(screen_text, reply_markup=markup)
