from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from database import database_connection
from feature_flags import feature_enabled


logger = logging.getLogger(__name__)

PROMPT_CONTRACT = "teacheros.analysis_followup"
PROMPT_VERSION = "2026-08-31.1"

VALID_ACTION_TYPES = {
    "reteach_lesson": "Reteaching Lesson",
    "targeted_worksheet": "Targeted Practice Worksheet",
    "differentiated_practice": "Differentiated Practice (Support / Core / Challenge)",
    "group_activity": "Temporary Group Activity",
    "reassessment": "Quick Reassessment & Check",
    "homework": "Targeted Homework Task",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_telegram_user_id(
    telegram_user_id: int | None = None, telegram_user: Any = None
) -> int:
    if isinstance(telegram_user_id, int):
        return telegram_user_id
    if isinstance(telegram_user, int):
        return telegram_user
    if telegram_user is not None and hasattr(telegram_user, "id"):
        return int(telegram_user.id)
    raise ValueError("A valid telegram_user or telegram_user_id is required.")


def _generate_action_content(
    action_type: str,
    target_title: str,
    class_info: dict[str, Any],
    analysis_uuid: str,
    duration_minutes: int,
) -> str:
    c_name = class_info.get("display_name", "Class")
    level = class_info.get("level", "B1")
    age = class_info.get("age_group", "adults")
    dur = duration_minutes

    header = (
        f"# {VALID_ACTION_TYPES[action_type]}: {target_title}\n\n"
        f"**Class:** {c_name} ({level} • {age}) | **Duration:** {dur} mins\n"
        f"**What this addresses:** Analysis `{analysis_uuid}` — Targeted Gap: *{target_title}*\n\n"
        f"---\n\n"
    )

    if action_type == "reteach_lesson":
        body = (
            f"## Pedagogical Objective\n"
            f"Learners will diagnose and correct patterns in **{target_title}** through guided discovery and communicative consolidation.\n\n"
            f"## Stage 1: Awareness & Guided Discovery (10 mins)\n"
            f"- Display 3 contrastive student sentences on the board highlighting the target pattern.\n"
            f"- Elicit Concept Checking Questions (CCQs):\n"
            f"  1. Is this action happening now or habitually?\n"
            f"  2. What clue tells us which form or ending to use?\n"
            f"  3. How does correcting this change the clarity for the reader?\n\n"
            f"## Stage 2: Controlled Practice & Peer Spotting (15 mins)\n"
            f"- Paired error-spotting task with 5 targeted sentences.\n"
            f"- Students identify the issue and explain the correction rule to their partner.\n\n"
            f"## Stage 3: Communicative Production (15 mins)\n"
            f"- Mini-speaking or writing prompt requiring 3 active uses of the target form.\n\n"
            f"## Stage 4: Formative Exit Ticket (5 mins)\n"
            f"- 2 quick verification sentences on index cards or chat.\n\n"
            f"## Teacher Notes & Anticipated Difficulties\n"
            f"- Watch for L1 transfer interference in subject-verb or prepositional agreement."
        )

    elif action_type == "targeted_worksheet":
        body = (
            f"## Student Worksheet — {target_title}\n\n"
            f"### Part A: Spot and Underline (5 items)\n"
            f"Read each sentence carefully. Underline where **{target_title}** needs revision:\n"
            f"1. The researcher explain the findings in chapter two.\n"
            f"2. Although public transit is fast, many commuters prefers driving.\n"
            f"3. Environmental policies depends on consistent enforcement.\n"
            f"4. Everyone participate actively during group workshops.\n"
            f"5. The main disadvantage are the substantial implementation costs.\n\n"
            f"### Part B: Rewrite and Correct (5 items)\n"
            f"Rewrite the sentences from Part A with accurate grammatical inflection.\n\n"
            f"### Part C: Creative Contextual Application\n"
            f"Write 3 original sentences about your current unit topic applying the corrected rule.\n\n"
            f"---\n"
            f"## ANSWER KEY & TEACHER NOTES\n"
            f"1. explain -> explains (Third-person singular)\n"
            f"2. prefers -> prefer (Plural subject 'commuters')\n"
            f"3. depends -> depend (Plural subject 'policies')\n"
            f"4. participate -> participates (Indefinite pronoun 'everyone')\n"
            f"5. are -> is (Singular head noun 'disadvantage')"
        )

    elif action_type == "differentiated_practice":
        body = (
            f"## Three-Tier Differentiated Practice: {target_title}\n\n"
            f"### 🟢 Tier 1: Support Route (Guided Scaffolding)\n"
            f"- **Sentence Frames:** 'When [subject] _____ (verb+s), it leads to _____.'\n"
            f"- **Word Bank:** explains / suggests / demonstrates / increases / requires\n"
            f"- **Task:** Fill in the blanks with the correct form from the bank with partner coaching.\n\n"
            f"### 🟡 Tier 2: Core Route (Standard Application)\n"
            f"- **Task:** Identify and edit 6 error items in an authentic paragraph without word bank hints.\n\n"
            f"### 🟣 Tier 3: Challenge Route (Transfer & Extension)\n"
            f"- **Task:** Compose a 100-word response defending a viewpoint, intentionally incorporating 4 complex subject-verb clauses.\n\n"
            f"## Teacher Grouping & Monitoring Protocol\n"
            f"- Discreetly distribute color-coded slips based on diagnosed needs; reconnect for whole-class synthesis."
        )

    elif action_type == "group_activity":
        body = (
            f"## Fluid Group Collaboration: The Editing Clinic\n\n"
            f"### Setup & Roles\n"
            f"- Groups of 3–4 students: **Rule Captain**, **Sentence Editor**, **Reporter**.\n\n"
            f"### Activity Protocol (20 mins)\n"
            f"1. Each team receives a 'patient' text containing 4 diagnosed weaknesses in **{target_title}**.\n"
            f"2. Teams collaborate to 'cure' the text by rewriting sentences on mini-whiteboards.\n"
            f"3. Teams rotate to audit other teams' solutions and award accuracy stars.\n\n"
            f"### Synthesis (10 mins)\n"
            f"- Group reporters share the most memorable rule explanation discovered."
        )

    elif action_type == "reassessment":
        body = (
            f"## 10-Minute Formative Reassessment: {target_title}\n\n"
            f"**Name:** ____________________ | **Date:** ____________\n\n"
            f"**Instructions:** Complete the 4 diagnostic questions below.\n\n"
            f"1. Correct the error in this sentence: *'Each participant submit their summary on Monday.'*\n"
            f"2. Choose the correct verb form: *'Neither the manager nor the employees (is / are) responsible.'*\n"
            f"3. Combine these clauses with correct agreement: *'The list of ingredients (be) short. The recipe (work) well.'*\n"
            f"4. Write 1 sentence explaining the rule in your own words.\n\n"
            f"---\n"
            f"## Marking Rubric (4 Points Total)\n"
            f"- 4/4: Mastery demonstrated (ready for progression)\n"
            f"- 2-3/4: Partial mastery (minor reinforcement needed)\n"
            f"- 0-1/4: Needs targeted 1-on-1 micro-reteach"
        )

    else:  # homework
        body = (
            f"## Targeted Home Practice: {target_title}\n\n"
            f"### Section 1: Self-Audit (10 mins)\n"
            f"Review your previous composition draft. Highlight 3 instances of **{target_title}** and verify each one.\n\n"
            f"### Section 2: Revision Practice (15 mins)\n"
            f"Write 4 revised sentences based on today's classroom feedback, showing clear improvement.\n\n"
            f"### Section 3: Reflection Question\n"
            f"*'What strategy will you use next time you write to check for this pattern before submitting?'*"
        )

    return header + body


def create_analysis_followup_action(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    analysis_id: int,
    action_type: str,
    finding_target_title: str | None = None,
    duration_minutes: int = 30,
    save_to_library: bool = True,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Generate a targeted teaching action strictly derived from an approved evidence analysis."""
    resolved_id = _resolve_telegram_user_id(telegram_user_id, telegram_user)

    norm_type = action_type.strip().lower()
    if norm_type not in VALID_ACTION_TYPES:
        raise ValueError(f"Invalid action_type '{action_type}'. Must be one of {set(VALID_ACTION_TYPES.keys())}")

    if not (5 <= duration_minutes <= 180):
        raise ValueError("duration_minutes must be between 5 and 180 minutes.")

    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (resolved_id,)
        ).fetchone()
        if user is None:
            raise ValueError(f"User {resolved_id} not registered.")
        user_id = int(user["id"])

        # Fetch analysis and class context
        an_row = connection.execute(
            """
            SELECT a.*, c.display_name, c.level, c.age_group, c.learner_count_band, c.goal
            FROM evidence_analysis_results AS a
            JOIN classes AS c ON c.id = a.class_id
            WHERE a.id = ? AND a.user_id = ?
            """,
            (analysis_id, user_id),
        ).fetchone()

        if an_row is None:
            raise ValueError(f"Evidence analysis {analysis_id} not found for this user.")

        analysis = dict(an_row)

        # Invariant: Must be approved
        if not analysis.get("approved"):
            raise ValueError("Cannot create follow-up action from an unapproved analysis. Please approve the analysis first.")

        findings = json.loads(analysis["findings_json"])

        # Determine target finding
        target = finding_target_title.strip() if finding_target_title else ""
        if not target:
            priorities = findings.get("next_priorities", [])
            errors = findings.get("common_errors", [])
            if priorities:
                target = priorities[0].get("title", "Targeted Gap")
            elif errors:
                target = errors[0].get("pattern", "Targeted Gap")
            else:
                target = "Identified Class Gap"

        content_markdown = _generate_action_content(
            action_type=norm_type,
            target_title=target,
            class_info=analysis,
            analysis_uuid=analysis["analysis_uuid"],
            duration_minutes=duration_minutes,
        )

        followup_uuid = f"fa-{secrets.token_hex(8)}"
        now = _utc_now()

        material_id = None
        if save_to_library:
            mat_type = "lesson" if "lesson" in norm_type else "worksheet" if "worksheet" in norm_type else "activity" if "activity" in norm_type else "assessment"
            title = f"[{VALID_ACTION_TYPES[norm_type]}] {target}"
            meta_json = json.dumps({
                "duration": f"{duration_minutes} mins",
                "prompt_contract": PROMPT_CONTRACT,
                "prompt_version": PROMPT_VERSION,
                "analysis_id": analysis_id,
                "analysis_uuid": analysis["analysis_uuid"],
            }, sort_keys=True)
            cursor_m = connection.execute(
                """
                INSERT INTO materials (
                    user_id, class_id, material_type, subtype, title, topic,
                    level, content, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    analysis["class_id"],
                    mat_type,
                    norm_type,
                    title,
                    target,
                    analysis.get("level", "B1"),
                    content_markdown,
                    meta_json,
                    now,
                ),
            )
            material_id = cursor_m.lastrowid

            connection.execute(
                """
                INSERT OR IGNORE INTO material_evidence_links (
                    material_id, analysis_id, created_at
                ) VALUES (?, ?, ?)
                """,
                (material_id, analysis_id, now),
            )

        cursor_f = connection.execute(
            """
            INSERT INTO analysis_followup_actions (
                followup_uuid, user_id, class_id, analysis_id,
                finding_target_title, action_type, duration_minutes,
                material_id, content_markdown, status,
                prompt_contract, prompt_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'generated', ?, ?, ?, ?)
            """,
            (
                followup_uuid,
                user_id,
                analysis["class_id"],
                analysis_id,
                target,
                norm_type,
                duration_minutes,
                material_id,
                content_markdown,
                PROMPT_CONTRACT,
                PROMPT_VERSION,
                now,
                now,
            ),
        )
        followup_id = cursor_f.lastrowid

        connection.execute(
            """
            INSERT OR IGNORE INTO product_events (
                event_uuid, user_id, class_id, event_name, privacy_class,
                properties_json, occurred_at
            ) VALUES (?, ?, ?, 'followup_created', 'product', ?, ?)
            """,
            (
                f"fa-ev:{followup_uuid}",
                user_id,
                analysis["class_id"],
                json.dumps({
                    "followup_id": followup_id,
                    "analysis_id": analysis_id,
                    "action_type": norm_type,
                    "duration": duration_minutes,
                    "material_id": material_id,
                }, sort_keys=True),
                now,
            ),
        )

    return get_analysis_followup_action(
        telegram_user_id=resolved_id,
        followup_id=followup_id,
        database_path=database_path,
    )  # type: ignore[return-value]


def accept_followup_action(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    followup_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Accept and confirm follow-up teaching action (value signal: analysis_approved -> followup_created -> followup_accepted)."""
    resolved_id = _resolve_telegram_user_id(telegram_user_id, telegram_user)

    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (resolved_id,)
        ).fetchone()
        if user is None:
            return None
        user_id = int(user["id"])

        row = connection.execute(
            "SELECT * FROM analysis_followup_actions WHERE id = ? AND user_id = ?",
            (followup_id, user_id),
        ).fetchone()
        if row is None:
            return None

        record = dict(row)
        now = _utc_now()
        connection.execute(
            """
            UPDATE analysis_followup_actions
            SET status = 'accepted', updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (now, followup_id, user_id),
        )

        connection.execute(
            """
            INSERT OR IGNORE INTO product_events (
                event_uuid, user_id, class_id, event_name, privacy_class,
                properties_json, occurred_at
            ) VALUES (?, ?, ?, 'followup_accepted', 'product', ?, ?)
            """,
            (
                f"fa-acc:{followup_id}:{secrets.token_hex(4)}",
                user_id,
                record["class_id"],
                json.dumps({
                    "followup_id": followup_id,
                    "analysis_id": record["analysis_id"],
                    "action_type": record["action_type"],
                }, sort_keys=True),
                now,
            ),
        )

    return get_analysis_followup_action(
        telegram_user_id=resolved_id,
        followup_id=followup_id,
        database_path=database_path,
    )


def get_analysis_followup_action(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    followup_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Retrieve follow-up action with linked class, analysis, and material information."""
    resolved_id = _resolve_telegram_user_id(telegram_user_id, telegram_user)

    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (resolved_id,)
        ).fetchone()
        if user is None:
            return None
        user_id = int(user["id"])

        row = connection.execute(
            """
            SELECT f.*, c.display_name AS class_name, a.analysis_uuid, a.uncertainty
            FROM analysis_followup_actions AS f
            JOIN classes AS c ON c.id = f.class_id
            JOIN evidence_analysis_results AS a ON a.id = f.analysis_id
            WHERE f.id = ? AND f.user_id = ?
            """,
            (followup_id, user_id),
        ).fetchone()
        if row is None:
            return None

        return dict(row)


def list_analysis_followup_actions(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    class_id: int | None = None,
    analysis_id: int | None = None,
    limit: int = 20,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List recent follow-up actions for user/class/analysis."""
    resolved_id = _resolve_telegram_user_id(telegram_user_id, telegram_user)

    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (resolved_id,)
        ).fetchone()
        if user is None:
            return []
        user_id = int(user["id"])

        params: list[Any] = [user_id]
        where_clauses = ["f.user_id = ?"]

        if class_id is not None:
            where_clauses.append("f.class_id = ?")
            params.append(class_id)
        if analysis_id is not None:
            where_clauses.append("f.analysis_id = ?")
            params.append(analysis_id)

        params.append(limit)
        query = f"""
            SELECT f.*, c.display_name AS class_name, a.analysis_uuid
            FROM analysis_followup_actions AS f
            JOIN classes AS c ON c.id = f.class_id
            JOIN evidence_analysis_results AS a ON a.id = f.analysis_id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY f.created_at DESC, f.id DESC
            LIMIT ?
        """
        rows = connection.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]
