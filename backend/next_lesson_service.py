from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from database import database_connection


VALID_MODES = {
    "recommendation", "continue_unfinished", "reteach",
    "new_topic", "assessment", "manual",
}
VALID_PRIORITIES = {"balanced", "continuity", "reteaching", "assessment"}
MODE_LABELS = {
    "recommendation": "Use recommendation",
    "continue_unfinished": "Continue unfinished work",
    "reteach": "Reteach",
    "new_topic": "Start a new topic",
    "assessment": "Prepare for assessment",
    "manual": "Choose manually",
}
SOURCE_CONTEXT_KEYS = {
    "class_objective": "class_objectives",
    "class_lesson": "class_lessons",
    "lesson_outcome": "lesson_outcomes",
    "class_action_item": "class_action_items",
    "material": "materials",
}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s().-]*){8,}(?!\d)")
_TIME_LINE = re.compile(r"(?im)^\s*(?:[-*]\s*)?time\s*:\s*(\d{1,3})\s*(?:minutes?|mins?)\b")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _json_list(value: object) -> list[Any]:
    try:
        decoded = json.loads(str(value or "[]"))
    except (json.JSONDecodeError, TypeError):
        return []
    return decoded if isinstance(decoded, list) else []


def _short(value: object, maximum: int = 160) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= maximum else text[: maximum - 1].rstrip() + "…"


def _owned_class(connection: Any, telegram_user_id: int, class_id: int) -> Any:
    return connection.execute(
        """
        SELECT c.* FROM classes AS c
        JOIN users AS u ON u.id = c.user_id
        WHERE c.id = ? AND u.telegram_user_id = ? AND c.status = 'active'
        """,
        (class_id, telegram_user_id),
    ).fetchone()


def _event(
    connection: Any,
    *,
    user_id: int,
    class_id: int,
    name: str,
    event_key: str,
    properties: Mapping[str, object] | None = None,
    material_id: int | None = None,
) -> None:
    safe_properties = dict(properties or {})
    connection.execute(
        """
        INSERT OR IGNORE INTO product_events (
            event_uuid, user_id, class_id, material_id, event_name,
            privacy_class, properties_json, occurred_at
        ) VALUES (?, ?, ?, ?, ?, 'product', ?, ?)
        """,
        (
            f"next-lesson:{event_key}", user_id, class_id, material_id, name,
            json.dumps(safe_properties, ensure_ascii=False, sort_keys=True), _utc_now(),
        ),
    )


def _objective_snapshot(connection: Any, user_id: int, class_id: int) -> tuple[list[int], list[str]]:
    rows = connection.execute(
        """
        SELECT id, objective FROM class_objectives
        WHERE user_id = ? AND class_id = ? AND status = 'current'
        ORDER BY priority DESC, updated_at DESC, id DESC LIMIT 3
        """,
        (user_id, class_id),
    ).fetchall()
    return (
        [int(row["id"]) for row in rows],
        [f"O{index}: Can do {_short(row['objective'], 220)}" for index, row in enumerate(rows, 1)],
    )


def _fallback_objective(mode: str, topic: str | None = None) -> str:
    if mode == "reteach":
        body = "use the previously difficult language more accurately with guided support"
    elif mode == "continue_unfinished":
        body = "complete and demonstrate the unfinished lesson objective"
    elif mode == "assessment":
        body = "demonstrate current learning through a short observable assessment task"
    elif mode == "manual" and topic:
        body = f"use language for {_short(topic, 120)} in a supported communicative task"
    else:
        body = "use target language for the next appropriate topic in a supported exchange"
    return "O1: Can do " + body


def _history_signal(connection: Any, user_id: int, class_id: int) -> dict[str, Any]:
    outcomes = connection.execute(
        """
        SELECT o.id, o.result, o.completion_status, o.class_lesson_id,
               l.title, o.updated_at
        FROM lesson_outcomes AS o
        JOIN class_lessons AS l ON l.id = o.class_lesson_id
        WHERE o.user_id = ? AND o.class_id = ? AND o.status = 'approved'
        ORDER BY o.updated_at DESC, o.id DESC LIMIT 5
        """,
        (user_id, class_id),
    ).fetchall()
    lesson_count = int(connection.execute(
        "SELECT COUNT(*) FROM class_lessons WHERE user_id = ? AND class_id = ?",
        (user_id, class_id),
    ).fetchone()[0])
    latest = outcomes[0] if outcomes else None
    return {"outcomes": outcomes, "latest": latest, "lesson_count": lesson_count}


def _balanced_recommendation(class_row: Any, signal: Mapping[str, Any]) -> tuple[str, str]:
    latest = signal.get("latest")
    if latest is not None:
        completion = str(latest["completion_status"] or "")
        result = str(latest["result"])
        if completion in {"partly_completed", "not_completed"}:
            return (
                "continue_unfinished",
                f"The recorded completion for lesson #{int(latest['class_lesson_id'])} was "
                f"{completion.replace('_', ' ')}. Continue it before adding more load.",
            )
        if result == "not_met":
            return (
                "reteach",
                f"Outcome #{int(latest['id'])} records needs reteaching. Propose a different "
                "route with support; this is a response to one record, not a mastery judgment.",
            )
        if result == "partly_met":
            return (
                "continue_unfinished",
                f"Outcome #{int(latest['id'])} records partly achieved. Consolidate the same "
                "objective with retrieval and a fresh communicative check.",
            )
    goal = str(class_row["goal"] or "").casefold()
    if "exam" in goal or "assessment" in goal:
        return (
            "assessment",
            "The teacher-saved class goal is assessment-focused. Prepare an aligned check "
            "without inferring mastery from prior outcomes.",
        )
    if latest is not None and str(latest["result"]) in {"met", "exceeded"}:
        return (
            "new_topic",
            f"Outcome #{int(latest['id'])} records achieved. Offer a next step with retrieval; "
            "one outcome does not establish mastery.",
        )
    return (
        "new_topic",
        "There is not enough approved outcome history to continue or reteach confidently. "
        "Start a modest next topic and keep the first check diagnostic.",
    )


def _priority_recommendation(
    priority: str, class_row: Any, signal: Mapping[str, Any]
) -> tuple[str, str]:
    if priority == "continuity":
        return "continue_unfinished", "Teacher priority is continuity: reuse recent work before expanding scope."
    if priority == "reteaching":
        return "reteach", "Teacher priority is reteaching: revisit the latest approved objective with a different route."
    if priority == "assessment":
        return "assessment", "Teacher priority is assessment: gather observable evidence against approved objectives."
    return _balanced_recommendation(class_row, signal)


def _uncertainty(signal: Mapping[str, Any], included_outcomes: int | None = None) -> tuple[str, str]:
    count = len(signal.get("outcomes") or []) if included_outcomes is None else included_outcomes
    if count == 0:
        return "high", "No included approved outcome records; the proposal relies on profile and objectives."
    if count == 1:
        return "medium", "Only one included approved outcome; it informs the proposal but cannot prove mastery."
    return "low", "Two or more approved outcomes are available, while teacher review remains required."


def _insert_sources(connection: Any, recommendation_id: int, user_id: int, class_id: int) -> None:
    rows: list[tuple[str, int, str, str, int]] = []
    objectives = connection.execute(
        """SELECT id, objective, priority FROM class_objectives
           WHERE user_id = ? AND class_id = ? AND status = 'current'
           ORDER BY priority DESC, updated_at DESC, id DESC LIMIT 6""",
        (user_id, class_id),
    ).fetchall()
    for row in objectives:
        rows.append((
            "class_objective", int(row["id"]),
            f"Objective #{int(row['id'])} · {_short(row['objective'])}",
            f"Teacher-saved current objective; priority {int(row['priority'])}.",
            900 + int(row["priority"]),
        ))
    lessons = connection.execute(
        """SELECT id, title, lifecycle_state, scheduled_for, taught_at
           FROM class_lessons WHERE user_id = ? AND class_id = ? AND status != 'archived'
           ORDER BY COALESCE(taught_at, scheduled_for, updated_at) DESC, id DESC LIMIT 5""",
        (user_id, class_id),
    ).fetchall()
    for index, row in enumerate(lessons):
        rows.append((
            "class_lesson", int(row["id"]),
            f"Lesson #{int(row['id'])} · {_short(row['title'])}",
            f"Recorded lesson state: {str(row['lifecycle_state']).replace('_', ' ')}.",
            800 - index,
        ))
    outcomes = connection.execute(
        """SELECT id, class_lesson_id, result, completion_status,
                  difficulty_categories_json, facts_version
           FROM lesson_outcomes WHERE user_id = ? AND class_id = ? AND status = 'approved'
           ORDER BY updated_at DESC, id DESC LIMIT 5""",
        (user_id, class_id),
    ).fetchall()
    for index, row in enumerate(outcomes):
        difficulties = ", ".join(str(x).replace("_", " ") for x in _json_list(row["difficulty_categories_json"])) or "none recorded"
        rows.append((
            "lesson_outcome", int(row["id"]),
            f"Outcome #{int(row['id'])} · lesson #{int(row['class_lesson_id'])}",
            "Recorded facts: result " + str(row["result"]).replace("_", " ")
            + "; completion " + str(row["completion_status"] or "not recorded").replace("_", " ")
            + f"; difficulties {difficulties}; facts version {int(row['facts_version'])}.",
            1000 - index,
        ))
    actions = connection.execute(
        """SELECT id, item_type, source_key, due_at FROM class_action_items
           WHERE user_id = ? AND class_id = ? AND status = 'pending'
           ORDER BY COALESCE(due_at, created_at), id LIMIT 4""",
        (user_id, class_id),
    ).fetchall()
    for index, row in enumerate(actions):
        rows.append((
            "class_action_item", int(row["id"]),
            f"Action #{int(row['id'])} · {str(row['item_type']).replace('_', ' ')}",
            f"Recorded pending action; due {row['due_at'] or 'not set'}.",
            700 - index,
        ))
    materials = connection.execute(
        """SELECT id, material_type, subtype FROM materials
           WHERE user_id = ? AND class_id = ? ORDER BY created_at DESC, id DESC LIMIT 3""",
        (user_id, class_id),
    ).fetchall()
    for index, row in enumerate(materials):
        rows.append((
            "material", int(row["id"]),
            f"Material #{int(row['id'])} · {str(row['material_type']).replace('_', ' ')}",
            f"Recorded recent resource format: {_short(row['subtype'] or row['material_type'], 100)}.",
            600 - index,
        ))
    connection.executemany(
        """
        INSERT INTO next_lesson_recommendation_sources (
            recommendation_id, class_id, user_id, source_type, source_record_id,
            source_label, fact_summary, sort_priority
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (recommendation_id, class_id, user_id, source_type, source_id, label, summary, priority)
            for source_type, source_id, label, summary, priority in rows
        ],
    )


def _decode_recommendation(row: Any, sources: list[Any]) -> dict[str, Any]:
    result = dict(row)
    result["objective_labels"] = [str(x) for x in _json_list(row["objective_labels_json"])]
    result["approved_objective_ids"] = [int(x) for x in _json_list(row["approved_objective_ids_json"])]
    result["sources"] = [dict(source) for source in sources]
    result["effective_mode"] = (
        str(row["recommended_mode"])
        if row["selected_mode"] == "recommendation"
        else row["selected_mode"]
    )
    return result


def _load_recommendation(connection: Any, user_id: int, recommendation_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM next_lesson_recommendations WHERE id = ? AND user_id = ?",
        (recommendation_id, user_id),
    ).fetchone()
    if row is None:
        return None
    sources = connection.execute(
        """SELECT * FROM next_lesson_recommendation_sources
           WHERE recommendation_id = ? ORDER BY included DESC, sort_priority DESC, id""",
        (recommendation_id,),
    ).fetchall()
    return _decode_recommendation(row, list(sources))


def get_or_create_recommendation(
    *, telegram_user_id: int, class_id: int, force_refresh: bool = False,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Return the durable active draft, or build one from approved owner-scoped records."""
    with database_connection(database_path) as connection:
        class_row = _owned_class(connection, telegram_user_id, class_id)
        if class_row is None:
            return None
        user_id = int(class_row["user_id"])
        if not force_refresh:
            existing = connection.execute(
                """SELECT id, status FROM next_lesson_recommendations
                   WHERE user_id = ? AND class_id = ? AND status IN ('ready', 'generating')
                   ORDER BY id DESC LIMIT 1""",
                (user_id, class_id),
            ).fetchone()
            if existing is not None:
                if existing["status"] == "generating":
                    connection.execute(
                        """UPDATE next_lesson_recommendations
                           SET status = 'ready', last_error_code = 'interrupted_generation',
                               updated_at = ?, input_version = input_version + 1
                           WHERE id = ?""",
                        (_utc_now(), int(existing["id"])),
                    )
                return _load_recommendation(connection, user_id, int(existing["id"]))
        else:
            connection.execute(
                """UPDATE next_lesson_recommendations
                   SET status = 'ignored', updated_at = ?
                   WHERE user_id = ? AND class_id = ? AND status IN ('ready', 'generating')""",
                (_utc_now(), user_id, class_id),
            )

        signal = _history_signal(connection, user_id, class_id)
        mode, rationale = _balanced_recommendation(class_row, signal)
        uncertainty, uncertainty_reason = _uncertainty(signal)
        objective_ids, objectives = _objective_snapshot(connection, user_id, class_id)
        if not objectives:
            objectives = [_fallback_objective(mode)]
        duration = class_row["lesson_duration_minutes"]
        if not isinstance(duration, int):
            duration = 60
        cursor = connection.execute(
            """
            INSERT INTO next_lesson_recommendations (
                draft_uuid, class_id, user_id, recommended_mode, rationale,
                uncertainty, uncertainty_reason, duration_minutes,
                objective_labels_json, approved_objective_ids_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), class_id, user_id, mode, rationale,
                uncertainty, uncertainty_reason, duration,
                json.dumps(objectives, ensure_ascii=False), json.dumps(objective_ids),
            ),
        )
        recommendation_id = int(cursor.lastrowid)
        _insert_sources(connection, recommendation_id, user_id, class_id)
        return _load_recommendation(connection, user_id, recommendation_id)


def get_recommendation(
    *, telegram_user_id: int, recommendation_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (telegram_user_id,)
        ).fetchone()
        return None if user is None else _load_recommendation(connection, int(user["id"]), recommendation_id)


def select_recommendation_mode(
    *, telegram_user_id: int, recommendation_id: int, mode: str,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    if mode not in VALID_MODES:
        raise ValueError("Unsupported next-lesson mode.")
    with database_connection(database_path) as connection:
        user = connection.execute("SELECT id FROM users WHERE telegram_user_id = ?", (telegram_user_id,)).fetchone()
        if user is None:
            return None
        user_id = int(user["id"])
        current = _load_recommendation(connection, user_id, recommendation_id)
        if current is None or current["status"] != "ready":
            return None
        effective = str(current["recommended_mode"]) if mode == "recommendation" else mode
        topic = str(current.get("teacher_request") or "") if effective == "manual" else None
        objective_ids, objectives = _objective_snapshot(connection, user_id, int(current["class_id"]))
        if not objectives:
            objectives = [_fallback_objective(effective, topic)]
        version = int(current["input_version"]) + 1
        connection.execute(
            """UPDATE next_lesson_recommendations
               SET selected_mode = ?, objective_labels_json = ?,
                   approved_objective_ids_json = ?, objectives_approved_at = NULL,
                   input_version = ?, last_error_code = NULL, updated_at = ?
               WHERE id = ? AND user_id = ? AND status = 'ready'""",
            (
                mode, json.dumps(objectives, ensure_ascii=False), json.dumps(objective_ids),
                version, _utc_now(), recommendation_id, user_id,
            ),
        )
        _event(
            connection, user_id=user_id, class_id=int(current["class_id"]),
            name="next_lesson_recommendation_selected",
            event_key=f"selected:{recommendation_id}:{version}",
            properties={"selected_mode": mode, "effective_mode": effective},
        )
        return _load_recommendation(connection, user_id, recommendation_id)


def set_recommendation_priority(
    *, telegram_user_id: int, recommendation_id: int, priority: str,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    if priority not in VALID_PRIORITIES:
        raise ValueError("Unsupported recommendation priority.")
    with database_connection(database_path) as connection:
        user = connection.execute("SELECT id FROM users WHERE telegram_user_id = ?", (telegram_user_id,)).fetchone()
        if user is None:
            return None
        user_id = int(user["id"])
        current = _load_recommendation(connection, user_id, recommendation_id)
        if current is None or current["status"] != "ready":
            return None
        class_row = connection.execute("SELECT * FROM classes WHERE id = ? AND user_id = ?", (current["class_id"], user_id)).fetchone()
        signal = _history_signal(connection, user_id, int(current["class_id"]))
        mode, rationale = _priority_recommendation(priority, class_row, signal)
        version = int(current["input_version"]) + 1
        connection.execute(
            """UPDATE next_lesson_recommendations
               SET priority_mode = ?, recommended_mode = ?, selected_mode = NULL,
                   rationale = ?, objectives_approved_at = NULL, input_version = ?,
                   last_error_code = NULL, updated_at = ? WHERE id = ? AND user_id = ?""",
            (priority, mode, rationale, version, _utc_now(), recommendation_id, user_id),
        )
        _event(
            connection, user_id=user_id, class_id=int(current["class_id"]),
            name="next_lesson_priority_changed",
            event_key=f"priority:{recommendation_id}:{version}",
            properties={"priority": priority, "recommended_mode": mode},
        )
        return _load_recommendation(connection, user_id, recommendation_id)


def toggle_recommendation_source(
    *, telegram_user_id: int, source_link_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    with database_connection(database_path) as connection:
        row = connection.execute(
            """SELECT s.*, r.status, r.input_version FROM next_lesson_recommendation_sources AS s
               JOIN next_lesson_recommendations AS r ON r.id = s.recommendation_id
               JOIN users AS u ON u.id = s.user_id
               WHERE s.id = ? AND u.telegram_user_id = ?""",
            (source_link_id, telegram_user_id),
        ).fetchone()
        if row is None or row["status"] != "ready":
            return None
        included = 0 if int(row["included"]) else 1
        version = int(row["input_version"]) + 1
        connection.execute(
            "UPDATE next_lesson_recommendation_sources SET included = ?, updated_at = ? WHERE id = ?",
            (included, _utc_now(), source_link_id),
        )
        included_outcomes = int(connection.execute(
            """SELECT COUNT(*) FROM next_lesson_recommendation_sources
               WHERE recommendation_id = ? AND source_type = 'lesson_outcome' AND included = 1""",
            (int(row["recommendation_id"]),),
        ).fetchone()[0])
        uncertainty, reason = _uncertainty({}, included_outcomes)
        connection.execute(
            """UPDATE next_lesson_recommendations
               SET uncertainty = ?, uncertainty_reason = ?, objectives_approved_at = NULL,
                   input_version = ?, updated_at = ? WHERE id = ?""",
            (uncertainty, reason, version, _utc_now(), int(row["recommendation_id"])),
        )
        _event(
            connection, user_id=int(row["user_id"]), class_id=int(row["class_id"]),
            name="next_lesson_source_changed",
            event_key=f"source:{int(row['recommendation_id'])}:{version}",
            properties={"source_type": str(row["source_type"]), "included": bool(included)},
        )
        return _load_recommendation(connection, int(row["user_id"]), int(row["recommendation_id"]))


def set_manual_next_lesson_request(
    *, telegram_user_id: int, recommendation_id: int, request: str,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    normalized = " ".join(str(request or "").split())
    if len(normalized) < 2 or len(normalized) > 300:
        raise ValueError("Manual topic must be between 2 and 300 characters.")
    if _CONTROL.search(normalized) or _EMAIL.search(normalized) or _PHONE.search(normalized):
        raise ValueError("Remove contact details or control characters from the topic.")
    with database_connection(database_path) as connection:
        user = connection.execute("SELECT id FROM users WHERE telegram_user_id = ?", (telegram_user_id,)).fetchone()
        if user is None:
            return None
        user_id = int(user["id"])
        current = _load_recommendation(connection, user_id, recommendation_id)
        if current is None or current["status"] != "ready":
            return None
        objective_ids, objectives = _objective_snapshot(connection, user_id, int(current["class_id"]))
        if not objectives:
            objectives = [_fallback_objective("manual", normalized)]
        version = int(current["input_version"]) + 1
        connection.execute(
            """UPDATE next_lesson_recommendations
               SET selected_mode = 'manual', teacher_request = ?, objective_labels_json = ?,
                   approved_objective_ids_json = ?, objectives_approved_at = NULL,
                   input_version = ?, last_error_code = NULL, updated_at = ?
               WHERE id = ? AND user_id = ? AND status = 'ready'""",
            (
                normalized, json.dumps(objectives, ensure_ascii=False), json.dumps(objective_ids),
                version, _utc_now(), recommendation_id, user_id,
            ),
        )
        _event(
            connection, user_id=user_id, class_id=int(current["class_id"]),
            name="next_lesson_recommendation_selected",
            event_key=f"selected:{recommendation_id}:{version}",
            properties={"selected_mode": "manual", "effective_mode": "manual"},
        )
        return _load_recommendation(connection, user_id, recommendation_id)


def ignore_recommendation(
    *, telegram_user_id: int, recommendation_id: int,
    database_path: Path | None = None,
) -> bool:
    with database_connection(database_path) as connection:
        row = connection.execute(
            """SELECT r.*, u.telegram_user_id FROM next_lesson_recommendations AS r
               JOIN users AS u ON u.id = r.user_id WHERE r.id = ?""",
            (recommendation_id,),
        ).fetchone()
        if row is None or int(row["telegram_user_id"]) != telegram_user_id or row["status"] != "ready":
            return False
        connection.execute(
            "UPDATE next_lesson_recommendations SET status = 'ignored', updated_at = ? WHERE id = ?",
            (_utc_now(), recommendation_id),
        )
        _event(
            connection, user_id=int(row["user_id"]), class_id=int(row["class_id"]),
            name="next_lesson_suggestion_ignored", event_key=f"ignored:{recommendation_id}",
            properties={"recommended_mode": str(row["recommended_mode"])},
        )
        return True


def generation_source_filter(recommendation: Mapping[str, Any]) -> dict[str, list[int]]:
    grouped = {key: [] for key in SOURCE_CONTEXT_KEYS.values()}
    for source in recommendation.get("sources", []):
        if int(source.get("included", 0)) != 1:
            continue
        key = SOURCE_CONTEXT_KEYS[str(source["source_type"])]
        grouped[key].append(int(source["source_record_id"]))
    return grouped


def claim_recommendation_generation(
    *, telegram_user_id: int, recommendation_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    with database_connection(database_path) as connection:
        user = connection.execute("SELECT id FROM users WHERE telegram_user_id = ?", (telegram_user_id,)).fetchone()
        if user is None:
            return None
        user_id = int(user["id"])
        current = _load_recommendation(connection, user_id, recommendation_id)
        if current is None or current["status"] != "ready" or current.get("selected_mode") is None:
            return None
        if current["selected_mode"] == "manual" and not str(current.get("teacher_request") or "").strip():
            return None
        now = _utc_now()
        cursor = connection.execute(
            """UPDATE next_lesson_recommendations
               SET status = 'generating', objectives_approved_at = ?, last_error_code = NULL,
                   updated_at = ? WHERE id = ? AND user_id = ? AND status = 'ready'""",
            (now, now, recommendation_id, user_id),
        )
        if cursor.rowcount != 1:
            return None
        _event(
            connection, user_id=user_id, class_id=int(current["class_id"]),
            name="next_lesson_generation_started",
            event_key=f"started:{recommendation_id}:{int(current['input_version'])}",
            properties={"selected_mode": str(current["selected_mode"])},
        )
        return _load_recommendation(connection, user_id, recommendation_id)


def release_recommendation_generation(
    *, telegram_user_id: int, recommendation_id: int, error_code: str,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    safe_code = re.sub(r"[^a-z0-9_.-]", "_", str(error_code).lower())[:100] or "generation_failed"
    with database_connection(database_path) as connection:
        row = connection.execute(
            """SELECT r.*, u.telegram_user_id FROM next_lesson_recommendations AS r
               JOIN users AS u ON u.id = r.user_id WHERE r.id = ?""",
            (recommendation_id,),
        ).fetchone()
        if row is None or int(row["telegram_user_id"]) != telegram_user_id or row["status"] != "generating":
            return None
        connection.execute(
            """UPDATE next_lesson_recommendations SET status = 'ready', last_error_code = ?,
               updated_at = ? WHERE id = ?""",
            (safe_code, _utc_now(), recommendation_id),
        )
        _event(
            connection, user_id=int(row["user_id"]), class_id=int(row["class_id"]),
            name="next_lesson_generation_retry_ready",
            event_key=f"retry:{recommendation_id}:{int(row['input_version'])}:{safe_code}",
            properties={"error_code": safe_code},
        )
        return _load_recommendation(connection, int(row["user_id"]), recommendation_id)


def plan_timing_total(content: str) -> int:
    return sum(int(value) for value in _TIME_LINE.findall(str(content)))


def complete_next_lesson_plan(
    *, telegram_user_id: int, recommendation_id: int, material_id: int,
    validation: Mapping[str, object], database_path: Path | None = None,
) -> dict[str, Any] | None:
    with database_connection(database_path) as connection:
        row = connection.execute(
            """SELECT r.*, u.telegram_user_id, m.content FROM next_lesson_recommendations AS r
               JOIN users AS u ON u.id = r.user_id
               JOIN materials AS m ON m.id = ? AND m.user_id = r.user_id AND m.class_id = r.class_id
               WHERE r.id = ?""",
            (material_id, recommendation_id),
        ).fetchone()
        if row is None or int(row["telegram_user_id"]) != telegram_user_id:
            return None
        existing = connection.execute(
            "SELECT * FROM next_lesson_plans WHERE recommendation_id = ?",
            (recommendation_id,),
        ).fetchone()
        if existing is not None:
            return dict(existing)
        if row["status"] != "generating" or row["selected_mode"] is None or row["objectives_approved_at"] is None:
            return None
        total = plan_timing_total(str(row["content"]))
        duration = int(row["duration_minutes"])
        cursor = connection.execute(
            """
            INSERT INTO next_lesson_plans (
                recommendation_id, class_id, user_id, material_id, selected_mode,
                duration_minutes, timing_total_minutes, objective_labels_json, validation_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recommendation_id, int(row["class_id"]), int(row["user_id"]), material_id,
                str(row["selected_mode"]), duration, total, str(row["objective_labels_json"]),
                json.dumps(dict(validation), ensure_ascii=False, sort_keys=True),
            ),
        )
        plan_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO next_lesson_plan_sources (
                next_lesson_plan_id, recommendation_source_id, class_id, user_id,
                source_type, source_record_id, source_label
            )
            SELECT ?, id, class_id, user_id, source_type, source_record_id, source_label
            FROM next_lesson_recommendation_sources
            WHERE recommendation_id = ? AND included = 1
            """,
            (plan_id, recommendation_id),
        )
        connection.execute(
            """UPDATE next_lesson_recommendations SET status = 'saved', material_id = ?,
               last_error_code = NULL, updated_at = ? WHERE id = ?""",
            (material_id, _utc_now(), recommendation_id),
        )
        _event(
            connection, user_id=int(row["user_id"]), class_id=int(row["class_id"]),
            material_id=material_id, name="next_lesson_plan_saved",
            event_key=f"saved:{recommendation_id}",
            properties={
                "selected_mode": str(row["selected_mode"]),
                "source_count": int(connection.execute(
                    "SELECT COUNT(*) FROM next_lesson_plan_sources WHERE next_lesson_plan_id = ?",
                    (plan_id,),
                ).fetchone()[0]),
                "timing_valid": total == duration,
            },
        )
        return dict(connection.execute("SELECT * FROM next_lesson_plans WHERE id = ?", (plan_id,)).fetchone())


def record_next_lesson_edit(
    *, telegram_user_id: int, plan_id: int, database_path: Path | None = None,
) -> bool:
    with database_connection(database_path) as connection:
        row = connection.execute(
            """SELECT p.*, u.telegram_user_id FROM next_lesson_plans AS p
               JOIN users AS u ON u.id = p.user_id WHERE p.id = ?""",
            (plan_id,),
        ).fetchone()
        if row is None or int(row["telegram_user_id"]) != telegram_user_id:
            return False
        count = int(row["teacher_edit_count"]) + 1
        connection.execute(
            "UPDATE next_lesson_plans SET teacher_edit_count = ?, updated_at = ? WHERE id = ?",
            (count, _utc_now(), plan_id),
        )
        _event(
            connection, user_id=int(row["user_id"]), class_id=int(row["class_id"]),
            material_id=int(row["material_id"]), name="next_lesson_teacher_edit",
            event_key=f"edit:{plan_id}:{count}", properties={"edit_count": count},
        )
        return True


def record_next_lesson_followup(
    *, telegram_user_id: int, plan_id: int, accepted: bool,
    database_path: Path | None = None,
) -> bool:
    with database_connection(database_path) as connection:
        row = connection.execute(
            """SELECT p.*, u.telegram_user_id FROM next_lesson_plans AS p
               JOIN users AS u ON u.id = p.user_id WHERE p.id = ?""",
            (plan_id,),
        ).fetchone()
        if row is None or int(row["telegram_user_id"]) != telegram_user_id:
            return False
        connection.execute(
            "UPDATE next_lesson_plans SET followup_accepted = ?, updated_at = ? WHERE id = ?",
            (1 if accepted else 0, _utc_now(), plan_id),
        )
        _event(
            connection, user_id=int(row["user_id"]), class_id=int(row["class_id"]),
            material_id=int(row["material_id"]), name="next_lesson_followup_acceptance",
            event_key=f"followup:{plan_id}:{1 if accepted else 0}",
            properties={"accepted": accepted},
        )
        return True


def next_lesson_metrics(*, database_path: Path | None = None) -> dict[str, Any]:
    with database_connection(database_path) as connection:
        selected = int(connection.execute(
            "SELECT COUNT(*) FROM product_events WHERE event_name = 'next_lesson_recommendation_selected'"
        ).fetchone()[0])
        saved = int(connection.execute("SELECT COUNT(*) FROM next_lesson_plans").fetchone()[0])
        edits = int(connection.execute("SELECT COALESCE(SUM(teacher_edit_count), 0) FROM next_lesson_plans").fetchone()[0])
        accepted = int(connection.execute("SELECT COUNT(*) FROM next_lesson_plans WHERE followup_accepted = 1").fetchone()[0])
        answered = int(connection.execute("SELECT COUNT(*) FROM next_lesson_plans WHERE followup_accepted IS NOT NULL").fetchone()[0])
    return {
        "recommendations_selected": selected,
        "plans_saved": saved,
        "teacher_edits": edits,
        "followup_answers": answered,
        "followup_accepted": accepted,
        "followup_acceptance_percent": None if answered == 0 else round(accepted * 100 / answered),
        "quality_definition": "use_not_generation_count",
    }


def source_snapshot_hash(recommendation: Mapping[str, Any]) -> str:
    payload = [
        [str(source["source_type"]), int(source["source_record_id"]), int(source["included"])]
        for source in recommendation.get("sources", [])
    ]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
