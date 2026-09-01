from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from day5_migration import apply_schema_v6
from day7_migration import apply_schema_v7
from day8_migration import apply_schema_v8
from day9_migration import apply_schema_v9
from day10_migration import apply_schema_v10
from day11_migration import apply_schema_v11
from day12_migration import apply_schema_v12
from day13_migration import apply_schema_v13
from day15_migration import apply_schema_v15
from day16_migration import apply_schema_v16
from day17_migration import apply_schema_v17
from day18_migration import apply_schema_v18
from day19_migration import apply_schema_v19
from day20_migration import apply_schema_v20
from day21_migration import apply_schema_v21
from day22_migration import apply_schema_v22
from config import (
    DATABASE_PATH,
    FREE_DAILY_GENERATION_LIMIT,
    PLAN_DAILY_LIMITS,
    PLAN_NAMES,
    USAGE_TIMEZONE,
    get_usage_timezone,
    ZARINPAL_SANDBOX,
)

_VALID_MATERIAL_TYPES = {"lesson", "activity", "worksheet", "assessment"}
_VALID_PAID_PLANS = {"pro", "premium"}
_PLAN_RANK = {"free": 0, "pro": 1, "premium": 2}
_VALID_FEEDBACK_AREAS = {
    "lesson",
    "activity",
    "worksheet",
    "assessment",
    "library",
    "search",
    "account",
    "website",
    "other",
}


@contextmanager
def _connection(database_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open one short-lived SQLite connection with safe defaults."""
    target_path = Path(database_path or DATABASE_PATH).expanduser().resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    """Add one migration column when an older SQLite database does not have it."""
    existing = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_utc_text(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _usage_day_start_utc() -> str:
    local_now = datetime.now(get_usage_timezone())
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return _utc_text(local_start)


def initialize_database(database_path: Path | None = None) -> Path:
    """Create the TeacherOS database and tables when they do not exist."""
    target_path = Path(database_path or DATABASE_PATH).expanduser().resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with _connection(target_path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_versions (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL UNIQUE,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language_code TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                material_type TEXT NOT NULL CHECK (
                    material_type IN ('lesson', 'activity', 'worksheet', 'assessment')
                ),
                subtype TEXT,
                title TEXT NOT NULL,
                level TEXT,
                topic TEXT,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_materials_user_created
                ON materials(user_id, created_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_materials_user_type
                ON materials(user_id, material_type);

            CREATE INDEX IF NOT EXISTS idx_materials_user_topic
                ON materials(user_id, topic);

            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL CHECK (
                    event_type IN ('generation', 'word_export', 'pdf_export')
                ),
                material_type TEXT CHECK (
                    material_type IS NULL OR
                    material_type IN ('lesson', 'activity', 'worksheet', 'assessment')
                ),
                material_id INTEGER,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_usage_events_user_created
                ON usage_events(user_id, created_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_usage_events_user_type
                ON usage_events(user_id, event_type);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_generation_material
                ON usage_events(event_type, material_id)
                WHERE event_type = 'generation' AND material_id IS NOT NULL;

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider TEXT NOT NULL DEFAULT 'zarinpal' CHECK (provider = 'zarinpal'),
                order_id TEXT NOT NULL UNIQUE,
                purpose TEXT NOT NULL,
                amount INTEGER NOT NULL CHECK (amount > 0),
                currency TEXT NOT NULL CHECK (currency IN ('IRT', 'IRR')),
                status TEXT NOT NULL CHECK (
                    status IN ('created', 'pending', 'paid', 'failed', 'cancelled')
                ),
                authority TEXT UNIQUE,
                payment_url TEXT,
                callback_token_hash TEXT NOT NULL UNIQUE,
                ref_id TEXT,
                card_pan TEXT,
                card_hash TEXT,
                provider_code INTEGER,
                provider_message TEXT,
                is_sandbox INTEGER NOT NULL DEFAULT 1 CHECK (is_sandbox IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                verified_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_payments_user_created
                ON payments(user_id, created_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_payments_status_created
                ON payments(status, created_at DESC, id DESC);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_provider_ref
                ON payments(provider, ref_id)
                WHERE ref_id IS NOT NULL;

            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_code TEXT NOT NULL CHECK (plan_code IN ('pro', 'premium')),
                source TEXT NOT NULL CHECK (source IN ('payment', 'manual')),
                source_payment_id INTEGER UNIQUE,
                starts_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
                is_sandbox INTEGER NOT NULL DEFAULT 0 CHECK (is_sandbox IN (0, 1)),
                granted_by_telegram_id INTEGER,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (source_payment_id) REFERENCES payments(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_subscriptions_user_expiry
                ON subscriptions(user_id, status, expires_at DESC);

            CREATE INDEX IF NOT EXISTS idx_subscriptions_plan_expiry
                ON subscriptions(plan_code, status, expires_at DESC);

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                area TEXT NOT NULL CHECK (
                    area IN (
                        'lesson', 'activity', 'worksheet', 'assessment',
                        'library', 'search', 'account', 'website', 'other'
                    )
                ),
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open' CHECK (
                    status IN ('open', 'reviewed', 'resolved')
                ),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TEXT,
                resolved_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_feedback_status_created
                ON feedback(status, created_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_feedback_user_created
                ON feedback(user_id, created_at DESC, id DESC);

            INSERT OR IGNORE INTO schema_versions(version) VALUES (1);
            INSERT OR IGNORE INTO schema_versions(version) VALUES (2);
            INSERT OR IGNORE INTO schema_versions(version) VALUES (3);
            INSERT OR IGNORE INTO schema_versions(version) VALUES (4);
            INSERT OR IGNORE INTO schema_versions(version) VALUES (5);

            INSERT OR IGNORE INTO usage_events (
                user_id, event_type, material_type, material_id, created_at
            )
            SELECT
                user_id, 'generation', material_type, id, created_at
            FROM materials;
            """
        )
        _ensure_column(connection, "payments", "product_code", "TEXT")
        _ensure_column(connection, "payments", "subscription_days", "INTEGER")
        apply_schema_v6(connection)
        apply_schema_v7(connection)
        apply_schema_v8(connection)
        apply_schema_v9(connection)
        apply_schema_v10(connection)
        apply_schema_v11(connection)
        apply_schema_v12(connection)
        apply_schema_v13(connection)
        apply_schema_v15(connection)
        apply_schema_v16(connection)
        apply_schema_v17(connection)
        apply_schema_v18(connection)
        apply_schema_v19(connection)
        apply_schema_v20(connection)
        apply_schema_v21(connection)
        apply_schema_v22(connection)

    return target_path


@contextmanager
def database_connection(
    database_path: Path | None = None,
) -> Iterator[sqlite3.Connection]:
    """Yield an initialized database connection for ownership-safe services."""
    target_path = initialize_database(database_path)
    with _connection(target_path) as connection:
        yield connection


def _upsert_user(connection: sqlite3.Connection, telegram_user: Any) -> int:
    telegram_user_id = getattr(telegram_user, "id", None)
    if not isinstance(telegram_user_id, int):
        raise ValueError("A valid Telegram user is required before saving material.")

    connection.execute(
        """
        INSERT INTO users (
            telegram_user_id,
            username,
            first_name,
            last_name,
            language_code
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(telegram_user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            language_code = excluded.language_code,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            telegram_user_id,
            getattr(telegram_user, "username", None),
            getattr(telegram_user, "first_name", None),
            getattr(telegram_user, "last_name", None),
            getattr(telegram_user, "language_code", None),
        ),
    )

    row = connection.execute(
        "SELECT id FROM users WHERE telegram_user_id = ?",
        (telegram_user_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("TeacherOS could not create or find the database user.")
    return int(row["id"])


def ensure_database_user(connection: sqlite3.Connection, telegram_user: Any) -> int:
    """Create or refresh a Telegram user inside an existing transaction."""
    return _upsert_user(connection, telegram_user)


def register_telegram_user(telegram_user: Any) -> int:
    """Create or refresh one Telegram user's database record."""
    initialize_database()
    with _connection() as connection:
        return _upsert_user(connection, telegram_user)


def save_generated_material(
    *,
    telegram_user: Any,
    material_type: str,
    title: str,
    content: str,
    subtype: str | None = None,
    level: str | None = None,
    topic: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    class_id: int | None = None,
    objective_ids: tuple[int, ...] | list[int] = (),
    ai_provenance: Mapping[str, Any] | None = None,
    quality_scores: Mapping[str, Any] | None = None,
) -> int:
    """Save one completed TeacherOS generation and return its library ID."""
    normalized_type = material_type.strip().lower()
    if normalized_type not in _VALID_MATERIAL_TYPES:
        raise ValueError(f"Unsupported material type: {material_type}")

    normalized_title = title.strip()
    normalized_content = content.strip()
    if not normalized_title:
        raise ValueError("Material title cannot be empty.")
    if not normalized_content:
        raise ValueError("Generated material cannot be empty.")

    metadata_json = json.dumps(
        dict(metadata or {}),
        ensure_ascii=False,
        sort_keys=True,
    )
    provenance = dict(ai_provenance or {})
    sources = provenance.get("source_record_ids", {})
    if not isinstance(sources, Mapping):
        sources = {}
    normalized_objective_ids = tuple(dict.fromkeys(int(value) for value in objective_ids))
    if any(value < 1 for value in normalized_objective_ids):
        raise ValueError("Objective IDs must be positive integers.")

    initialize_database()
    with _connection() as connection:
        user_id = _upsert_user(connection, telegram_user)
        cursor = connection.execute(
            """
            INSERT INTO materials (
                user_id,
                material_type,
                subtype,
                title,
                level,
                topic,
                content,
                metadata_json,
                class_id,
                ai_prompt_contract,
                ai_prompt_version,
                ai_prompt_hash_sha256,
                ai_context_hash_sha256,
                ai_source_record_ids_json,
                quality_scores_json
            )
            SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            WHERE ? IS NULL OR EXISTS (
                SELECT 1 FROM classes
                WHERE id = ? AND user_id = ? AND status = 'active'
            )
            """,
            (
                user_id,
                normalized_type,
                subtype.strip() if isinstance(subtype, str) and subtype.strip() else None,
                normalized_title,
                level.strip() if isinstance(level, str) and level.strip() else None,
                topic.strip() if isinstance(topic, str) and topic.strip() else None,
                normalized_content,
                metadata_json,
                class_id,
                provenance.get("prompt_contract"),
                provenance.get("prompt_version"),
                provenance.get("prompt_hash_sha256"),
                provenance.get("context_hash_sha256"),
                json.dumps(dict(sources), ensure_ascii=False, sort_keys=True),
                json.dumps(dict(quality_scores or {}), ensure_ascii=False, sort_keys=True),
                class_id,
                class_id,
                user_id,
            ),
        )
        material_id = cursor.lastrowid
        if material_id is None or cursor.rowcount != 1:
            raise RuntimeError("TeacherOS could not save the generated material.")

        for objective_id in normalized_objective_ids:
            objective = connection.execute(
                "SELECT 1 FROM class_objectives WHERE id = ? AND class_id = ? "
                "AND user_id = ? AND status = 'current'",
                (objective_id, class_id, user_id),
            ).fetchone()
            if class_id is None or objective is None:
                raise ValueError("Objective link does not belong to the active class.")
            connection.execute(
                "INSERT INTO material_objective_links "
                "(material_id, objective_id, class_id, user_id) VALUES (?, ?, ?, ?)",
                (int(material_id), objective_id, class_id, user_id),
            )

        if normalized_type == "lesson" and class_id is not None:
            lesson_cursor = connection.execute(
                """
                INSERT OR IGNORE INTO class_lessons (
                    class_id, user_id, material_id, title, status,
                    lifecycle_state, origin_key
                ) VALUES (?, ?, ?, ?, 'draft', 'generated', ?)
                """,
                (class_id, user_id, int(material_id), normalized_title, f"material:{material_id}"),
            )
            lesson_row = connection.execute(
                "SELECT id FROM class_lessons WHERE origin_key = ?",
                (f"material:{material_id}",),
            ).fetchone()
            if lesson_row is None:
                raise RuntimeError("TeacherOS could not create the generated lesson record.")
            if lesson_cursor.rowcount == 1:
                connection.execute(
                    """
                    INSERT INTO class_lesson_transitions (
                        event_uuid, class_lesson_id, class_id, user_id,
                        from_state, to_state, reason
                    ) VALUES (?, ?, ?, ?, NULL, 'generated', 'material_generated')
                    """,
                    (
                        f"lesson-generated:{material_id}", int(lesson_row["id"]),
                        class_id, user_id,
                    ),
                )

        connection.execute(
            """
            INSERT INTO usage_events (
                user_id, event_type, material_type, material_id
            )
            VALUES (?, 'generation', ?, ?)
            """,
            (user_id, normalized_type, int(material_id)),
        )
        return int(material_id)


def database_healthcheck() -> dict[str, int | str]:
    """Return a small status summary used by check_project.py."""
    path = initialize_database()
    with _connection() as connection:
        user_count = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        material_count = int(
            connection.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        )
        usage_event_count = int(
            connection.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        )
        payment_count = int(
            connection.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
        )
        subscription_count = int(
            connection.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0]
        )
        feedback_count = int(
            connection.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        )
        class_count = int(connection.execute("SELECT COUNT(*) FROM classes").fetchone()[0])
        objective_count = int(
            connection.execute("SELECT COUNT(*) FROM class_objectives").fetchone()[0]
        )
        class_lesson_count = int(
            connection.execute("SELECT COUNT(*) FROM class_lessons").fetchone()[0]
        )
        outcome_count = int(
            connection.execute("SELECT COUNT(*) FROM lesson_outcomes").fetchone()[0]
        )
        product_event_count = int(
            connection.execute("SELECT COUNT(*) FROM product_events").fetchone()[0]
        )
        setup_draft_count = int(
            connection.execute("SELECT COUNT(*) FROM class_setup_drafts").fetchone()[0]
        )
        class_action_item_count = int(
            connection.execute("SELECT COUNT(*) FROM class_action_items").fetchone()[0]
        )
        ai_generation_audit_count = int(
            connection.execute("SELECT COUNT(*) FROM ai_generation_audits").fetchone()[0]
        )
        material_objective_link_count = int(
            connection.execute("SELECT COUNT(*) FROM material_objective_links").fetchone()[0]
        )
        class_lesson_transition_count = int(
            connection.execute("SELECT COUNT(*) FROM class_lesson_transitions").fetchone()[0]
        )
        outcome_fact_revision_count = int(
            connection.execute("SELECT COUNT(*) FROM lesson_outcome_fact_revisions").fetchone()[0]
        )
        outcome_reminder_count = int(
            connection.execute("SELECT COUNT(*) FROM lesson_outcome_reminders").fetchone()[0]
        )
        outcome_ai_suggestion_count = int(
            connection.execute("SELECT COUNT(*) FROM lesson_outcome_ai_suggestions").fetchone()[0]
        )
        retrieval_review_item_count = int(
            connection.execute("SELECT COUNT(*) FROM retrieval_review_items").fetchone()[0]
        )
        retrieval_review_log_count = int(
            connection.execute("SELECT COUNT(*) FROM retrieval_review_logs").fetchone()[0]
        )
        proposed_class_objective_count = int(
            connection.execute("SELECT COUNT(*) FROM proposed_class_objectives").fetchone()[0]
        )
        objective_evidence_link_count = int(
            connection.execute("SELECT COUNT(*) FROM objective_evidence_links").fetchone()[0]
        )
        class_curriculum_unit_count = int(
            connection.execute("SELECT COUNT(*) FROM class_curriculum_units").fetchone()[0]
        )
        cefr_objective_mapping_count = int(
            connection.execute("SELECT COUNT(*) FROM cefr_objective_mappings").fetchone()[0]
        )
        golden_curriculum_evaluation_count = int(
            connection.execute("SELECT COUNT(*) FROM golden_curriculum_evaluations").fetchone()[0]
        )
        schema_version = int(
            connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
        )

    return {
        "path": str(path),
        "schema_version": schema_version,
        "users": user_count,
        "materials": material_count,
        "usage_events": usage_event_count,
        "payments": payment_count,
        "subscriptions": subscription_count,
        "feedback": feedback_count,
        "classes": class_count,
        "class_objectives": objective_count,
        "class_lessons": class_lesson_count,
        "lesson_outcomes": outcome_count,
        "product_events": product_event_count,
        "class_setup_drafts": setup_draft_count,
        "class_action_items": class_action_item_count,
        "ai_generation_audits": ai_generation_audit_count,
        "material_objective_links": material_objective_link_count,
        "class_lesson_transitions": class_lesson_transition_count,
        "lesson_outcome_fact_revisions": outcome_fact_revision_count,
        "lesson_outcome_reminders": outcome_reminder_count,
        "lesson_outcome_ai_suggestions": outcome_ai_suggestion_count,
        "retrieval_review_items": retrieval_review_item_count,
        "retrieval_review_logs": retrieval_review_log_count,
        "proposed_class_objectives": proposed_class_objective_count,
        "objective_evidence_links": objective_evidence_link_count,
        "class_curriculum_units": class_curriculum_unit_count,
        "cefr_objective_mappings": cefr_objective_mapping_count,
        "golden_curriculum_evaluations": golden_curriculum_evaluation_count,
    }

def _normalize_material_filter(material_type: str | None) -> str | None:
    if material_type is None:
        return None
    normalized = material_type.strip().lower()
    if normalized in {"", "all"}:
        return None
    if normalized not in _VALID_MATERIAL_TYPES:
        raise ValueError(f"Unsupported material filter: {material_type}")
    return normalized


def count_user_materials(
    *,
    telegram_user_id: int,
    material_type: str | None = None,
) -> int:
    """Count saved materials that belong to one Telegram user."""
    normalized_type = _normalize_material_filter(material_type)
    initialize_database()

    sql = """
        SELECT COUNT(*)
        FROM materials AS m
        JOIN users AS u ON u.id = m.user_id
        WHERE u.telegram_user_id = ?
    """
    parameters: list[Any] = [telegram_user_id]
    if normalized_type is not None:
        sql += " AND m.material_type = ?"
        parameters.append(normalized_type)

    with _connection() as connection:
        row = connection.execute(sql, parameters).fetchone()
        return int(row[0]) if row is not None else 0


def list_user_materials(
    *,
    telegram_user_id: int,
    material_type: str | None = None,
    limit: int = 6,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return one user's saved-material summaries, newest first."""
    if limit < 1 or limit > 50:
        raise ValueError("Library page size must be between 1 and 50.")
    if offset < 0:
        raise ValueError("Library offset cannot be negative.")

    normalized_type = _normalize_material_filter(material_type)
    initialize_database()

    sql = """
        SELECT
            m.id,
            m.material_type,
            m.subtype,
            m.title,
            m.level,
            m.topic,
            m.created_at
        FROM materials AS m
        JOIN users AS u ON u.id = m.user_id
        WHERE u.telegram_user_id = ?
    """
    parameters: list[Any] = [telegram_user_id]
    if normalized_type is not None:
        sql += " AND m.material_type = ?"
        parameters.append(normalized_type)

    sql += " ORDER BY m.created_at DESC, m.id DESC LIMIT ? OFFSET ?"
    parameters.extend((limit, offset))

    with _connection() as connection:
        rows = connection.execute(sql, parameters).fetchall()
        return [dict(row) for row in rows]


def list_class_materials(
    *, telegram_user_id: int, class_id: int, limit: int = 20
) -> list[dict[str, Any]]:
    """Return materials linked to one active, owned class."""
    if class_id < 1 or limit < 1 or limit > 50:
        raise ValueError("Invalid class-library request.")
    initialize_database()
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT m.id, m.material_type, m.subtype, m.title, m.level, m.topic,
                   m.created_at
            FROM materials AS m
            JOIN users AS u ON u.id = m.user_id
            JOIN classes AS c ON c.id = m.class_id AND c.user_id = m.user_id
            WHERE u.telegram_user_id = ? AND c.id = ? AND c.status = 'active'
            ORDER BY m.created_at DESC, m.id DESC LIMIT ?
            """,
            (telegram_user_id, class_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def get_user_material(
    *,
    telegram_user_id: int,
    material_id: int,
) -> dict[str, Any] | None:
    """Return one complete material only when it belongs to the requesting user."""
    if material_id < 1:
        return None

    initialize_database()
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT
                m.id,
                m.material_type,
                m.subtype,
                m.title,
                m.level,
                m.topic,
                m.content,
                m.metadata_json,
                m.class_id,
                m.ai_prompt_contract,
                m.ai_prompt_version,
                m.ai_prompt_hash_sha256,
                m.ai_context_hash_sha256,
                m.ai_source_record_ids_json,
                m.quality_scores_json,
                m.created_at
            FROM materials AS m
            JOIN users AS u ON u.id = m.user_id
            WHERE u.telegram_user_id = ? AND m.id = ?
            """,
            (telegram_user_id, material_id),
        ).fetchone()

    if row is None:
        return None

    material = dict(row)
    try:
        metadata = json.loads(str(material.get("metadata_json") or "{}"))
    except json.JSONDecodeError:
        metadata = {}
    material["metadata"] = metadata if isinstance(metadata, dict) else {}
    for source, target in (
        ("ai_source_record_ids_json", "ai_source_record_ids"),
        ("quality_scores_json", "quality_scores"),
    ):
        try:
            decoded = json.loads(str(material.get(source) or "{}"))
        except json.JSONDecodeError:
            decoded = {}
        material[target] = decoded if isinstance(decoded, dict) else {}
        material.pop(source, None)
    with _connection() as connection:
        links = connection.execute(
            "SELECT objective_id FROM material_objective_links "
            "WHERE material_id = ? ORDER BY objective_id",
            (material_id,),
        ).fetchall()
    material["objective_ids"] = [int(row[0]) for row in links]
    material.pop("metadata_json", None)
    return material


def delete_user_material(
    *,
    telegram_user_id: int,
    material_id: int,
) -> bool:
    """Delete one saved material only when it belongs to the requesting user."""
    if material_id < 1:
        return False

    initialize_database()
    try:
        with _connection() as connection:
            cursor = connection.execute(
                """
                DELETE FROM materials
                WHERE id = ?
                  AND user_id = (
                      SELECT id FROM users WHERE telegram_user_id = ?
                  )
                """,
                (material_id, telegram_user_id),
            )
            return cursor.rowcount == 1
    except sqlite3.IntegrityError:
        # A class lesson keeps its immutable resource for auditability.
        return False


def plan_material_as_next_lesson(
    *, telegram_user_id: int, material_id: int
) -> tuple[dict[str, Any] | None, bool]:
    """Idempotently add an owned, class-linked lesson to the class plan."""
    # Kept for Day 10 callers; Day 11's UI asks for an explicit date choice.
    from lesson_history_service import schedule_material_lesson

    result = schedule_material_lesson(
        telegram_user_id=telegram_user_id,
        material_id=material_id,
        date_choice="next_class",
    )
    lesson = result.get("lesson")
    return (
        lesson if isinstance(lesson, dict) else None,
        result.get("status") in {"planned", "replaced"},
    )



def _normalize_search_query(query: str) -> tuple[str, list[str]]:
    """Validate a library-search phrase and return normalized unique terms."""
    normalized = " ".join(str(query or "").split())
    if len(normalized) < 2:
        raise ValueError("Search text must contain at least 2 characters.")
    if len(normalized) > 80:
        raise ValueError("Search text cannot be longer than 80 characters.")

    terms: list[str] = []
    for term in normalized.casefold().split():
        if term not in terms:
            terms.append(term)
        if len(terms) == 8:
            break
    return normalized, terms


def _escape_like(value: str) -> str:
    """Escape SQLite LIKE wildcard characters so user text stays literal."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _search_where_clause(terms: list[str]) -> tuple[str, list[str]]:
    searchable_text = """
        LOWER(
            COALESCE(m.title, '') || ' ' ||
            COALESCE(m.topic, '') || ' ' ||
            COALESCE(m.level, '') || ' ' ||
            COALESCE(m.material_type, '') || ' ' ||
            COALESCE(m.subtype, '') || ' ' ||
            COALESCE(m.content, '') || ' ' ||
            COALESCE(m.metadata_json, '')
        )
    """
    conditions = [f"{searchable_text} LIKE ? ESCAPE '\\'" for _ in terms]
    parameters = [f"%{_escape_like(term)}%" for term in terms]
    return " AND ".join(conditions), parameters


def count_user_search_results(
    *,
    telegram_user_id: int,
    query: str,
) -> int:
    """Count private library materials matching every search term."""
    _, terms = _normalize_search_query(query)
    where_clause, search_parameters = _search_where_clause(terms)
    initialize_database()

    sql = f"""
        SELECT COUNT(*)
        FROM materials AS m
        JOIN users AS u ON u.id = m.user_id
        WHERE u.telegram_user_id = ?
          AND {where_clause}
    """

    with _connection() as connection:
        row = connection.execute(
            sql,
            [telegram_user_id, *search_parameters],
        ).fetchone()
        return int(row[0]) if row is not None else 0


def search_user_materials(
    *,
    telegram_user_id: int,
    query: str,
    limit: int = 6,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Search one user's library and return safe material summaries."""
    if limit < 1 or limit > 50:
        raise ValueError("Search page size must be between 1 and 50.")
    if offset < 0:
        raise ValueError("Search offset cannot be negative.")

    normalized_query, terms = _normalize_search_query(query)
    where_clause, search_parameters = _search_where_clause(terms)
    initialize_database()

    phrase = f"%{_escape_like(normalized_query.casefold())}%"
    sql = f"""
        SELECT
            m.id,
            m.material_type,
            m.subtype,
            m.title,
            m.level,
            m.topic,
            m.created_at
        FROM materials AS m
        JOIN users AS u ON u.id = m.user_id
        WHERE u.telegram_user_id = ?
          AND {where_clause}
        ORDER BY
            CASE
                WHEN LOWER(m.title) = ? THEN 0
                WHEN LOWER(m.title) LIKE ? ESCAPE '\\' THEN 1
                WHEN LOWER(COALESCE(m.topic, '')) LIKE ? ESCAPE '\\' THEN 2
                ELSE 3
            END,
            m.created_at DESC,
            m.id DESC
        LIMIT ? OFFSET ?
    """
    parameters: list[Any] = [
        telegram_user_id,
        *search_parameters,
        normalized_query.casefold(),
        phrase,
        phrase,
        limit,
        offset,
    ]

    with _connection() as connection:
        rows = connection.execute(sql, parameters).fetchall()
        return [dict(row) for row in rows]


def record_export_event(
    *,
    telegram_user: Any,
    export_format: str,
    material_id: int,
) -> int:
    """Record one successful Word or PDF export for an owned material."""
    normalized_format = str(export_format or "").strip().lower()
    event_type = {
        "word": "word_export",
        "pdf": "pdf_export",
    }.get(normalized_format)
    if event_type is None:
        raise ValueError(f"Unsupported export format: {export_format}")
    if material_id < 1:
        raise ValueError("A valid material ID is required.")

    initialize_database()
    with _connection() as connection:
        user_id = _upsert_user(connection, telegram_user)
        material = connection.execute(
            """
            SELECT material_type
            FROM materials
            WHERE id = ? AND user_id = ?
            """,
            (material_id, user_id),
        ).fetchone()
        if material is None:
            raise ValueError("The exported material does not belong to this user.")

        cursor = connection.execute(
            """
            INSERT INTO usage_events (
                user_id, event_type, material_type, material_id
            )
            VALUES (?, ?, ?, ?)
            """,
            (user_id, event_type, str(material["material_type"]), material_id),
        )
        event_id = cursor.lastrowid
        if event_id is None:
            raise RuntimeError("TeacherOS could not record the export.")
        return int(event_id)


def get_user_usage_summary(*, telegram_user_id: int) -> dict[str, Any]:
    """Return private all-time and current-UTC-day usage for one user."""
    initialize_database()
    utc_day_start = _usage_day_start_utc()

    with _connection() as connection:
        user_row = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        if user_row is None:
            return {
                "saved_materials": 0,
                "active_days": 0,
                "today": {"generations": 0, "word_exports": 0, "pdf_exports": 0},
                "all_time": {"generations": 0, "word_exports": 0, "pdf_exports": 0},
                "generation_breakdown": {
                    "lesson": 0,
                    "activity": 0,
                    "worksheet": 0,
                    "assessment": 0,
                },
            }

        user_id = int(user_row["id"])
        saved_materials = int(
            connection.execute(
                "SELECT COUNT(*) FROM materials WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]
        )

        rows = connection.execute(
            """
            SELECT
                event_type,
                COUNT(*) AS total_count,
                SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS today_count
            FROM usage_events
            WHERE user_id = ?
            GROUP BY event_type
            """,
            (utc_day_start, user_id),
        ).fetchall()

        all_time = {"generations": 0, "word_exports": 0, "pdf_exports": 0}
        today = {"generations": 0, "word_exports": 0, "pdf_exports": 0}
        key_map = {
            "generation": "generations",
            "word_export": "word_exports",
            "pdf_export": "pdf_exports",
        }
        for row in rows:
            key = key_map[str(row["event_type"])]
            all_time[key] = int(row["total_count"] or 0)
            today[key] = int(row["today_count"] or 0)

        breakdown = {
            "lesson": 0,
            "activity": 0,
            "worksheet": 0,
            "assessment": 0,
        }
        for row in connection.execute(
            """
            SELECT material_type, COUNT(*) AS count_value
            FROM usage_events
            WHERE user_id = ? AND event_type = 'generation'
            GROUP BY material_type
            """,
            (user_id,),
        ).fetchall():
            material_type = str(row["material_type"] or "")
            if material_type in breakdown:
                breakdown[material_type] = int(row["count_value"] or 0)

        active_days = int(
            connection.execute(
                """
                SELECT COUNT(DISTINCT DATE(created_at))
                FROM usage_events
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()[0]
        )

    return {
        "saved_materials": saved_materials,
        "active_days": active_days,
        "today": today,
        "all_time": all_time,
        "generation_breakdown": breakdown,
    }




def save_beta_feedback(
    *,
    telegram_user: Any,
    rating: int,
    area: str,
    message: str = "",
) -> int:
    """Save one beta rating. Only rating 1 requires a written explanation."""
    try:
        normalized_rating = int(rating)
    except (TypeError, ValueError) as exc:
        raise ValueError("Feedback rating must be a whole number from 1 to 5.") from exc
    if normalized_rating not in {1, 2, 3, 4, 5}:
        raise ValueError("Feedback rating must be between 1 and 5.")

    normalized_area = str(area or "").strip().lower()
    if normalized_area not in _VALID_FEEDBACK_AREAS:
        raise ValueError("Unknown TeacherOS feedback area.")

    normalized_message = " ".join(str(message or "").split())
    if normalized_rating == 1 and len(normalized_message) < 5:
        raise ValueError(
            "Please write a few words about what made the experience very frustrating."
        )
    if len(normalized_message) > 2000:
        raise ValueError("Feedback cannot be longer than 2,000 characters.")

    initialize_database()
    with _connection() as connection:
        user_id = _upsert_user(connection, telegram_user)
        cursor = connection.execute(
            """
            INSERT INTO feedback (user_id, rating, area, message)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, normalized_rating, normalized_area, normalized_message),
        )
        feedback_id = cursor.lastrowid
        if feedback_id is None:
            raise RuntimeError("TeacherOS could not save the feedback.")
        return int(feedback_id)


def update_beta_feedback_message(
    *,
    feedback_id: int,
    telegram_user_id: int,
    message: str,
) -> bool:
    """Attach an optional comment to a rating owned by the current Telegram user."""
    normalized_message = " ".join(str(message or "").split())
    if not normalized_message:
        raise ValueError("The optional comment cannot be empty.")
    if len(normalized_message) > 2000:
        raise ValueError("Feedback cannot be longer than 2,000 characters.")

    initialize_database()
    with _connection() as connection:
        cursor = connection.execute(
            """
            UPDATE feedback
            SET message = ?
            WHERE id = ?
              AND user_id = (
                  SELECT id FROM users WHERE telegram_user_id = ?
              )
            """,
            (normalized_message, int(feedback_id), int(telegram_user_id)),
        )
        return cursor.rowcount > 0


def get_admin_feedback_summary(*, limit: int = 8) -> dict[str, Any]:
    """Return beta feedback metrics and the latest reports for the owner dashboard."""
    safe_limit = max(1, min(int(limit), 20))
    initialize_database()
    now = datetime.now(timezone.utc)
    seven_day_start = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    with _connection() as connection:
        totals = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                AVG(rating) AS average_rating,
                SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open_count,
                SUM(CASE WHEN status = 'reviewed' THEN 1 ELSE 0 END) AS reviewed_count,
                SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) AS resolved_count,
                SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS last_7_days
            FROM feedback
            """,
            (seven_day_start,),
        ).fetchone()

        area_rows = connection.execute(
            """
            SELECT area, COUNT(*) AS count_value
            FROM feedback
            GROUP BY area
            ORDER BY count_value DESC, area ASC
            """
        ).fetchall()

        recent_rows = connection.execute(
            """
            SELECT
                f.id,
                f.rating,
                f.area,
                f.message,
                f.status,
                f.created_at,
                u.telegram_user_id,
                u.username,
                u.first_name,
                u.last_name
            FROM feedback AS f
            JOIN users AS u ON u.id = f.user_id
            ORDER BY f.created_at DESC, f.id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    return {
        "total": int(totals["total"] or 0),
        "average_rating": round(float(totals["average_rating"] or 0.0), 2),
        "open": int(totals["open_count"] or 0),
        "reviewed": int(totals["reviewed_count"] or 0),
        "resolved": int(totals["resolved_count"] or 0),
        "last_7_days": int(totals["last_7_days"] or 0),
        "area_breakdown": {
            str(row["area"]): int(row["count_value"] or 0) for row in area_rows
        },
        "recent": [dict(row) for row in recent_rows],
    }


def update_feedback_status(*, feedback_id: int, status: str) -> bool:
    """Mark one beta report as reviewed or resolved."""
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in {"reviewed", "resolved"}:
        raise ValueError("Feedback status must be reviewed or resolved.")

    timestamp_column = "reviewed_at" if normalized_status == "reviewed" else "resolved_at"
    initialize_database()
    with _connection() as connection:
        cursor = connection.execute(
            f"""
            UPDATE feedback
            SET status = ?, {timestamp_column} = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (normalized_status, int(feedback_id)),
        )
        return cursor.rowcount > 0


def get_admin_dashboard_summary() -> dict[str, Any]:
    """Return aggregate platform metrics without exposing individual teacher data."""
    initialize_database()
    now = datetime.now(timezone.utc)
    # Keep admin "today" metrics aligned with the same configured timezone used
    # for daily generation quotas (Asia/Tehran by default).
    today_start = _usage_day_start_utc()
    seven_day_start = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    thirty_day_start = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

    with _connection() as connection:
        users_row = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS new_today,
                SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS new_7_days,
                SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS new_30_days,
                SUM(CASE WHEN updated_at >= ? THEN 1 ELSE 0 END) AS active_today,
                SUM(CASE WHEN updated_at >= ? THEN 1 ELSE 0 END) AS active_7_days,
                SUM(CASE WHEN updated_at >= ? THEN 1 ELSE 0 END) AS active_30_days
            FROM users
            """,
            (
                today_start,
                seven_day_start,
                thirty_day_start,
                today_start,
                seven_day_start,
                thirty_day_start,
            ),
        ).fetchone()

        usage_rows = connection.execute(
            """
            SELECT
                event_type,
                COUNT(*) AS total_count,
                SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS today_count
            FROM usage_events
            GROUP BY event_type
            """,
            (today_start,),
        ).fetchall()

        generation_rows = connection.execute(
            """
            SELECT material_type, COUNT(*) AS count_value
            FROM usage_events
            WHERE event_type = 'generation'
            GROUP BY material_type
            """
        ).fetchall()

        saved_rows = connection.execute(
            """
            SELECT material_type, COUNT(*) AS count_value
            FROM materials
            GROUP BY material_type
            """
        ).fetchall()

    users = {
        "total": int(users_row["total"] or 0),
        "new_today": int(users_row["new_today"] or 0),
        "new_7_days": int(users_row["new_7_days"] or 0),
        "new_30_days": int(users_row["new_30_days"] or 0),
        "active_today": int(users_row["active_today"] or 0),
        "active_7_days": int(users_row["active_7_days"] or 0),
        "active_30_days": int(users_row["active_30_days"] or 0),
    }
    today = {"generations": 0, "word_exports": 0, "pdf_exports": 0}
    all_time = {"generations": 0, "word_exports": 0, "pdf_exports": 0}
    key_map = {
        "generation": "generations",
        "word_export": "word_exports",
        "pdf_export": "pdf_exports",
    }
    for row in usage_rows:
        key = key_map.get(str(row["event_type"]))
        if key is None:
            continue
        all_time[key] = int(row["total_count"] or 0)
        today[key] = int(row["today_count"] or 0)

    generation_breakdown = {
        "lesson": 0,
        "activity": 0,
        "worksheet": 0,
        "assessment": 0,
    }
    for row in generation_rows:
        material_type = str(row["material_type"] or "")
        if material_type in generation_breakdown:
            generation_breakdown[material_type] = int(row["count_value"] or 0)

    saved_breakdown = {
        "lesson": 0,
        "activity": 0,
        "worksheet": 0,
        "assessment": 0,
    }
    for row in saved_rows:
        material_type = str(row["material_type"] or "")
        if material_type in saved_breakdown:
            saved_breakdown[material_type] = int(row["count_value"] or 0)

    return {
        "users": users,
        "today": today,
        "all_time": all_time,
        "generation_breakdown": generation_breakdown,
        "saved_breakdown": saved_breakdown,
        "saved_materials": sum(saved_breakdown.values()),
    }


def get_platform_usage_summary() -> dict[str, int]:
    """Backward-compatible compact platform totals."""
    summary = get_admin_dashboard_summary()
    return {
        "total_users": int(summary["users"]["total"]),
        "active_users_today": int(summary["users"]["active_today"]),
        "generations": int(summary["all_time"]["generations"]),
        "word_exports": int(summary["all_time"]["word_exports"]),
        "pdf_exports": int(summary["all_time"]["pdf_exports"]),
    }



def create_payment_order(
    *,
    telegram_user: Any,
    purpose: str,
    amount: int,
    currency: str,
    callback_token_hash: str,
    is_sandbox: bool,
    product_code: str | None = None,
    subscription_days: int | None = None,
) -> dict[str, Any]:
    """Create a local payment order before contacting the gateway."""
    normalized_purpose = " ".join(str(purpose or "").split())
    normalized_currency = str(currency or "").strip().upper()
    normalized_hash = str(callback_token_hash or "").strip().lower()
    if not normalized_purpose:
        raise ValueError("Payment purpose cannot be empty.")
    if not isinstance(amount, int) or amount <= 0:
        raise ValueError("Payment amount must be a positive whole number.")
    if normalized_currency not in {"IRT", "IRR"}:
        raise ValueError("Payment currency must be IRT or IRR.")
    if len(normalized_hash) != 64 or any(c not in "0123456789abcdef" for c in normalized_hash):
        raise ValueError("Callback token hash must be a SHA-256 hex digest.")
    normalized_product = str(product_code or "").strip().lower() or None
    if normalized_product is not None and normalized_product not in _VALID_PAID_PLANS:
        raise ValueError("Payment product code must be pro or premium.")
    if normalized_product is None:
        normalized_days = None
    else:
        normalized_days = int(subscription_days or 0)
        if normalized_days < 1 or normalized_days > 3660:
            raise ValueError("Subscription days must be between 1 and 3660.")

    initialize_database()
    with _connection() as connection:
        user_id = _upsert_user(connection, telegram_user)
        order_id = (
            f"TOS-{user_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            f"-{secrets.token_hex(4)}"
        )
        cursor = connection.execute(
            """
            INSERT INTO payments (
                user_id, order_id, purpose, amount, currency, status,
                callback_token_hash, is_sandbox, product_code, subscription_days
            )
            VALUES (?, ?, ?, ?, ?, 'created', ?, ?, ?, ?)
            """,
            (
                user_id,
                order_id,
                normalized_purpose,
                amount,
                normalized_currency,
                normalized_hash,
                1 if is_sandbox else 0,
                normalized_product,
                normalized_days,
            ),
        )
        payment_id = cursor.lastrowid
        if payment_id is None:
            raise RuntimeError("TeacherOS could not create the payment order.")
        row = connection.execute(
            """
            SELECT p.*, u.telegram_user_id
            FROM payments AS p
            JOIN users AS u ON u.id = p.user_id
            WHERE p.id = ?
            """,
            (int(payment_id),),
        ).fetchone()
        if row is None:
            raise RuntimeError("TeacherOS could not reload the payment order.")
        return dict(row)


def set_payment_pending(
    *,
    payment_id: int,
    authority: str,
    payment_url: str,
    provider_code: int | None = None,
    provider_message: str | None = None,
) -> dict[str, Any]:
    """Attach ZarinPal authority and payment URL to a created order."""
    normalized_authority = str(authority or "").strip()
    normalized_url = str(payment_url or "").strip()
    if not normalized_authority or not normalized_url:
        raise ValueError("Gateway authority and payment URL are required.")

    initialize_database()
    with _connection() as connection:
        connection.execute(
            """
            UPDATE payments
            SET status = 'pending', authority = ?, payment_url = ?,
                provider_code = ?, provider_message = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'created'
            """,
            (
                normalized_authority,
                normalized_url,
                provider_code,
                provider_message,
                payment_id,
            ),
        )
        row = connection.execute(
            """
            SELECT p.*, u.telegram_user_id
            FROM payments AS p
            JOIN users AS u ON u.id = p.user_id
            WHERE p.id = ?
            """,
            (payment_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Payment order was not found.")
        return dict(row)


def mark_payment_failed(
    *,
    payment_id: int,
    provider_code: int | None,
    provider_message: str,
) -> dict[str, Any] | None:
    """Mark a non-paid payment as failed without overwriting a verified payment."""
    initialize_database()
    with _connection() as connection:
        connection.execute(
            """
            UPDATE payments
            SET status = 'failed', provider_code = ?, provider_message = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status != 'paid'
            """,
            (provider_code, str(provider_message or "")[:500], payment_id),
        )
        row = connection.execute(
            """
            SELECT p.*, u.telegram_user_id
            FROM payments AS p
            JOIN users AS u ON u.id = p.user_id
            WHERE p.id = ?
            """,
            (payment_id,),
        ).fetchone()
        return dict(row) if row is not None else None


def mark_payment_cancelled(
    *,
    payment_id: int,
    provider_message: str = "Payment cancelled or unsuccessful",
) -> dict[str, Any] | None:
    """Mark a returned NOK payment as cancelled unless it was already paid."""
    initialize_database()
    with _connection() as connection:
        connection.execute(
            """
            UPDATE payments
            SET status = 'cancelled', provider_message = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status != 'paid'
            """,
            (str(provider_message or "")[:500], payment_id),
        )
        row = connection.execute(
            """
            SELECT p.*, u.telegram_user_id
            FROM payments AS p
            JOIN users AS u ON u.id = p.user_id
            WHERE p.id = ?
            """,
            (payment_id,),
        ).fetchone()
        return dict(row) if row is not None else None


def _activate_paid_subscription(
    connection: sqlite3.Connection,
    *,
    payment_id: int,
) -> dict[str, Any] | None:
    """Create exactly one paid entitlement for a verified plan payment."""
    payment = connection.execute(
        """
        SELECT id, user_id, status, product_code, subscription_days, is_sandbox
        FROM payments
        WHERE id = ?
        """,
        (payment_id,),
    ).fetchone()
    if payment is None or str(payment["status"]) != "paid":
        return None

    plan_code = str(payment["product_code"] or "").strip().lower()
    if plan_code not in _VALID_PAID_PLANS:
        return None
    days = int(payment["subscription_days"] or 0)
    if days < 1:
        return None

    existing = connection.execute(
        "SELECT * FROM subscriptions WHERE source_payment_id = ?",
        (payment_id,),
    ).fetchone()
    if existing is not None:
        return dict(existing)

    now = datetime.now(timezone.utc)
    latest = connection.execute(
        """
        SELECT MAX(expires_at) AS latest_expiry
        FROM subscriptions
        WHERE user_id = ? AND plan_code = ? AND status = 'active'
          AND is_sandbox = ? AND expires_at > ?
        """,
        (
            int(payment["user_id"]),
            plan_code,
            int(payment["is_sandbox"] or 0),
            _utc_text(now),
        ),
    ).fetchone()
    latest_expiry = _parse_utc_text(latest["latest_expiry"] if latest else None)
    base = latest_expiry if latest_expiry is not None and latest_expiry > now else now
    expires_at = base + timedelta(days=days)

    connection.execute(
        """
        INSERT OR IGNORE INTO subscriptions (
            user_id, plan_code, source, source_payment_id,
            starts_at, expires_at, status, is_sandbox, note
        )
        VALUES (?, ?, 'payment', ?, ?, ?, 'active', ?, ?)
        """,
        (
            int(payment["user_id"]),
            plan_code,
            payment_id,
            _utc_text(now),
            _utc_text(expires_at),
            int(payment["is_sandbox"] or 0),
            f"Activated by verified ZarinPal payment #{payment_id}",
        ),
    )
    row = connection.execute(
        "SELECT * FROM subscriptions WHERE source_payment_id = ?",
        (payment_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _payment_with_subscription(
    connection: sqlite3.Connection,
    *,
    payment_id: int | None = None,
    callback_token_hash: str | None = None,
    telegram_user_id: int | None = None,
) -> dict[str, Any] | None:
    conditions: list[str] = []
    parameters: list[Any] = []
    if payment_id is not None:
        conditions.append("p.id = ?")
        parameters.append(payment_id)
    if callback_token_hash is not None:
        conditions.append("p.callback_token_hash = ?")
        parameters.append(callback_token_hash)
    if telegram_user_id is not None:
        conditions.append("u.telegram_user_id = ?")
        parameters.append(telegram_user_id)
    if not conditions:
        raise ValueError("A payment lookup condition is required.")

    row = connection.execute(
        f"""
        SELECT
            p.*,
            u.telegram_user_id,
            s.plan_code AS activated_plan,
            s.starts_at AS subscription_starts_at,
            s.expires_at AS subscription_expires_at,
            s.status AS subscription_status
        FROM payments AS p
        JOIN users AS u ON u.id = p.user_id
        LEFT JOIN subscriptions AS s ON s.source_payment_id = p.id
        WHERE {' AND '.join(conditions)}
        """,
        parameters,
    ).fetchone()
    return dict(row) if row is not None else None


def mark_payment_paid(
    *,
    payment_id: int,
    authority: str,
    ref_id: str | int | None,
    card_pan: str | None,
    card_hash: str | None,
    provider_code: int,
    provider_message: str,
) -> dict[str, Any]:
    """Idempotently verify a payment and activate its subscription in one transaction."""
    normalized_authority = str(authority or "").strip()
    normalized_ref = str(ref_id).strip() if ref_id is not None else None
    initialize_database()
    with _connection() as connection:
        existing = connection.execute(
            "SELECT status, authority FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        if existing is None:
            raise RuntimeError("Payment order was not found.")
        if str(existing["authority"] or "") != normalized_authority:
            raise ValueError("Payment authority does not match the stored order.")

        if str(existing["status"]) != "paid":
            connection.execute(
                """
                UPDATE payments
                SET status = 'paid', ref_id = COALESCE(ref_id, ?),
                    card_pan = COALESCE(card_pan, ?),
                    card_hash = COALESCE(card_hash, ?),
                    provider_code = ?, provider_message = ?,
                    verified_at = COALESCE(verified_at, CURRENT_TIMESTAMP),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status != 'paid'
                """,
                (
                    normalized_ref,
                    str(card_pan or "")[:64] or None,
                    str(card_hash or "")[:128] or None,
                    provider_code,
                    str(provider_message or "")[:500],
                    payment_id,
                ),
            )

        _activate_paid_subscription(connection, payment_id=payment_id)
        row = _payment_with_subscription(connection, payment_id=payment_id)
        if row is None:
            raise RuntimeError("Payment order disappeared after verification.")
        return row


def get_payment_by_callback_token_hash(callback_token_hash: str) -> dict[str, Any] | None:
    """Find a payment using the SHA-256 hash of its unguessable callback token."""
    initialize_database()
    with _connection() as connection:
        return _payment_with_subscription(
            connection,
            callback_token_hash=str(callback_token_hash or "").strip().lower(),
        )


def get_user_payment(*, telegram_user_id: int, payment_id: int) -> dict[str, Any] | None:
    """Return one payment only when it belongs to the requesting Telegram user."""
    initialize_database()
    with _connection() as connection:
        return _payment_with_subscription(
            connection,
            payment_id=payment_id,
            telegram_user_id=telegram_user_id,
        )


def list_user_payments(*, telegram_user_id: int, limit: int = 5) -> list[dict[str, Any]]:
    """Return one user's newest payment orders without exposing other users."""
    if limit < 1 or limit > 20:
        raise ValueError("Payment history limit must be between 1 and 20.")
    initialize_database()
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT
                p.*,
                s.plan_code AS activated_plan,
                s.expires_at AS subscription_expires_at,
                s.status AS subscription_status
            FROM payments AS p
            JOIN users AS u ON u.id = p.user_id
            LEFT JOIN subscriptions AS s ON s.source_payment_id = p.id
            WHERE u.telegram_user_id = ?
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT ?
            """,
            (telegram_user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def get_admin_payment_summary() -> dict[str, Any]:
    """Return aggregate verified-payment metrics for the owner dashboard."""
    initialize_database()
    today_start = _usage_day_start_utc()
    with _connection() as connection:
        status_rows = connection.execute(
            """
            SELECT is_sandbox, status, COUNT(*) AS count_value,
                   COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) AS paid_amount
            FROM payments
            GROUP BY is_sandbox, status
            """
        ).fetchall()
        today_rows = connection.execute(
            """
            SELECT is_sandbox, COUNT(*) AS paid_count, COALESCE(SUM(amount), 0) AS paid_amount
            FROM payments
            WHERE status = 'paid' AND verified_at >= ?
            GROUP BY is_sandbox
            """,
            (today_start,),
        ).fetchall()

    def empty_bucket() -> dict[str, int]:
        return {
            "created": 0,
            "pending": 0,
            "paid": 0,
            "failed": 0,
            "cancelled": 0,
            "paid_amount": 0,
            "paid_today": 0,
            "paid_amount_today": 0,
        }

    result = {"live": empty_bucket(), "sandbox": empty_bucket(), "currency": "IRT"}
    for row in status_rows:
        bucket = result["sandbox" if int(row["is_sandbox"]) else "live"]
        status = str(row["status"])
        if status in bucket:
            bucket[status] = int(row["count_value"] or 0)
        if status == "paid":
            bucket["paid_amount"] = int(row["paid_amount"] or 0)
    for row in today_rows:
        bucket = result["sandbox" if int(row["is_sandbox"]) else "live"]
        bucket["paid_today"] = int(row["paid_count"] or 0)
        bucket["paid_amount_today"] = int(row["paid_amount"] or 0)
    return result


def record_payment_provider_note(
    *,
    payment_id: int,
    provider_code: int | None,
    provider_message: str,
) -> dict[str, Any] | None:
    """Store a gateway error while preserving the current payment status for retry."""
    initialize_database()
    with _connection() as connection:
        connection.execute(
            """
            UPDATE payments
            SET provider_code = ?, provider_message = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (provider_code, str(provider_message or "")[:500], payment_id),
        )
        row = connection.execute(
            """
            SELECT p.*, u.telegram_user_id
            FROM payments AS p
            JOIN users AS u ON u.id = p.user_id
            WHERE p.id = ?
            """,
            (payment_id,),
        ).fetchone()
        return dict(row) if row is not None else None


def _active_subscription_rows(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    include_sandbox: bool,
) -> list[sqlite3.Row]:
    now_text = _utc_text(datetime.now(timezone.utc))
    sandbox_clause = "" if include_sandbox else " AND is_sandbox = 0"
    return connection.execute(
        f"""
        SELECT *
        FROM subscriptions
        WHERE user_id = ? AND status = 'active'
          AND starts_at <= ? AND expires_at > ?
          {sandbox_clause}
        ORDER BY
            CASE plan_code WHEN 'premium' THEN 2 WHEN 'pro' THEN 1 ELSE 0 END DESC,
            expires_at DESC,
            id DESC
        """,
        (user_id, now_text, now_text),
    ).fetchall()


def get_user_entitlement(
    *,
    telegram_user_id: int,
    include_sandbox: bool | None = None,
) -> dict[str, Any]:
    """Return the effective plan and generation quota for one Telegram user."""
    initialize_database()
    allow_sandbox = ZARINPAL_SANDBOX if include_sandbox is None else bool(include_sandbox)
    day_start = _usage_day_start_utc()

    with _connection() as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        if user is None:
            used_today = 0
            selected: sqlite3.Row | None = None
        else:
            user_id = int(user["id"])
            selected_rows = _active_subscription_rows(
                connection,
                user_id=user_id,
                include_sandbox=allow_sandbox,
            )
            selected = selected_rows[0] if selected_rows else None
            used_today = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM usage_events
                    WHERE user_id = ? AND event_type = 'generation' AND created_at >= ?
                    """,
                    (user_id, day_start),
                ).fetchone()[0]
            )

    plan_code = str(selected["plan_code"]) if selected is not None else "free"
    daily_limit = PLAN_DAILY_LIMITS[plan_code]
    remaining = None if daily_limit is None else max(0, daily_limit - used_today)
    return {
        "plan_code": plan_code,
        "plan_name": PLAN_NAMES[plan_code],
        "daily_limit": daily_limit,
        "used_today": used_today,
        "remaining": remaining,
        "allowed": daily_limit is None or used_today < daily_limit,
        "priority": plan_code == "premium",
        "starts_at": selected["starts_at"] if selected is not None else None,
        "expires_at": selected["expires_at"] if selected is not None else None,
        "source": selected["source"] if selected is not None else "free",
        "is_sandbox": bool(selected["is_sandbox"]) if selected is not None else False,
        "usage_timezone": USAGE_TIMEZONE,
    }


def record_general_generation(*, telegram_user: Any, metadata: Mapping[str, Any] | None = None) -> int:
    """Count one successful general TeacherOS AI response that has no material record."""
    initialize_database()
    metadata_json = json.dumps(dict(metadata or {}), ensure_ascii=False, sort_keys=True)
    with _connection() as connection:
        user_id = _upsert_user(connection, telegram_user)
        cursor = connection.execute(
            """
            INSERT INTO usage_events (user_id, event_type, material_type, material_id, metadata_json)
            VALUES (?, 'generation', NULL, NULL, ?)
            """,
            (user_id, metadata_json),
        )
        event_id = cursor.lastrowid
        if event_id is None:
            raise RuntimeError("TeacherOS could not record the AI generation.")
        return int(event_id)


def grant_manual_subscription(
    *,
    telegram_user_id: int,
    plan_code: str,
    days: int,
    granted_by_telegram_id: int,
    note: str | None = None,
) -> dict[str, Any]:
    """Owner-only database operation for trials, support, and early testers."""
    normalized_plan = str(plan_code or "").strip().lower()
    if normalized_plan not in _VALID_PAID_PLANS:
        raise ValueError("Plan must be pro or premium.")
    if days < 1 or days > 3660:
        raise ValueError("Days must be between 1 and 3660.")

    initialize_database()
    with _connection() as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        if user is None:
            raise ValueError("That Telegram user has not started TeacherOS yet.")

        now = datetime.now(timezone.utc)
        latest = connection.execute(
            """
            SELECT MAX(expires_at) AS latest_expiry
            FROM subscriptions
            WHERE user_id = ? AND plan_code = ? AND status = 'active'
              AND is_sandbox = 0 AND expires_at > ?
            """,
            (int(user["id"]), normalized_plan, _utc_text(now)),
        ).fetchone()
        latest_expiry = _parse_utc_text(latest["latest_expiry"] if latest else None)
        base = latest_expiry if latest_expiry is not None and latest_expiry > now else now
        expiry = base + timedelta(days=days)
        cursor = connection.execute(
            """
            INSERT INTO subscriptions (
                user_id, plan_code, source, starts_at, expires_at, status,
                is_sandbox, granted_by_telegram_id, note
            )
            VALUES (?, ?, 'manual', ?, ?, 'active', 0, ?, ?)
            """,
            (
                int(user["id"]),
                normalized_plan,
                _utc_text(now),
                _utc_text(expiry),
                granted_by_telegram_id,
                str(note or "Manual owner grant")[:500],
            ),
        )
        subscription_id = cursor.lastrowid
        row = connection.execute(
            "SELECT * FROM subscriptions WHERE id = ?",
            (subscription_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("TeacherOS could not create the subscription.")
        return dict(row)


def revoke_user_subscriptions(*, telegram_user_id: int) -> int:
    """Revoke all currently active paid entitlements for one registered user."""
    initialize_database()
    with _connection() as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        if user is None:
            return 0
        cursor = connection.execute(
            """
            UPDATE subscriptions
            SET status = 'revoked', updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND status = 'active'
            """,
            (int(user["id"]),),
        )
        return int(cursor.rowcount)


def get_admin_subscription_summary() -> dict[str, Any]:
    """Return aggregate plan metrics without exposing teacher identities."""
    initialize_database()
    now = datetime.now(timezone.utc)
    now_text = _utc_text(now)
    seven_days_text = _utc_text(now + timedelta(days=7))
    with _connection() as connection:
        total_users = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        rows = connection.execute(
            """
            SELECT user_id, plan_code, source, is_sandbox, expires_at
            FROM subscriptions
            WHERE status = 'active' AND starts_at <= ? AND expires_at > ?
            ORDER BY user_id,
                CASE plan_code WHEN 'premium' THEN 2 WHEN 'pro' THEN 1 ELSE 0 END DESC,
                expires_at DESC
            """,
            (now_text, now_text),
        ).fetchall()
        total_activations = int(
            connection.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0]
        )
        revoked = int(
            connection.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE status = 'revoked'"
            ).fetchone()[0]
        )
        expiring = int(
            connection.execute(
                """
                SELECT COUNT(DISTINCT user_id)
                FROM subscriptions
                WHERE status = 'active' AND expires_at > ? AND expires_at <= ?
                """,
                (now_text, seven_days_text),
            ).fetchone()[0]
        )

    best_by_user: dict[int, sqlite3.Row] = {}
    for row in rows:
        user_id = int(row["user_id"])
        current = best_by_user.get(user_id)
        if current is None or _PLAN_RANK[str(row["plan_code"])] > _PLAN_RANK[str(current["plan_code"])]:
            best_by_user[user_id] = row

    active = {"pro": 0, "premium": 0}
    live = {"pro": 0, "premium": 0}
    sandbox = {"pro": 0, "premium": 0}
    manual = {"pro": 0, "premium": 0}
    for row in best_by_user.values():
        plan = str(row["plan_code"])
        active[plan] += 1
        if str(row["source"]) == "manual":
            manual[plan] += 1
        elif int(row["is_sandbox"] or 0):
            sandbox[plan] += 1
        else:
            live[plan] += 1

    paid_users = len(best_by_user)
    return {
        "registered_users": total_users,
        "active": {"free": max(0, total_users - paid_users), **active},
        "live": live,
        "sandbox": sandbox,
        "manual": manual,
        "expiring_7_days": expiring,
        "total_activations": total_activations,
        "revoked": revoked,
    }
