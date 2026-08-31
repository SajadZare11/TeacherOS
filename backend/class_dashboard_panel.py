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
    "open", "today", "details", "plan", "analyze", "create", "outcome",
    "progress", "profile", "pfedit", "edset", "edmulti", "edsave", "edclear",
    "archask", "archyes", "restask", "restyes", "library", "hist", "taught",
    "canask", "canyes", "ostart", "ores", "odiff", "odone", "odnext",
    "ocomp", "oedit", "onote", "onclear", "oskip", "oremind", "orsave",
    "nlrec", "nlmode", "nlmset", "nlprio", "nlpset", "nlsrc", "nltog",
    "nlwhy", "nlgen", "nlign", "nlman", "nlfa",
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
    difficulty_values = (
        [
            OUTCOME_DIFFICULTY_LABELS.get(str(item), _human(item))
            for item in difficulty.get("difficulty_categories", [])
            if item != "none"
        ]
        if difficulty else []
    )
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
        "Last outcome: " + (
            OUTCOME_RESULT_LABELS.get(str(outcome["result"]), _human(outcome["result"]))
            if outcome else "None recorded"
        ),
        "Difficulty: " + (
            ", ".join(difficulty_values)
            if difficulty_values else f"{_human(difficulty['result'])}; support {_human(difficulty.get('support_needed'))}"
            if difficulty else "None unresolved"
        ),
        f"Outcome capture: {snapshot.get('outcome_recording_rate_percent', 0)}% of taught lessons",
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
    class_name: str, lessons: list[dict[str, Any]], metrics: dict[str, int]
) -> str:
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
            "The pilot target is 60%; friction is diagnosed before incentives are added.",
        ]
    )
    return "\n".join(lines)


def _outcome_result_text(lesson: dict[str, Any], *, notice: str | None = None) -> str:
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
            "No note is required. You can save the three facts first.",
        ]
    )
    return "\n".join(lines)


def _outcome_difficulty_text(lesson: dict[str, Any], mask: int, *, notice: str | None = None) -> str:
    selected = _difficulty_values(mask) if mask else []
    lines = [
        f"✅ Post-lesson check-in · {lesson['display_name']}",
        f"Lesson #{lesson['id']}: {_short(lesson['title'], 52)}", "",
        "Tap 2 of 3 · Difficulties",
        "Choose No major difficulty for the normal three-tap path, or select every category that applied.",
    ]
    if selected:
        lines.extend(["", "Selected: " + ", ".join(OUTCOME_DIFFICULTY_LABELS[item] for item in selected)])
    if notice:
        lines.extend(["", notice])
    return "\n".join(lines)


def _outcome_completion_text(lesson: dict[str, Any], difficulties: list[str]) -> str:
    return "\n".join(
        [
            f"✅ Post-lesson check-in · {lesson['display_name']}",
            f"Lesson #{lesson['id']}: {_short(lesson['title'], 52)}", "",
            "Tap 3 of 3 · Completion",
            "How much of the planned lesson was completed?",
            "Difficulty: " + ", ".join(OUTCOME_DIFFICULTY_LABELS[item] for item in difficulties),
            "Your tap saves the facts immediately. An optional note comes afterward.",
        ]
    )


def _outcome_summary_text(
    outcome: dict[str, Any], metrics: dict[str, int], *, notice: str | None = None
) -> str:
    difficulties = outcome.get("difficulty_categories") or []
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
        "Recorded facts are stored separately from any later AI suggestion.",
    ]
    if notice:
        lines.extend(["", notice])
    return "\n".join(lines)


def _next_lesson_rec_text(
    class_name: str, rec: dict[str, Any], *, notice: str | None = None
) -> str:
    mode = rec.get("effective_mode") or rec.get("recommended_mode")
    mode_title = MODE_LABELS.get(str(mode), str(mode).replace("_", " ").title())
    prio = str(rec.get("priority_mode", "balanced")).title()
    uncertainty = str(rec.get("uncertainty", "low")).upper()
    duration = rec.get("duration_minutes", 60)
    objectives = rec.get("objective_labels") or []
    sources = rec.get("sources", [])
    included_count = sum(1 for s in sources if s.get("included") == 1)

    lines = [
        f"🎯 Plan Next Lesson · {class_name}",
        "",
        f"Proposed mode: {mode_title}",
        f"Priority: {prio} · Uncertainty: {uncertainty}",
        f"Duration: {duration} mins · Active sources: {included_count}/{len(sources)}",
        "",
        f"Rationale: {rec['rationale']}",
    ]
    if rec.get("teacher_request") and mode == "manual":
        lines.extend(["", f"Custom topic: {_short(rec['teacher_request'], 60)}"])
    if objectives:
        lines.extend(["", "Target objective(s):"] + [f"• {_short(obj, 60)}" for obj in objectives[:3]])
    if notice:
        lines.extend(["", notice])
    lines.extend([
        "",
        "Review the proposed direction above. You can change mode, priority, or active sources before generating.",
    ])
    return "\n".join(lines)


def _next_lesson_why_text(class_name: str, rec: dict[str, Any]) -> str:
    sources = rec.get("sources", [])
    included = [s for s in sources if s.get("included") == 1]
    lines = [
        f"💡 Why this next? · {class_name}",
        "",
        f"Rationale: {rec['rationale']}",
        f"Uncertainty: {str(rec.get('uncertainty', 'low')).upper()} ({rec.get('uncertainty_reason', '')})",
        "",
        "Records used:",
    ]
    if not included:
        lines.append("• No specific historical records included; relying on general class profile.")
    else:
        for s in included:
            lines.append(f"• [{s['source_type'].replace('_', ' ')}] {s['source_label']}\n  {_short(s['fact_summary'], 90)}")
    return "\n".join(lines)


def _next_lesson_modes_text(class_name: str, rec: dict[str, Any]) -> str:
    current = rec.get("selected_mode") or "recommendation (auto)"
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


def _next_lesson_priorities_text(class_name: str, rec: dict[str, Any]) -> str:
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


def _next_lesson_sources_text(class_name: str, rec: dict[str, Any]) -> str:
    sources = rec.get("sources", [])
    included_count = sum(1 for s in sources if s.get("included") == 1)
    return "\n".join([
        f"📋 Active History Sources · {class_name}",
        "",
        f"Active records: {included_count} of {len(sources)}",
        "Tap any record to include (✅) or exclude (▫️) it from the next lesson proposal.",
    ])


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
                await _recover(query, context)
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
                await _recover(query, context)
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
                await _recover(query, context)
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
                await _recover(query, context)
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
                await _recover(query, context)
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
                await _recover(query, context)
                return
            class_id = int(lesson_record["class_id"])
        elif action in {"nlrec", "nlmode", "nlprio", "nlsrc", "nlwhy", "nlgen", "nlign", "nlman"}:
            rec_id = _decode_positive_base36(object_id)
            rec_record = get_recommendation(
                telegram_user_id=user.id, recommendation_id=rec_id
            )
            if rec_record is None:
                await _recover(query, context)
                return
            class_id = int(rec_record["class_id"])
        elif action == "nlmset":
            selected_mode_code = object_id[0]
            rec_id = _decode_positive_base36(object_id[1:])
            rec_record = get_recommendation(
                telegram_user_id=user.id, recommendation_id=rec_id
            )
            if rec_record is None or selected_mode_code not in NEXT_LESSON_MODE_CODES:
                await _recover(query, context)
                return
            class_id = int(rec_record["class_id"])
        elif action == "nlpset":
            selected_prio_code = object_id[0]
            rec_id = _decode_positive_base36(object_id[1:])
            rec_record = get_recommendation(
                telegram_user_id=user.id, recommendation_id=rec_id
            )
            if rec_record is None or selected_prio_code not in NEXT_LESSON_PRIO_CODES:
                await _recover(query, context)
                return
            class_id = int(rec_record["class_id"])
        elif action == "nltog":
            source_link_id = _decode_positive_base36(object_id)
            rec_record = toggle_recommendation_source(
                telegram_user_id=user.id, source_link_id=source_link_id
            )
            if rec_record is None:
                await _recover(query, context)
                return
            class_id = int(rec_record["class_id"])
        elif action == "nlfa":
            followup_accepted = object_id[0] == "1"
            plan_id = _decode_positive_base36(object_id[1:])
            plan_row = record_next_lesson_followup(
                telegram_user_id=user.id, plan_id=plan_id, accepted=followup_accepted
            )
            if not plan_row:
                await _recover(query, context)
                return
            revision = int(revision_text, 36)
            class_id = int(state["id"]) if state else 0
            if class_id == 0:
                snapshot = class_dashboard_snapshot(telegram_user_id=user.id, class_id=int(object_id[1:], 36) if len(object_id) > 1 else 0)
                if snapshot:
                    class_id = int(snapshot["class"]["id"])
            await _safe_edit(
                query,
                "✅ Thank you! Your feedback on this lesson recommendation was saved.\n\n"
                "TeacherOS uses this to improve future suggestions.",
                InlineKeyboardMarkup([[InlineKeyboardButton("Done · Class Home", callback_data=_cb("open", class_id or 1, revision))]]),
            )
            return
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
        if action == "outcome":
            if class_record["status"] != "active":
                await _recover(query, context)
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
                    str(class_record["display_name"]), outcome_lessons, outcome_metrics
                ),
                outcome_lesson_picker_keyboard(outcome_lessons, class_id, revision),
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
                await _recover(query, context)
                return
        if action in {"ostart", "oedit"}:
            existing_outcome = get_lesson_outcome(
                telegram_user_id=user.id, lesson_id=int(lesson_record["id"])
            )
            notice = (
                "Correction mode: the next save updates the same outcome and keeps a fact revision."
                if existing_outcome is not None else None
            )
            await _safe_edit(
                query,
                _outcome_result_text(lesson_record, notice=notice),
                outcome_result_keyboard(int(lesson_record["id"]), revision),
            )
            return
        if action == "ores":
            await _safe_edit(
                query,
                _outcome_difficulty_text(lesson_record, 0),
                outcome_difficulty_keyboard(
                    int(lesson_record["id"]), str(outcome_result_code), 0, revision
                ),
            )
            return
        if action == "odiff":
            bit = OUTCOME_DIFFICULTY_OPTION_BITS[str(outcome_option_code)]
            outcome_mask ^= 1 << bit
            await _safe_edit(
                query,
                _outcome_difficulty_text(lesson_record, outcome_mask),
                outcome_difficulty_keyboard(
                    int(lesson_record["id"]), str(outcome_result_code), outcome_mask, revision
                ),
            )
            return
        if action in {"odone", "odnext"}:
            if action == "odnext" and outcome_mask == 0:
                await _safe_edit(
                    query,
                    _outcome_difficulty_text(
                        lesson_record, 0,
                        notice="Choose at least one category, or tap No major difficulty.",
                    ),
                    outcome_difficulty_keyboard(
                        int(lesson_record["id"]), str(outcome_result_code), 0, revision
                    ),
                )
                return
            difficulties = _difficulty_values(outcome_mask)
            await _safe_edit(
                query,
                _outcome_completion_text(lesson_record, difficulties),
                outcome_completion_keyboard(
                    int(lesson_record["id"]), str(outcome_result_code), outcome_mask, revision
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
                await _recover(query, context)
                return
            metrics = outcome_recording_metrics(
                telegram_user_id=user.id, class_id=class_id
            )
            notice = (
                "Saved before asking for prose. Add a note only if it helps."
                if changed else "No duplicate was created; these facts were already saved."
            )
            await _safe_edit(
                query,
                _outcome_summary_text(outcome, metrics, notice=notice),
                outcome_summary_keyboard(
                    int(lesson_record["id"]), class_id, revision,
                    has_note=bool(outcome.get("notes")),
                ),
            )
            return
        if action == "onote":
            outcome = get_lesson_outcome(
                telegram_user_id=user.id, lesson_id=int(lesson_record["id"])
            )
            if outcome is None:
                await _recover(query, context)
                return
            context.user_data["outcome_note"] = {
                "state": "text", "lesson_id": int(lesson_record["id"]),
                "class_id": class_id, "revision": revision,
            }
            await _safe_edit(
                query,
                "📝 Optional teacher note\n\nType up to 1,000 characters, or skip. "
                "Do not include student names, email addresses, phone numbers, health, or disability information.",
                outcome_note_keyboard(
                    int(lesson_record["id"]), class_id, revision,
                    has_note=bool(outcome.get("notes")),
                ),
            )
            return
        if action == "onclear":
            outcome, changed = update_outcome_note(
                telegram_user_id=user.id, lesson_id=int(lesson_record["id"]), note=None
            )
            if outcome is None:
                await _recover(query, context)
                return
            context.user_data.pop("outcome_note", None)
            metrics = outcome_recording_metrics(
                telegram_user_id=user.id, class_id=class_id
            )
            await _safe_edit(
                query,
                _outcome_summary_text(
                    outcome, metrics,
                    notice="Optional note cleared." if changed else "The optional note was already empty.",
                ),
                outcome_summary_keyboard(
                    int(lesson_record["id"]), class_id, revision, has_note=False
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
            await _safe_edit(
                query,
                _outcome_summary_text(outcome, metrics, notice="Optional note skipped."),
                outcome_summary_keyboard(
                    int(lesson_record["id"]), class_id, revision,
                    has_note=bool(outcome.get("notes")),
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
                await _safe_edit(
                    query,
                    _outcome_summary_text(
                        existing_outcome, metrics,
                        notice="This outcome is already recorded; no reminder is needed.",
                    ),
                    outcome_summary_keyboard(
                        int(lesson_record["id"]), class_id, revision,
                        has_note=bool(existing_outcome.get("notes")),
                    ),
                )
                return
            await _safe_edit(
                query,
                f"⏰ One-shot outcome reminder\n\nLesson #{lesson_record['id']}: "
                f"{_short(lesson_record['title'], 52)}\n\nChoose a local time. "
                "TeacherOS sends only this explicit reminder; it does not repeat automatically.",
                outcome_reminder_keyboard(int(lesson_record["id"]), revision),
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
                notice = (
                    "Reminder already scheduled; duplicate callback ignored."
                    if reminder_result["status"] == "already_scheduled"
                    else "One reminder scheduled. It will not repeat unless you explicitly snooze it."
                )
                await _safe_edit(
                    query,
                    f"✅ {notice}\n\nDue: {due_text}\nLesson: {_short(lesson_record['title'], 52)}",
                    outcome_reminder_keyboard(int(lesson_record["id"]), revision),
                )
                return
            message = (
                "This lesson already has an outcome; no reminder was created."
                if reminder_result["status"] == "completed"
                else "Reminder limit reached. Open the class when you are ready; no more prompts will be sent."
            )
            await _safe_edit(
                query, f"ℹ {message}",
                outcome_result_keyboard(int(lesson_record["id"]), revision),
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
            if action == "taught" and updated_lesson.get("lifecycle_state") == "taught":
                await _safe_edit(
                    query,
                    _outcome_result_text(updated_lesson, notice=notice),
                    outcome_result_keyboard(int(updated_lesson["id"]), revision),
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
        if action == "plan" and feature_enabled("continuity"):
            touch_class_activity(telegram_user_id=user.id, class_id=class_id)
            rec = get_or_create_recommendation(telegram_user_id=user.id, class_id=class_id)
            if rec is None:
                await _recover(query, context)
                return
            await _safe_edit(
                query,
                _next_lesson_rec_text(str(class_record["display_name"]), rec),
                next_lesson_recommendation_keyboard(rec, class_id, revision),
            )
            return
        if action == "nlrec":
            if rec_record is None:
                await _recover(query, context)
                return
            await _safe_edit(
                query,
                _next_lesson_rec_text(str(class_record["display_name"]), rec_record),
                next_lesson_recommendation_keyboard(rec_record, class_id, revision),
            )
            return
        if action == "nlwhy":
            if rec_record is None:
                await _recover(query, context)
                return
            await _safe_edit(
                query,
                _next_lesson_why_text(str(class_record["display_name"]), rec_record),
                next_lesson_why_keyboard(int(rec_record["id"]), revision),
            )
            return
        if action == "nlmode":
            if rec_record is None:
                await _recover(query, context)
                return
            await _safe_edit(
                query,
                _next_lesson_modes_text(str(class_record["display_name"]), rec_record),
                next_lesson_modes_keyboard(
                    int(rec_record["id"]), rec_record.get("selected_mode"), revision
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
                await _recover(query, context)
                return
            await _safe_edit(
                query,
                _next_lesson_rec_text(
                    str(class_record["display_name"]),
                    updated_rec,
                    notice=f"✅ Mode set to {MODE_LABELS.get(mode_str, mode_str)}.",
                ),
                next_lesson_recommendation_keyboard(updated_rec, class_id, revision),
            )
            return
        if action == "nlprio":
            if rec_record is None:
                await _recover(query, context)
                return
            await _safe_edit(
                query,
                _next_lesson_priorities_text(str(class_record["display_name"]), rec_record),
                next_lesson_priorities_keyboard(
                    int(rec_record["id"]),
                    str(rec_record.get("priority_mode", "balanced")),
                    revision,
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
                await _recover(query, context)
                return
            await _safe_edit(
                query,
                _next_lesson_rec_text(
                    str(class_record["display_name"]),
                    updated_rec,
                    notice=f"✅ Priority set to {prio_str.title()}.",
                ),
                next_lesson_recommendation_keyboard(updated_rec, class_id, revision),
            )
            return
        if action == "nlsrc":
            if rec_record is None:
                await _recover(query, context)
                return
            await _safe_edit(
                query,
                _next_lesson_sources_text(str(class_record["display_name"]), rec_record),
                next_lesson_sources_keyboard(
                    int(rec_record["id"]), rec_record.get("sources", []), revision
                ),
            )
            return
        if action == "nltog":
            if rec_record is None:
                await _recover(query, context)
                return
            await _safe_edit(
                query,
                _next_lesson_sources_text(str(class_record["display_name"]), rec_record),
                next_lesson_sources_keyboard(
                    int(rec_record["id"]), rec_record.get("sources", []), revision
                ),
            )
            return
        if action == "nlign":
            if rec_record is None:
                await _recover(query, context)
                return
            ignore_recommendation(telegram_user_id=user.id, recommendation_id=int(rec_record["id"]))
            await _render_dashboard(
                query, context, telegram_user_id=user.id, class_id=class_id, expected_revision=revision
            )
            return
        if action == "nlman":
            if rec_record is None:
                await _recover(query, context)
                return
            context.user_data["next_lesson_topic"] = {
                "rec_id": int(rec_record["id"]),
                "class_id": class_id,
                "revision": revision,
                "state": "text",
            }
            await _safe_edit(
                query,
                f"✏ Choose Manually · {class_record['display_name']}\n\n"
                "Type your custom lesson topic (2 to 300 characters).\n\n"
                "Do not include student names, email addresses, phone numbers, or sensitive data.",
                next_lesson_why_keyboard(int(rec_record["id"]), revision),
            )
            return
        if action == "nlgen":
            if rec_record is None:
                await _recover(query, context)
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
                await _safe_edit(
                    query,
                    f"✏ Choose Manually · {class_record['display_name']}\n\n"
                    "Type your custom lesson topic before generating.",
                    next_lesson_why_keyboard(int(rec_record["id"]), revision),
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
                await _recover(query, context)
                return

            await _safe_edit(
                query,
                "🧠 Generating your next lesson plan...\n\n"
                "TeacherOS is synthesizing approved class history into a classroom-ready lesson.",
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
                await _safe_edit(
                    query,
                    "❌ I could not generate the next lesson right now.\n\n"
                    "Your choices are saved. Check your connection, then tap Generate to retry.",
                    next_lesson_recommendation_keyboard(refreshed or rec_record, class_id, revision),
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

            summary_lines = [
                f"✅ Next lesson plan generated & saved · {class_record['display_name']}",
                f"Mode: {MODE_LABELS.get(effective_mode, effective_mode)} · Level: {level} · {duration} mins",
                "",
                "Did this lesson address the intended target?",
            ]
            await _safe_edit(
                query,
                "\n".join(summary_lines),
                next_lesson_followup_keyboard(plan_id, class_id, revision)
                if plan_id
                else class_details_keyboard(class_id, revision, archived=False),
            )
            if query.message is not None:
                for start in range(0, len(result_text), 4000):
                    await query.message.reply_text(result_text[start : start + 4000])
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
                await update.message.reply_text(
                    "⚠️ This class changed. Topic was not saved. Refresh the class.",
                    reply_markup=class_recovery_keyboard(),
                )
                return
            rec = set_manual_next_lesson_request(
                telegram_user_id=update.effective_user.id,
                recommendation_id=rec_id,
                request=update.message.text or "",
            )
            if rec is None:
                context.user_data.pop("next_lesson_topic", None)
                await update.message.reply_text(
                    "⚠️ The recommendation draft is no longer available.",
                    reply_markup=class_recovery_keyboard(),
                )
                return
            context.user_data.pop("next_lesson_topic", None)
            await update.message.reply_text(
                _next_lesson_rec_text(
                    str(snapshot["class"]["display_name"]), rec,
                    notice="✅ Custom manual topic saved.",
                ),
                reply_markup=next_lesson_recommendation_keyboard(rec, class_id, revision),
            )
        except ValueError as exc:
            await update.message.reply_text(
                f"⚠️ {exc}\n\nType a short, non-sensitive topic (2 to 300 characters), or return to the plan.",
                reply_markup=next_lesson_why_keyboard(rec_id, revision),
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
                await update.message.reply_text(
                    "⚠️ This class changed. The note was not saved. Refresh the class.",
                    reply_markup=class_recovery_keyboard(),
                )
                return
            outcome, _ = update_outcome_note(
                telegram_user_id=update.effective_user.id,
                lesson_id=lesson_id,
                note=update.message.text or "",
            )
            if outcome is None:
                context.user_data.pop("outcome_note", None)
                await update.message.reply_text(
                    "⚠️ The taught lesson or saved outcome is no longer available. No note was saved.",
                    reply_markup=class_recovery_keyboard(),
                )
                return
            context.user_data.pop("outcome_note", None)
            metrics = outcome_recording_metrics(
                telegram_user_id=update.effective_user.id, class_id=class_id
            )
            await update.message.reply_text(
                _outcome_summary_text(outcome, metrics, notice="Optional note saved."),
                reply_markup=outcome_summary_keyboard(
                    lesson_id, class_id, revision, has_note=bool(outcome.get("notes"))
                ),
            )
        except ValueError as exc:
            outcome = get_lesson_outcome(
                telegram_user_id=update.effective_user.id, lesson_id=lesson_id
            )
            await update.message.reply_text(
                f"⚠️ {exc}\n\nUse a short, non-sensitive teaching note, or skip it.",
                reply_markup=outcome_note_keyboard(
                    lesson_id, class_id, revision,
                    has_note=bool(outcome and outcome.get("notes")),
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
