from __future__ import annotations

import json
import logging
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from database import database_connection
from feature_flags import feature_enabled


logger = logging.getLogger(__name__)

PROMPT_CONTRACT = "teacheros.evidence_analysis"
PROMPT_VERSION = "2026-08-31.1"

_PERCENTAGE_PATTERN = re.compile(r"\b\d{1,3}(?:\.\d+)?%\b")


class EvidenceAnalysisError(Exception):
    """Raised when evidence analysis encounters a domain or safety error."""


def _require_evidence_feature() -> None:
    if not feature_enabled("evidence"):
        raise PermissionError("Evidence intelligence feature flag is disabled.")


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


def _frequency_band(count: int, total: int) -> str:
    if total <= 0:
        return "few"
    if count == 1 and total == 1:
        return "single_sample"
    ratio = count / total
    if ratio >= 0.60 or count >= 10:
        return "most"
    if ratio >= 0.35 or count >= 4:
        return "many"
    if count >= 2 or ratio >= 0.20:
        return "some"
    return "few"


def _extract_anonymized_findings(
    items: Sequence[dict[str, Any]],
    class_info: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministically analyze evidence items into transparent, cited pedagogical patterns."""
    total = len(items)
    if total == 0:
        raise ValueError("Cannot extract findings from zero evidence items.")

    item_map = {int(it["id"]): it for it in items}
    all_item_ids = list(item_map.keys())

    # Build corpus representations
    texts: list[str] = [str(it["content"]) for it in items]
    labels: list[str] = [str(it["student_label"]) for it in items]

    # Analysis categories
    strengths: list[dict[str, Any]] = []
    common_errors: list[dict[str, Any]] = []
    misconceptions: list[dict[str, Any]] = []
    next_priorities: list[dict[str, Any]] = []
    temporary_groups: list[dict[str, Any]] = []

    # 1. Strengths Extraction
    longer_items = [it for it in items if int(it["word_count"]) >= 8]
    if longer_items:
        s_ids = [int(it["id"]) for it in longer_items]
        s_labels = [str(it["student_label"]) for it in longer_items]
        strengths.append({
            "area": "Task Engagement & Elaboration",
            "description": "Learners produced sustained responses with meaningful vocabulary and complete sentence structures.",
            "item_ids": s_ids,
            "evidence_labels": s_labels,
        })
    else:
        strengths.append({
            "area": "Initial Concept Production",
            "description": "Learners attempted the prompt directly and provided core keywords.",
            "item_ids": all_item_ids,
            "evidence_labels": labels,
        })

    # Vocabulary & Cohesion strength
    cohesive_words = {"because", "however", "therefore", "although", "for example", "furthermore", "and", "so", "but"}
    cohesive_items = [
        it for it in items
        if any(w in str(it["content"]).lower() for w in cohesive_words)
    ]
    if cohesive_items:
        strengths.append({
            "area": "Logical Linking & Cohesion",
            "description": "Evidence demonstrates use of discourse markers to connect ideas.",
            "item_ids": [int(it["id"]) for it in cohesive_items],
            "evidence_labels": [str(it["student_label"]) for it in cohesive_items],
        })

    # 2. Common Errors & Misconceptions Detection
    # Common error patterns in English learner corpora
    error_patterns = [
        (
            "Subject-Verb Agreement",
            "grammar",
            re.compile(r"\b(he|she|it|everyone|someone|everybody)\s+(don't|go|have|like|play|work|think|seem)\b", re.IGNORECASE),
            "Third-person singular inflection omitted in present tense.",
            "Learners may treat singular third-person pronouns identically to plural/first-person forms due to L1 transfer or simplification.",
        ),
        (
            "Tense Consistency",
            "grammar",
            re.compile(r"\b(yesterday|last\s+\w+|ago)\s+.*\b(is|go|goes|see|sees|play|plays|have|has)\b", re.IGNORECASE),
            "Shift to present tense forms within past narrative context.",
            "Learners establish temporal framing once with a time adverbial and omit inflection on subsequent finite verbs.",
        ),
        (
            "Article & Determiner Usage",
            "vocabulary",
            re.compile(r"\b(a|an)\s+(information|advices|homeworks|equipments|furnitures|researches)\b", re.IGNORECASE),
            "Countable article applied to uncountable mass nouns.",
            "Overgeneralization of countable noun morphology to abstract or collective nouns.",
        ),
        (
            "Preposition Collocation",
            "vocabulary",
            re.compile(r"\b(depend\s+of|interested\s+at|good\s+in|listen\s+the|discuss\s+about)\b", re.IGNORECASE),
            "Non-standard prepositional complementation.",
            "Direct translation from Persian/L1 or analogy with semantically related verbs.",
        ),
        (
            "Sentence Boundary & Run-ons",
            "structure",
            re.compile(r"([a-z]{3,}[,;]\s+[a-z]{3,}){3,}", re.IGNORECASE),
            "Comma splice or multi-clause chaining without conjunctions.",
            "Spoken fluency rhythm carried into written composition without punctuation boundaries.",
        ),
    ]

    for err_name, cat, pat, err_desc, mis_hyp in error_patterns:
        matched = [it for it in items if pat.search(str(it["content"]))]
        if matched:
            m_ids = [int(it["id"]) for it in matched]
            m_labels = [str(it["student_label"]) for it in matched]
            band = _frequency_band(len(matched), total)
            common_errors.append({
                "category": cat,
                "error_name": err_name,
                "description": err_desc,
                "frequency_band": band,
                "occurrence_count": len(matched),
                "item_ids": m_ids,
                "evidence_labels": m_labels,
                "examples": [str(it["content"])[:80] + ("..." if len(str(it["content"])) > 80 else "") for it in matched[:2]],
            })
            misconceptions.append({
                "related_error": err_name,
                "hypothesis": mis_hyp,
                "item_ids": m_ids,
                "evidence_labels": m_labels,
            })

    # If no specific regex error matched, check length variation / generic structure
    if not common_errors:
        short_items = [it for it in items if int(it["word_count"]) < 10]
        if short_items:
            s_ids = [int(it["id"]) for it in short_items]
            s_labels = [str(it["student_label"]) for it in short_items]
            common_errors.append({
                "category": "structure",
                "error_name": "Response Brevity & Development",
                "description": "Responses are very short or lack supporting detail.",
                "frequency_band": _frequency_band(len(short_items), total),
                "occurrence_count": len(short_items),
                "item_ids": s_ids,
                "evidence_labels": s_labels,
                "examples": [str(it["content"]) for it in short_items[:2]],
            })
            misconceptions.append({
                "related_error": "Response Brevity & Development",
                "hypothesis": "Learners may lack confidence in expanding sentences or require guided prompt scaffolds.",
                "item_ids": s_ids,
                "evidence_labels": s_labels,
            })
        else:
            common_errors.append({
                "category": "structure",
                "error_name": "Complex Syntax Polish",
                "description": "Responses are generally accurate; refinement needed on clause connectors and advanced lexical variety.",
                "frequency_band": "some",
                "occurrence_count": max(1, total // 2),
                "item_ids": all_item_ids[:2],
                "evidence_labels": labels[:2],
                "examples": [texts[0][:80] + "..."],
            })

    # 3. Next Priorities (Top 1 to 3 actionable next steps)
    priority_idx = 1
    for err in common_errors[:2]:
        next_priorities.append({
            "priority": priority_idx,
            "title": f"Targeted Reteach: {err['error_name']}",
            "action": f"Provide focused 10-minute concept check and practice on {err['description'].lower()}.",
            "item_ids": err["item_ids"],
            "target_frequency_band": err["frequency_band"],
        })
        priority_idx += 1

    if priority_idx <= 3 and strengths:
        next_priorities.append({
            "priority": priority_idx,
            "title": f"Build Upon: {strengths[0]['area']}",
            "action": "Pair learners to model successful structures and encourage collaborative expansion.",
            "item_ids": strengths[0]["item_ids"],
            "target_frequency_band": "class_wide",
        })

    # 4. Optional Temporary Groups (fluid & task-specific)
    if total >= 3 and len(common_errors) >= 1:
        error_item_ids = set(common_errors[0]["item_ids"])
        group_a_items = [it for it in items if int(it["id"]) in error_item_ids]
        group_b_items = [it for it in items if int(it["id"]) not in error_item_ids]
        if group_a_items and group_b_items:
            temporary_groups.append({
                "group_name": "Group A (Guided Review)",
                "focus": f"Scaffolded practice targeting {common_errors[0]['error_name']}.",
                "student_labels": [str(it["student_label"]) for it in group_a_items],
            })
            temporary_groups.append({
                "group_name": "Group B (Fluency & Extension)",
                "focus": "Peer editing and communicative fluency extension task.",
                "student_labels": [str(it["student_label"]) for it in group_b_items],
            })

    # Traceability Verification: Enforce that all cited item_ids exist in items
    for block_name, block_list in [
        ("strengths", strengths),
        ("common_errors", common_errors),
        ("misconceptions", misconceptions),
        ("next_priorities", next_priorities),
    ]:
        for entry in block_list:
            cited_ids = entry.get("item_ids", [])
            if not cited_ids:
                raise EvidenceAnalysisError(f"Finding in {block_name} has no traceable evidence item IDs.")
            for cid in cited_ids:
                if cid not in item_map:
                    raise EvidenceAnalysisError(
                        f"Finding cites non-existent evidence item ID {cid} (not in batch)."
                    )

    return {
        "response_count": total,
        "strengths": strengths,
        "common_errors": common_errors,
        "likely_misconceptions": misconceptions,
        "next_priorities": next_priorities,
        "temporary_groups": temporary_groups,
    }


def _build_default_approved_summary(
    findings: dict[str, Any],
    response_count: int,
    uncertainty: str,
) -> str:
    """Generate a clean, privacy-first summary that survives raw evidence purging."""
    lines: list[str] = [
        f"Evidence Analysis Summary ({response_count} student responses, uncertainty: {uncertainty.upper()}):",
        "",
        "Key Strengths:",
    ]
    for s in findings.get("strengths", []):
        lines.append(f"• {s['area']}: {s['description']}")

    lines.append("")
    lines.append("Common Areas for Growth:")
    for e in findings.get("common_errors", []):
        lines.append(f"• {e['error_name']} ({e['frequency_band']}): {e['description']}")

    if findings.get("likely_misconceptions"):
        lines.append("")
        lines.append("Pedagogical Hypotheses:")
        for m in findings["likely_misconceptions"]:
            lines.append(f"• {m['hypothesis']}")

    if findings.get("next_priorities"):
        lines.append("")
        lines.append("Recommended Next Actions:")
        for p in findings["next_priorities"]:
            lines.append(f"{p['priority']}. {p['title']} — {p['action']}")

    return "\n".join(lines)


def analyze_evidence_batch(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    batch_id: int,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Perform calibrated, transparent, cited pedagogical analysis on an evidence batch."""
    _require_evidence_feature()
    resolved_id = _resolve_telegram_user_id(telegram_user_id, telegram_user)

    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (resolved_id,)
        ).fetchone()
        if user is None:
            raise ValueError(f"User with telegram_user_id {resolved_id} not registered.")
        user_id = int(user["id"])

        batch = connection.execute(
            """
            SELECT * FROM evidence_batches
            WHERE id = ? AND user_id = ? AND status != 'deleted'
            """,
            (batch_id, user_id),
        ).fetchone()
        if batch is None:
            raise ValueError(f"Evidence batch {batch_id} not found or access denied.")

        class_id = int(batch["class_id"])
        class_row = connection.execute(
            "SELECT * FROM classes WHERE id = ? AND user_id = ?", (class_id, user_id)
        ).fetchone()

        # Load active items
        item_rows = connection.execute(
            """
            SELECT * FROM evidence_items
            WHERE batch_id = ? AND user_id = ? AND status = 'active'
            ORDER BY id ASC
            """,
            (batch_id, user_id),
        ).fetchall()
        items = [dict(r) for r in item_rows]

        if not items:
            raise ValueError(
                "Cannot analyze an empty evidence batch. Please submit or restore student work first."
            )

        response_count = len(items)

        # Calibrated Uncertainty Determination
        if response_count <= 2:
            uncertainty = "high"
            uncertainty_reason = (
                f"Based on only {response_count} student response(s). High sample variance; "
                "early exploratory indicator only."
            )
            limited_evidence_notice = (
                f"⚠️ Limited Evidence Notice: Only {response_count} student response(s) analyzed. "
                "Treat findings as preliminary indications, not class-wide mastery."
            )
        elif response_count <= 5:
            uncertainty = "medium"
            uncertainty_reason = (
                f"Based on {response_count} student responses. Patterns are emerging but "
                "may not capture the entire class cohort."
            )
            limited_evidence_notice = (
                f"ℹ️ Moderate Sample Notice: {response_count} student responses analyzed. "
                "Useful for preliminary reteaching focus."
            )
        else:
            uncertainty = "low"
            uncertainty_reason = (
                f"Based on {response_count} student responses with robust coverage across the group."
            )
            limited_evidence_notice = None

        # Generate transparent, cited findings
        findings = _extract_anonymized_findings(items, dict(class_row) if class_row else None)
        findings_json = json.dumps(findings, sort_keys=True, ensure_ascii=False)

        # Validate zero fake percentages in findings text
        if _PERCENTAGE_PATTERN.search(findings_json):
            raise EvidenceAnalysisError("Analysis output contains prohibited invented percentage format.")

        analysis_uuid = f"ea-{secrets.token_hex(8)}"
        cursor = connection.execute(
            """
            INSERT INTO evidence_analysis_results (
                analysis_uuid, batch_id, class_id, user_id, response_count,
                findings_json, uncertainty, uncertainty_reason, limited_evidence_notice,
                approved, status, prompt_contract, prompt_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'draft', ?, ?, ?, ?)
            """,
            (
                analysis_uuid,
                batch_id,
                class_id,
                user_id,
                response_count,
                findings_json,
                uncertainty,
                uncertainty_reason,
                limited_evidence_notice,
                PROMPT_CONTRACT,
                PROMPT_VERSION,
                _utc_now(),
                _utc_now(),
            ),
        )
        analysis_id = cursor.lastrowid

        # Product event (ZERO raw text in telemetry)
        connection.execute(
            """
            INSERT OR IGNORE INTO product_events (
                event_uuid, user_id, class_id, event_name, privacy_class,
                properties_json, occurred_at
            ) VALUES (?, ?, ?, 'evidence_batch_analyzed', 'product', ?, ?)
            """,
            (
                f"ea-ev:{analysis_uuid}",
                user_id,
                class_id,
                json.dumps({
                    "analysis_id": analysis_id,
                    "batch_id": batch_id,
                    "response_count": response_count,
                    "uncertainty": uncertainty,
                }, sort_keys=True),
                _utc_now(),
            ),
        )

    return get_evidence_analysis(
        telegram_user_id=resolved_id,
        analysis_id=analysis_id,
        database_path=database_path,
    )  # type: ignore[return-value]


def approve_evidence_analysis(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    analysis_id: int,
    approved_summary: str | None = None,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Approve an evidence analysis finding and persist its minimal, separate pedagogical summary."""
    _require_evidence_feature()
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
            SELECT * FROM evidence_analysis_results
            WHERE id = ? AND user_id = ? AND status != 'rejected'
            """,
            (analysis_id, user_id),
        ).fetchone()
        if row is None:
            return None

        analysis_dict = dict(row)
        findings = json.loads(analysis_dict["findings_json"])

        summary = approved_summary
        if not summary:
            summary = _build_default_approved_summary(
                findings,
                int(analysis_dict["response_count"]),
                str(analysis_dict["uncertainty"]),
            )

        now = _utc_now()
        connection.execute(
            """
            UPDATE evidence_analysis_results
            SET approved = 1, status = 'approved', approved_summary = ?, approved_at = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (summary, now, now, analysis_id, user_id),
        )

        connection.execute(
            """
            INSERT OR IGNORE INTO product_events (
                event_uuid, user_id, class_id, event_name, privacy_class,
                properties_json, occurred_at
            ) VALUES (?, ?, ?, 'evidence_analysis_approved', 'product', ?, ?)
            """,
            (
                f"ea-appr:{analysis_id}:{secrets.token_hex(4)}",
                user_id,
                int(analysis_dict["class_id"]),
                json.dumps({
                    "analysis_id": analysis_id,
                    "batch_id": int(analysis_dict["batch_id"]),
                    "uncertainty": analysis_dict["uncertainty"],
                }, sort_keys=True),
                now,
            ),
        )

    return get_evidence_analysis(
        telegram_user_id=resolved_id,
        analysis_id=analysis_id,
        database_path=database_path,
    )


def update_analysis_summary(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    analysis_id: int,
    new_summary: str,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Allow teacher to edit and refine the approved pedagogical summary."""
    _require_evidence_feature()
    resolved_id = _resolve_telegram_user_id(telegram_user_id, telegram_user)
    cleaned = new_summary.strip()
    if not cleaned or len(cleaned) > 5000:
        raise ValueError("Approved summary must be between 1 and 5000 characters.")

    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (resolved_id,)
        ).fetchone()
        if user is None:
            return None
        user_id = int(user["id"])

        cursor = connection.execute(
            """
            UPDATE evidence_analysis_results
            SET approved_summary = ?, updated_at = ?
            WHERE id = ? AND user_id = ? AND status != 'rejected'
            """,
            (cleaned, _utc_now(), analysis_id, user_id),
        )
        if cursor.rowcount != 1:
            return None

    return get_evidence_analysis(
        telegram_user_id=resolved_id,
        analysis_id=analysis_id,
        database_path=database_path,
    )


def reject_evidence_analysis(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    analysis_id: int,
    database_path: Path | None = None,
) -> bool:
    """Reject/dismiss an evidence analysis finding."""
    _require_evidence_feature()
    resolved_id = _resolve_telegram_user_id(telegram_user_id, telegram_user)

    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (resolved_id,)
        ).fetchone()
        if user is None:
            return False
        user_id = int(user["id"])

        now = _utc_now()
        cursor = connection.execute(
            """
            UPDATE evidence_analysis_results
            SET status = 'rejected', approved = 0, updated_at = ?
            WHERE id = ? AND user_id = ? AND status != 'rejected'
            """,
            (now, analysis_id, user_id),
        )
        return cursor.rowcount == 1


def get_evidence_analysis(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    analysis_id: int,
    database_path: Path | None = None,
) -> dict[str, Any] | None:
    """Retrieve an evidence analysis with provenance and source availability status."""
    _require_evidence_feature()
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
            SELECT a.*, b.evidence_type, b.source_format, b.retention_policy,
                   c.display_name AS class_name, c.level AS class_level
            FROM evidence_analysis_results AS a
            JOIN evidence_batches AS b ON b.id = a.batch_id
            JOIN classes AS c ON c.id = a.class_id
            WHERE a.id = ? AND a.user_id = ?
            """,
            (analysis_id, user_id),
        ).fetchone()
        if row is None:
            return None

        result = dict(row)
        result["findings"] = json.loads(result["findings_json"])

        # Provenance verification: Check if underlying raw items are still active
        batch_id = int(result["batch_id"])
        active_items_count = connection.execute(
            "SELECT COUNT(*) FROM evidence_items WHERE batch_id = ? AND user_id = ? AND status = 'active'",
            (batch_id, user_id),
        ).fetchone()[0]

        result["source_evidence_active_count"] = int(active_items_count)
        result["source_evidence_purged_or_deleted"] = bool(active_items_count == 0)
        return result


def list_evidence_analyses(
    *,
    telegram_user_id: int | None = None,
    telegram_user: Any = None,
    class_id: int | None = None,
    batch_id: int | None = None,
    limit: int = 20,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List recent evidence analysis results for a class or batch."""
    _require_evidence_feature()
    resolved_id = _resolve_telegram_user_id(telegram_user_id, telegram_user)

    with database_connection(database_path) as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (resolved_id,)
        ).fetchone()
        if user is None:
            return []
        user_id = int(user["id"])

        params: list[Any] = [user_id]
        where_clauses = ["a.user_id = ?"]

        if class_id is not None:
            where_clauses.append("a.class_id = ?")
            params.append(class_id)
        if batch_id is not None:
            where_clauses.append("a.batch_id = ?")
            params.append(batch_id)

        params.append(limit)
        query = f"""
            SELECT a.*, b.evidence_type, b.source_format,
                   c.display_name AS class_name
            FROM evidence_analysis_results AS a
            JOIN evidence_batches AS b ON b.id = a.batch_id
            JOIN classes AS c ON c.id = a.class_id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT ?
        """
        rows = connection.execute(query, tuple(params)).fetchall()
        results: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["findings"] = json.loads(d["findings_json"])
            results.append(d)
        return results
