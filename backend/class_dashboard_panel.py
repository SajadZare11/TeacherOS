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
    class_dashboard_keyboard,
    class_details_keyboard,
    class_profile_keyboard,
    confirmation_keyboard,
    edit_choice_keyboard,
    edit_multi_keyboard,
    edit_text_keyboard,
    lesson_cancel_confirmation_keyboard,
    lesson_history_keyboard,
    today_queue_keyboard,
)
from class_dashboard_service import (
    class_dashboard_snapshot,
    set_class_archived,
    today_queue,
    touch_class_activity,
    update_profile_field,
)
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
from database import list_class_materials
from keyboards import class_library_keyboard
from lesson_history_service import (
    cancel_planned_lesson,
    get_owned_class_lesson,
    lesson_conversion_metrics,
    list_lesson_history,
    mark_lesson_taught,
)


logger = logging.getLogger(__name__)
DASHBOARD_ACTIONS = {
    "open", "today", "details", "plan", "analyze", "create", "outcome",
    "progress", "profile", "pfedit", "edset", "edmulti", "edsave", "edclear",
    "archask", "archyes", "restask", "restyes", "library", "hist", "taught",
    "canask", "canyes",
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


def _human(value: object) -> str:
    if value in {None, "not_sure", "ns"}:
        return "Not sure"
    return str(value).replace("_", " ").title()


def _when(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "Not recorded"
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


def _choice_text(field: str, values: object) -> str:
    if not isinstance(values, list) or not values:
        return "Not sure"
    labels = CHOICE_LABELS[field]
    return ", ".join(labels.get(str(item), _human(item)) for item in values)


def _profile_lines(class_record: dict[str, Any]) -> list[str]:
    profile = _profile_data(class_record)
    book = class_record.get("coursebook")
    if book and class_record.get("coursebook_unit"):
        book = f"{book} · {class_record['coursebook_unit']}"
    if not book:
        book = "Skipped" if profile.get("coursebook_state") == "skipped" else "Not sure"
    duration = class_record.get("lesson_duration_minutes")
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


def _dashboard_text(snapshot: dict[str, Any]) -> str:
    class_record = snapshot["class"]
    profile = _profile_data(class_record)
    compact = " · ".join(
        part for part in (
            _human(class_record.get("level") or profile.get("level_choice")),
            _human(class_record.get("age_group") or profile.get("age_group_choice")),
            _human(class_record.get("learner_count_band") or profile.get("learner_count_band_choice")),
        ) if part != "Not sure"
    ) or "Profile uses explicit Not sure values"
    planned = snapshot["next_planned_lesson"]
    outcome = snapshot["last_outcome"]
    difficulty = snapshot["unresolved_difficulty"]
    context_label = "Archived class" if class_record["status"] == "archived" else "Active class"
    lines = [
        f"🏫 {context_label}: {class_record['display_name']}",
        f"{compact}",
        "",
        (
            "♻ NEXT: Restore this class to continue"
            if class_record["status"] == "archived"
            else "🎯 NEXT: Plan Next Lesson"
        ),
        "",
        "Next lesson: " + (
            f"{_short(planned['title'])} · {_short(planned.get('scheduled_for') or 'date not set', 22)}"
            if planned else "None planned"
        ),
        "Last outcome: " + (_human(outcome["result"]) if outcome else "None recorded"),
        "Difficulty: " + (
            f"{_human(difficulty['result'])}; support {_human(difficulty.get('support_needed'))}"
            if difficulty else "None unresolved"
        ),
        f"Reviews due: {snapshot['due_review_count']}",
    ]
    if snapshot["pending_analysis_count"]:
        lines.append(f"Analysis awaiting approval: {snapshot['pending_analysis_count']}")
    if snapshot["no_history"]:
        lines.extend(["", "No history yet. Start with one useful next lesson."])
    return "\n".join(lines)


def _details_text(snapshot: dict[str, Any]) -> str:
    class_record = snapshot["class"]
    counts = snapshot["history_counts"]
    return "\n".join(
        [
            f"ℹ Details · {class_record['display_name']}",
            "",
            *_profile_lines(class_record),
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
) -> str:
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


def _active_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    state = context.user_data.get("active_class")
    return state if isinstance(state, dict) else None


async def _recover(query: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await _safe_edit(
        query,
        "⚠️ This class view changed, expired, or is no longer available.\n\n"
        "No change was made. Refresh your own class list or return home.",
        class_recovery_keyboard(),
    )


async def _render_dashboard(
    query: Any,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    telegram_user_id: int,
    class_id: int,
    expected_revision: int | None,
) -> None:
    snapshot = class_dashboard_snapshot(
        telegram_user_id=telegram_user_id, class_id=class_id
    )
    if snapshot is None:
        await _recover(query, context)
        return
    class_record = snapshot["class"]
    if expected_revision and int(class_record["revision"]) != expected_revision:
        await _recover(query, context)
        return
    touch_class_activity(telegram_user_id=telegram_user_id, class_id=class_id)
    context.user_data.clear()
    context.user_data["active_class"] = {
        "id": class_id,
        "display_name": str(class_record["display_name"]),
        "revision": int(class_record["revision"]),
    }
    if class_record["status"] == "archived":
        text = _dashboard_text(snapshot) + "\n\nStatus: Archived · history preserved · read-only"
        markup = archived_dashboard_keyboard(class_id, int(class_record["revision"]))
    else:
        text = _dashboard_text(snapshot)
        markup = class_dashboard_keyboard(class_id, int(class_record["revision"]))
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
    try:
        if action == "today":
            items = today_queue(telegram_user_id=user.id)
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
            await _safe_edit(query, "\n".join(lines), today_queue_keyboard(items))
            return

        state = _active_state(context)
        lesson_record = None
        if action in {"taught", "canask", "canyes"}:
            lesson_id = int(object_id, 36)
            lesson_record = get_owned_class_lesson(
                telegram_user_id=user.id, lesson_id=lesson_id
            )
            if lesson_record is None:
                await _recover(query, context)
                return
            class_id = int(lesson_record["class_id"])
        elif action in {"edset", "edmulti", "edsave"}:
            edit_state = context.user_data.get("class_edit")
            if not isinstance(edit_state, dict):
                await _recover(query, context)
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

        snapshot = class_dashboard_snapshot(telegram_user_id=user.id, class_id=class_id)
        if snapshot is None or int(snapshot["class"]["revision"]) != revision:
            await _recover(query, context)
            return
        class_record = snapshot["class"]
        context.user_data["active_class"] = {
            "id": class_id,
            "display_name": str(class_record["display_name"]),
            "revision": revision,
        }

        if action == "details":
            await _safe_edit(
                query, _details_text(snapshot),
                class_details_keyboard(class_id, revision, archived=class_record["status"] == "archived"),
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
                _history_text(str(class_record["display_name"]), lessons, metrics),
                lesson_history_keyboard(lessons, class_id, revision),
            )
            return
        if action == "canask":
            if lesson_record is None or lesson_record.get("lifecycle_state") != "planned":
                await _recover(query, context)
                return
            await _safe_edit(
                query,
                f"Cancel planned lesson #{lesson_record['id']}?\n\n"
                f"{lesson_record['title']}\n\n"
                "The plan becomes Cancelled and remains auditable. Its generated resource stays in the library.",
                lesson_cancel_confirmation_keyboard(
                    int(lesson_record["id"]), class_id, revision
                ),
            )
            return
        if action in {"taught", "canyes"}:
            if lesson_record is None:
                await _recover(query, context)
                return
            if action == "taught":
                updated_lesson, changed = mark_lesson_taught(
                    telegram_user_id=user.id, lesson_id=int(lesson_record["id"])
                )
                notice = (
                    "✅ Marked as taught. Outcome and review workflows may now use this fact."
                    if changed else
                    "ℹ No duplicate was created. This lesson was already taught or was not planned."
                )
            else:
                updated_lesson, changed = cancel_planned_lesson(
                    telegram_user_id=user.id, lesson_id=int(lesson_record["id"])
                )
                notice = (
                    "✅ Plan cancelled. The generated resource and audit record were kept."
                    if changed else
                    "ℹ No duplicate change was made. This plan was already cancelled or was not active."
                )
            if updated_lesson is None:
                await _recover(query, context)
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
                    str(class_record["display_name"]), lessons, metrics, notice=notice
                ),
                lesson_history_keyboard(lessons, class_id, revision),
            )
            return
        if action == "profile":
            context.user_data.pop("class_edit", None)
            text = "\n".join([f"👤 Class Profile · {class_record['display_name']}", "", *_profile_lines(class_record)])
            if class_record["status"] == "archived":
                text += "\n\nArchived profiles are read-only until restored."
            await _safe_edit(
                query, text,
                class_profile_keyboard(class_id, revision, archived=class_record["status"] == "archived"),
            )
            return
        if action in {"archask", "restask"}:
            archive = action == "archask"
            if archive != (class_record["status"] == "active"):
                await _recover(query, context)
                return
            verb = "Archive" if archive else "Restore"
            effect = (
                "It leaves the active workspace, but every linked material, lesson, outcome, and action item stays intact."
                if archive else "It returns to the active workspace with all linked history intact."
            )
            await _safe_edit(
                query, f"{verb} {class_record['display_name']}?\n\n{effect}",
                confirmation_keyboard(class_id, revision, archive=archive),
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
                await _recover(query, context)
                return
            context.user_data.clear()
            await _safe_edit(
                query,
                ("✅ Class archived" if action == "archyes" else "✅ Class restored")
                + f" · {updated['display_name']}\n\nAll linked materials and history were preserved.",
                (
                    archived_dashboard_keyboard(class_id, int(updated["revision"]))
                    if action == "archyes"
                    else class_dashboard_keyboard(class_id, int(updated["revision"]))
                ),
            )
            return
        if action == "pfedit":
            if class_record["status"] != "active" or object_id not in FIELD_CODES:
                await _recover(query, context)
                return
            field_code = object_id
            field = FIELD_CODES[field_code]
            edit_state = {"class_id": class_id, "revision": revision, "field_code": field_code, "field": field}
            context.user_data["class_edit"] = edit_state
            if field_code in {"nm", "bk"}:
                edit_state["state"] = "text"
                prompt = (
                    "Type one short private class label. Never enter student names or sensitive data."
                    if field_code == "nm"
                    else "Type Coursebook | Unit as one short phrase, or choose Clear."
                )
                await _safe_edit(query, f"✏ Edit {field.replace('_', ' ').title()}\n\n{prompt}", edit_text_keyboard(class_id, revision, coursebook=field_code == "bk"))
                return
            if field_code in SINGLE_CHOICES:
                choices, _ = SINGLE_CHOICES[field_code]
                encoded = tuple((field_code + code, label) for code, label in choices)
                await _safe_edit(query, f"✏ Edit {field.replace('_', ' ').title()}\n\nSave one choice.", edit_choice_keyboard(encoded, revision))
                return
            choices, profile_key = MULTI_CHOICES[field_code]
            selected = list(_profile_data(class_record).get(profile_key, []))
            edit_state["selected"] = selected
            await _safe_edit(query, f"✏ Edit {field.replace('_', ' ').title()}\n\nChoose options, then Save this field.", edit_multi_keyboard(field_code, choices, selected, revision))
            return
        if action == "edset":
            edit_state = context.user_data.get("class_edit")
            field_code = str(edit_state.get("field_code"))
            if not object_id.startswith(field_code) or field_code not in SINGLE_CHOICES:
                await _recover(query, context)
                return
            _, value_map = SINGLE_CHOICES[field_code]
            value = value_map.get(object_id[len(field_code):])
            updated = update_profile_field(
                telegram_user_id=user.id, class_id=class_id,
                field=FIELD_CODES[field_code], value=value, expected_revision=revision,
            )
            if updated is None:
                await _recover(query, context)
                return
            context.user_data.pop("class_edit", None)
            new_revision = int(updated["revision"])
            context.user_data["active_class"] = {"id": class_id, "display_name": updated["display_name"], "revision": new_revision}
            await _safe_edit(query, "✅ Profile field updated\n\n" + "\n".join(_profile_lines(updated)), class_profile_keyboard(class_id, new_revision, archived=False))
            return
        if action == "edmulti":
            edit_state = context.user_data.get("class_edit")
            field_code = str(edit_state.get("field_code"))
            if not object_id.startswith(field_code) or field_code not in MULTI_CHOICES:
                await _recover(query, context)
                return
            code = object_id[len(field_code):]
            choices, _ = MULTI_CHOICES[field_code]
            allowed = {choice for choice, _ in choices}
            if code not in allowed:
                await _recover(query, context)
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
            await _safe_edit(query, f"✏ Edit {FIELD_CODES[field_code].replace('_', ' ').title()}\n\nChoose options, then Save this field.", edit_multi_keyboard(field_code, choices, selected, revision))
            return
        if action == "edsave":
            edit_state = context.user_data.get("class_edit")
            field_code = str(edit_state.get("field_code"))
            selected = list(edit_state.get("selected", []))
            if object_id != field_code or field_code not in MULTI_CHOICES or not selected:
                await _safe_edit(query, "Choose at least one option, including Not sure if needed.", edit_multi_keyboard(field_code, MULTI_CHOICES[field_code][0], selected, revision))
                return
            updated = update_profile_field(
                telegram_user_id=user.id, class_id=class_id,
                field=FIELD_CODES[field_code], value=selected, expected_revision=revision,
            )
            if updated is None:
                await _recover(query, context)
                return
            context.user_data.pop("class_edit", None)
            new_revision = int(updated["revision"])
            context.user_data["active_class"] = {"id": class_id, "display_name": updated["display_name"], "revision": new_revision}
            await _safe_edit(query, "✅ Profile field updated\n\n" + "\n".join(_profile_lines(updated)), class_profile_keyboard(class_id, new_revision, archived=False))
            return
        if action == "edclear":
            edit_state = context.user_data.get("class_edit")
            if not isinstance(edit_state, dict) or edit_state.get("field_code") != "bk":
                await _recover(query, context)
                return
            updated = update_profile_field(
                telegram_user_id=user.id, class_id=class_id, field="coursebook",
                value={"coursebook_state": "skipped"}, expected_revision=revision,
            )
            if updated is None:
                await _recover(query, context)
                return
            context.user_data.pop("class_edit", None)
            new_revision = int(updated["revision"])
            await _safe_edit(query, "✅ Coursebook cleared\n\n" + "\n".join(_profile_lines(updated)), class_profile_keyboard(class_id, new_revision, archived=False))
            return

        if action == "library":
            records = list_class_materials(
                telegram_user_id=user.id, class_id=class_id, limit=20
            )
            lines = [f"• #{item['id']} · {item['title']}" for item in records]
            await _safe_edit(
                query,
                f"📁 {class_record['display_name']} Library\n\n" + ("\n".join(lines) if lines else "No class-linked materials yet."),
                class_library_keyboard(records, class_id, revision),
            )
            return
        if action in {"plan", "analyze", "create", "outcome", "progress"}:
            touch_class_activity(telegram_user_id=user.id, class_id=class_id)
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
            await _safe_edit(
                query,
                f"{headings[action]}\n🏫 Active class: {class_record['display_name']}\n\n{body[action]}",
                class_action_keyboard(
                    class_id, revision, action,
                    class_aware=feature_enabled("continuity"),
                ),
            )
            return
        await _recover(query, context)
    except Exception:
        logger.exception("Could not continue class dashboard")
        await _recover(query, context)


async def get_class_dashboard_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
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
            await update.message.reply_text(
                "⚠️ This profile changed. No edit was saved. Refresh the class.",
                reply_markup=class_recovery_keyboard(),
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
        await update.message.reply_text(
            "✅ Profile field updated\n\n" + "\n".join(_profile_lines(updated)),
            reply_markup=class_profile_keyboard(class_id, revision, archived=False),
        )
    except ValueError:
        await update.message.reply_text(
            "Use one short, non-sensitive phrase. Do not include student names, email addresses, phone numbers, health, or disability information.",
            reply_markup=edit_text_keyboard(
                int(edit_state["class_id"]),
                int(edit_state["revision"]),
                coursebook=field_code == "bk",
            ),
        )
