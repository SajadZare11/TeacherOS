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

PROMPT_CONTRACT = "teacheros.differentiation"
PROMPT_VERSION = "2026-08-31.1"

VALID_ADAPTATION_TYPES = {
    "shorter": "Shorter Version (-15 to 20 mins)",
    "longer_plus15": "Extended Depth (+15 mins)",
    "fast_finisher": "Fast Finisher Extension",
    "easier_scaffold": "High-Scaffold Route",
    "harder_extension": "Advanced Challenge Extension",
    "no_tech_low_resource": "Zero-Tech / Low-Resource Version",
    "large_class": "Large Class Protocol (25+ students)",
    "more_communicative": "Paired Interactive / Communicative",
    "more_exam_focused": "Exam Task Format (Timed & Scored)",
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


def _build_support_route(title: str, topic: str, level: str) -> str:
    return (
        f"### 🟢 Support Route: Guided Scaffolding\n"
        f"- **Objective:** Same core standard with step-by-step cognitive scaffolding.\n"
        f"- **Model Sentence Frame:** 'Although [cause / condition], [main outcome].'\n"
        f"- **Target Word Bank:** although / however / therefore / in contrast / significantly\n"
        f"- **Guided Micro-Steps:**\n"
        f"  1. Read the 3 provided model sentences and highlight the transition word.\n"
        f"  2. Choose the best connector from the word bank to complete 3 paired ideas.\n"
        f"  3. Write 2 original sentences with your peer coach before independent checking."
    )


def _build_core_route(title: str, topic: str, level: str) -> str:
    return (
        f"### 🟡 Core Route: Standard Application\n"
        f"- **Objective:** Independent demonstration of {topic} at {level} level.\n"
        f"- **Task Instructions:**\n"
        f"  1. Analyze the short paragraph and identify 4 opportunities for advanced cohesion.\n"
        f"  2. Rewrite the paragraph independently incorporating appropriate transitions.\n"
        f"  3. Exchange drafts with a peer for criteria-based accuracy checking."
    )


def _build_challenge_route(title: str, topic: str, level: str) -> str:
    return (
        f"### 🟣 Challenge Route: Transfer & Cognitive Depth\n"
        f"- **Objective:** Same core standard applied to complex reasoning and debate.\n"
        f"- **Task Instructions (Not Busywork):**\n"
        f"  1. Read two opposing arguments regarding {topic}.\n"
        f"  2. Synthesize both viewpoints into a 120-word nuanced critique.\n"
        f"  3. Justify your linguistic choices and explain why specific connectors were selected."
    )


def _build_delivery_guidance(level: str) -> str:
    return (
        f"### 📋 Classroom Delivery & Grouping Guidance\n"
        f"- **Discreet Distribution:** Provide tiered tasks via color-coded assignment cards (Green / Gold / Purple) or self-selection choice boards to avoid stigmatization.\n"
        f"- **Monitoring Protocol:** Spend the first 4 minutes observing Support groups to ensure initial momentum; then circulate to Challenge groups to probe reasoning.\n"
        f"- **Whole-Class Reconnection:** Reassemble class for a 5-minute debrief where students from all three tiers contribute findings toward the shared objective."
    )


def _build_adapted_content(
    adaptation_type: str,
    original_title: str,
    original_topic: str,
    original_level: str,
    original_content: str,
) -> tuple[str, str, str]:
    """Return (title, changes_summary, adapted_content_markdown)."""
    type_name = VALID_ADAPTATION_TYPES[adaptation_type]
    title = f"{original_title} ({type_name})"

    if adaptation_type == "shorter":
        summary = "Condensed from 45 mins to 25 mins by streamlining warm-up and focusing directly on core practice."
        content = (
            f"# {title}\n\n"
            f"**Quick-Paced 25-Minute Version** | Level: {original_level}\n"
            f"**Pedagogical Changes:** Retains the primary objective while merging stages 1 & 2 into a 5-minute rapid hook.\n\n"
            f"## Stage 1: Rapid 5-Minute Activation\n"
            f"- Board 2 key contrasting examples immediately.\n\n"
            f"## Stage 2: 15-Minute Core Production\n"
            f"- Paired task directly targeting {original_topic}.\n\n"
            f"## Stage 3: 5-Minute Fast Exit Ticket\n"
            f"- Individual verification check."
        )

    elif adaptation_type == "longer_plus15":
        summary = "Extended by +15 minutes with structured peer debate and metacognitive reflection."
        content = (
            f"# {title}\n\n"
            f"**Extended 60-Minute Version** | Level: {original_level}\n"
            f"**Pedagogical Changes:** Adds deep peer review cycle and oral debate defense.\n\n"
            f"{original_content}\n\n"
            f"## Additional +15 Min Extension: Critical Synthesis\n"
            f"- Pairs rotate to audit other teams' work using rubric criteria.\n"
            f"- Whole-class debate defending conclusions."
        )

    elif adaptation_type == "fast_finisher":
        summary = "Added self-directed lateral thinking and real-world application tasks for early finishers."
        content = (
            f"# {title}\n\n"
            f"## Fast-Finisher Extension Tasks (No Busywork)\n"
            f"1. **Rule Explainer:** Write a 3-sentence 'Cheat Sheet' tip for a student who missed class today.\n"
            f"2. **Real-World Transfer:** Find an authentic online news sentence on {original_topic} and identify how connectors are used.\n"
            f"3. **Peer Editor Role:** Act as the roving consultant for teams requesting second-opinion audits."
        )

    elif adaptation_type == "easier_scaffold":
        summary = "Added visual cues, graphic organizers, and pre-populated sentence frames for maximum support."
        content = (
            f"# {title}\n\n"
            f"**Scaffolded Edition** | Level: {original_level}\n\n"
            f"### Scaffolding Aids Included:\n"
            f"- Pre-filled Venn diagram organizer for ideas.\n"
            f"- 4 bilingual glossed vocabulary hints.\n"
            f"- Sentence completion starters with highlighted grammar markers."
        )

    elif adaptation_type == "harder_extension":
        summary = "Elevated lexical demands and added counter-argumentation requirement."
        content = (
            f"# {title}\n\n"
            f"**Advanced Academic Edition** | Level: {original_level}\n\n"
            f"### Advanced Constraints:\n"
            f"- Must incorporate at least 2 concessive clauses ('Notwithstanding...', 'In spite of the fact that...').\n"
            f"- Include refutation of an alternative viewpoint."
        )

    elif adaptation_type == "no_tech_low_resource":
        summary = "Redesigned for paper/chalkboard only; no audio, projector, or internet required."
        content = (
            f"# {title}\n\n"
            f"**Zero-Tech / Low-Resource Version**\n\n"
            f"### Classroom Setup Instructions:\n"
            f"- Divide the chalkboard into 3 vertical columns: (Examples | Practice | Rules).\n"
            f"- Students use standard notebook paper in pairs.\n"
            f"- Physical 'Walk and Talk' mingling activity replaces digital polling."
        )

    elif adaptation_type == "large_class":
        summary = "Structured for 25+ students using pyramid grouping (1 -> 2 -> 4) and silent signaling."
        content = (
            f"# {title}\n\n"
            f"**Large Class Management Protocol (25+ Learners)**\n\n"
            f"### Organization & Acoustic Control:\n"
            f"- **Pyramid Pairing:** Think (individual 1 min) -> Pair (2 mins) -> Square (group of 4, 5 mins).\n"
            f"- **Silent Signaling:** Thumbs up / sideways for comprehension check instead of individual shouting."
        )

    elif adaptation_type == "more_communicative":
        summary = "Transformed reading/writing exercises into lively paired negotiation and oral information-gap."
        content = (
            f"# {title}\n\n"
            f"**High-Interaction Communicative Version**\n\n"
            f"### Paired Information-Gap Setup:\n"
            f"- Student A and Student B receive complementary scenario cards.\n"
            f"- Must orally negotiate a compromise regarding {original_topic} before writing down their agreed resolution."
        )

    else:  # more_exam_focused
        summary = "Reformatted to match standard international examination timing, rubric scales, and scoring guides."
        content = (
            f"# {title}\n\n"
            f"**Exam Simulation Edition (Cambridge / IELTS Style)**\n\n"
            f"### Exam Specifications:\n"
            f"- **Time Limit:** Exactly 20 minutes under timed conditions.\n"
            f"- **Word Limit:** 140–190 words.\n"
            f"- **Assessment Band Descriptors:** Evaluated against Task Achievement, Coherence & Cohesion, and Lexical Resource."
        )

    return title, summary, content


def generate_tiered_differentiation(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    source_material_id: int,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Generate 3-tier differentiation (Support, Core, Challenge) sharing the exact same can-do objective."""
    resolved_id = _resolve_telegram_user_id(telegram_user_id, telegram_user)

    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (resolved_id,)
        ).fetchone()
        if user is None:
            raise ValueError(f"User {resolved_id} not registered.")
        user_id = int(user["id"])

        mat_row = connection.execute(
            "SELECT * FROM materials WHERE id = ? AND user_id = ?",
            (source_material_id, user_id),
        ).fetchone()
        if mat_row is None:
            raise ValueError(f"Material {source_material_id} not found for this user.")

        mat = dict(mat_row)
        topic = mat.get("topic") or mat.get("title") or "Classroom Objective"
        level = mat.get("level") or "B1"
        objective = f"Students can accurately understand and produce {topic} in context."

        support = _build_support_route(mat["title"], topic, level)
        core = _build_core_route(mat["title"], topic, level)
        challenge = _build_challenge_route(mat["title"], topic, level)
        guidance = _build_delivery_guidance(level)

        diff_uuid = f"df-{secrets.token_hex(8)}"
        now = _utc_now()

        cursor = connection.execute(
            """
            INSERT INTO material_differentiations (
                diff_uuid, user_id, class_id, source_material_id,
                objective, support_route_markdown, core_route_markdown,
                challenge_route_markdown, delivery_guidance_markdown,
                prompt_contract, prompt_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                diff_uuid,
                user_id,
                mat.get("class_id"),
                source_material_id,
                objective,
                support,
                core,
                challenge,
                guidance,
                PROMPT_CONTRACT,
                PROMPT_VERSION,
                now,
            ),
        )
        diff_id = cursor.lastrowid

        connection.execute(
            """
            INSERT OR IGNORE INTO product_events (
                event_uuid, user_id, class_id, event_name, privacy_class,
                properties_json, occurred_at
            ) VALUES (?, ?, ?, 'material_differentiated', 'product', ?, ?)
            """,
            (
                f"df-ev:{diff_uuid}",
                user_id,
                mat.get("class_id"),
                json.dumps({"material_id": source_material_id, "diff_id": diff_id}, sort_keys=True),
                now,
            ),
        )

    return get_tiered_differentiation(
        telegram_user_id=resolved_id,
        differentiation_id=diff_id,
        database_path=database_path,
    )  # type: ignore[return-value]


def generate_one_tap_adaptation(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    source_material_id: int,
    adaptation_type: str,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Generate 1-tap emergency adaptation preserving source material and explaining changes."""
    resolved_id = _resolve_telegram_user_id(telegram_user_id, telegram_user)

    norm_type = adaptation_type.strip().lower()
    if norm_type not in VALID_ADAPTATION_TYPES:
        raise ValueError(f"Invalid adaptation_type '{adaptation_type}'. Must be one of {set(VALID_ADAPTATION_TYPES.keys())}")

    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (resolved_id,)
        ).fetchone()
        if user is None:
            raise ValueError(f"User {resolved_id} not registered.")
        user_id = int(user["id"])

        mat_row = connection.execute(
            "SELECT * FROM materials WHERE id = ? AND user_id = ?",
            (source_material_id, user_id),
        ).fetchone()
        if mat_row is None:
            raise ValueError(f"Material {source_material_id} not found for this user.")

        mat = dict(mat_row)
        topic = mat.get("topic") or "General"
        level = mat.get("level") or "B1"

        title, summary, adapted_content = _build_adapted_content(
            adaptation_type=norm_type,
            original_title=mat["title"],
            original_topic=topic,
            original_level=level,
            original_content=mat.get("content", ""),
        )

        adaptation_uuid = f"ad-{secrets.token_hex(8)}"
        now = _utc_now()

        cursor = connection.execute(
            """
            INSERT INTO material_adaptations (
                adaptation_uuid, user_id, class_id, source_material_id,
                adaptation_type, title, changes_summary,
                adapted_content_markdown, prompt_contract, prompt_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                adaptation_uuid,
                user_id,
                mat.get("class_id"),
                source_material_id,
                norm_type,
                title,
                summary,
                adapted_content,
                PROMPT_CONTRACT,
                PROMPT_VERSION,
                now,
            ),
        )
        adaptation_id = cursor.lastrowid

        connection.execute(
            """
            INSERT OR IGNORE INTO product_events (
                event_uuid, user_id, class_id, event_name, privacy_class,
                properties_json, occurred_at
            ) VALUES (?, ?, ?, 'material_adapted', 'product', ?, ?)
            """,
            (
                f"ad-ev:{adaptation_uuid}",
                user_id,
                mat.get("class_id"),
                json.dumps({
                    "material_id": source_material_id,
                    "adaptation_id": adaptation_id,
                    "adaptation_type": norm_type,
                }, sort_keys=True),
                now,
            ),
        )

    return get_material_adaptation(
        telegram_user_id=resolved_id,
        adaptation_id=adaptation_id,
        database_path=database_path,
    )  # type: ignore[return-value]


def get_tiered_differentiation(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    differentiation_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Retrieve 3-tier differentiation record."""
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
            SELECT d.*, m.title AS source_title, m.material_type
            FROM material_differentiations AS d
            JOIN materials AS m ON m.id = d.source_material_id
            WHERE d.id = ? AND d.user_id = ?
            """,
            (differentiation_id, user_id),
        ).fetchone()
        if row is None:
            return None
        return dict(row)


def get_material_adaptation(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    adaptation_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Retrieve material adaptation record."""
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
            SELECT a.*, m.title AS source_title, m.material_type
            FROM material_adaptations AS a
            JOIN materials AS m ON m.id = a.source_material_id
            WHERE a.id = ? AND a.user_id = ?
            """,
            (adaptation_id, user_id),
        ).fetchone()
        if row is None:
            return None
        return dict(row)


def list_material_adaptations(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    source_material_id: int,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List all adaptations generated for a specific material."""
    resolved_id = _resolve_telegram_user_id(telegram_user_id, telegram_user)

    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (resolved_id,)
        ).fetchone()
        if user is None:
            return []
        user_id = int(user["id"])

        rows = connection.execute(
            """
            SELECT a.*, m.title AS source_title
            FROM material_adaptations AS a
            JOIN materials AS m ON m.id = a.source_material_id
            WHERE a.source_material_id = ? AND a.user_id = ?
            ORDER BY a.created_at DESC
            """,
            (source_material_id, user_id),
        ).fetchall()
        return [dict(r) for r in rows]
