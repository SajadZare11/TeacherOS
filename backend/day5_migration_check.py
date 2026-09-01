from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from database import initialize_database
from day22_migration import SCHEMA_VERSION
from feature_flags import FEATURE_ENV_VARS, feature_flag_snapshot, quick_create_is_default
from pdf_document import create_pdf_export
from word_document import create_word_export


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEGACY_TABLES = (
    "users",
    "materials",
    "usage_events",
    "payments",
    "subscriptions",
    "feedback",
)
NEW_TABLES = (
    "classes",
    "class_objectives",
    "class_lessons",
    "lesson_outcomes",
    "product_events",
    "class_setup_drafts",
    "class_action_items",
    "ai_generation_audits",
    "material_objective_links",
    "class_lesson_transitions",
    "lesson_outcome_fact_revisions",
    "lesson_outcome_reminders",
    "lesson_outcome_ai_suggestions",
    "next_lesson_recommendations",
    "next_lesson_recommendation_sources",
    "next_lesson_plans",
    "next_lesson_plan_sources",
    "evidence_batches",
    "evidence_items",
    "evidence_analysis_results",
    "writing_feedback_records",
    "analysis_followup_actions",
    "material_evidence_links",
    "material_differentiations",
    "material_adaptations",
    "retrieval_review_items",
    "retrieval_review_logs",
    "proposed_class_objectives",
    "objective_evidence_links",
    "class_curriculum_units",
    "cefr_objective_mappings",
    "golden_curriculum_evaluations",
)

_POST_LEGACY_MATERIAL_COLUMNS = {
    "class_id", "ai_prompt_contract", "ai_prompt_version",
    "ai_prompt_hash_sha256", "ai_context_hash_sha256",
    "ai_source_record_ids_json", "quality_scores_json",
}


@contextmanager
def _connect(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _counts(connection: sqlite3.Connection, tables: tuple[str, ...]) -> dict[str, int]:
    return {
        table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in tables
    }


def _schema_fingerprint(connection: sqlite3.Connection) -> str:
    objects = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()
    payload = [tuple(row) for row in objects]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _legacy_data_fingerprint(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    for table in LEGACY_TABLES:
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
        legacy_columns = [
            column for column in columns if column not in _POST_LEGACY_MATERIAL_COLUMNS
        ]
        order = "id" if "id" in legacy_columns else "rowid"
        rows = connection.execute(
            f"SELECT {', '.join(legacy_columns)} FROM {table} ORDER BY {order}"
        ).fetchall()
        digest.update(table.encode("utf-8"))
        digest.update(json.dumps([tuple(row) for row in rows], default=str).encode("utf-8"))
    return digest.hexdigest()


def _strip_v6_to_legacy_fixture(path: Path) -> None:
    """Convert a new empty temp DB into the exact additive pre-v6 shape."""
    with _connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        for trigger in (
            "trg_materials_class_owner_insert",
            "trg_materials_class_owner_update",
            "trg_lessons_material_owner_insert",
            "trg_lessons_material_owner_update",
            "trg_product_events_owner_insert",
            "trg_product_events_owner_update",
            "trg_ai_audits_class_owner_insert",
            "trg_ai_audits_class_owner_update",
            "trg_material_objectives_owner_insert",
            "trg_material_objectives_owner_update",
            "trg_lesson_material_class_insert_v11",
            "trg_lesson_legacy_status_insert_v11",
            "trg_lesson_material_immutable_v11",
            "trg_lesson_lifecycle_transition_v11",
            "trg_lesson_material_delete_guard_v11",
            "trg_material_lesson_link_immutable_v11",
            "trg_outcome_requires_taught_insert_v11",
            "trg_outcome_requires_taught_update_v11",
            "trg_lesson_transition_owner_v11",
            "trg_lesson_transition_immutable_update_v11",
            "trg_outcome_active_unique_insert_v12",
            "trg_outcome_active_unique_update_v12",
            "trg_outcome_three_tap_complete_insert_v12",
            "trg_outcome_three_tap_complete_update_v12",
            "trg_outcome_revision_owner_v12",
            "trg_outcome_revision_immutable_update_v12",
            "trg_outcome_reminder_owner_insert_v12",
            "trg_outcome_reminder_owner_update_v12",
            "trg_outcome_suggestion_owner_v12",
            "trg_outcome_completes_reminder_insert_v12",
            "trg_outcome_completes_reminder_update_v12",
            "trg_next_lesson_owner_insert_v13",
            "trg_next_lesson_owner_update_v13",
            "trg_next_lesson_source_owner_insert_v13",
            "trg_next_lesson_source_owner_update_v13",
            "trg_next_lesson_plan_owner_insert_v13",
            "trg_next_lesson_plan_owner_update_v13",
            "trg_next_lesson_plan_source_owner_insert_v13",
            "trg_next_lesson_plan_source_owner_update_v13",
            "trg_next_lesson_immutable_saved_update_v13",
            "trg_next_lesson_plan_immutable_update_v13",
            "trg_next_lesson_plan_source_immutable_update_v13",
            "trg_evidence_batch_owner_insert_v15",
            "trg_evidence_batch_owner_update_v15",
            "trg_evidence_item_owner_insert_v15",
            "trg_evidence_item_owner_update_v15",
            "trg_evidence_item_count_insert_v15",
            "trg_evidence_item_count_update_v15",
            "trg_evidence_item_count_delete_v15",
            "trg_evidence_analysis_owner_insert_v16",
            "trg_evidence_analysis_owner_update_v16",
            "trg_evidence_analysis_approved_immutable_v16",
            "trg_writing_feedback_class_owner_v17",
            "trg_writing_feedback_evidence_owner_v17",
            "trg_analysis_followup_owner_v18",
            "trg_analysis_followup_approved_check_v18",
            "trg_material_diff_owner_v19",
            "trg_material_adap_owner_v19",
        ):
            connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        for index in (
            "idx_materials_id_user",
            "idx_materials_user_class_created",
            "idx_evidence_batches_owner",
            "idx_evidence_batches_uuid",
            "idx_evidence_items_batch",
            "idx_evidence_items_class",
            "idx_evidence_analysis_batch",
            "idx_evidence_analysis_class",
            "idx_evidence_analysis_uuid",
            "idx_writing_feedback_user_created",
            "idx_writing_feedback_class",
            "idx_writing_feedback_uuid",
            "idx_writing_feedback_evidence",
            "idx_analysis_followup_user_class",
            "idx_analysis_followup_analysis",
            "idx_analysis_followup_uuid",
            "idx_material_evidence_analysis",
            "idx_material_evidence_material",
            "idx_material_diff_source",
            "idx_material_diff_user",
            "idx_material_adap_source",
            "idx_material_adap_user",
        ):
            connection.execute(f"DROP INDEX IF EXISTS {index}")
        for table in (
            "golden_curriculum_evaluations",
            "cefr_objective_mappings",
            "class_curriculum_units",
            "objective_evidence_links",
            "proposed_class_objectives",
            "retrieval_review_logs",
            "retrieval_review_items",
            "material_adaptations",
            "material_differentiations",
            "material_evidence_links",
            "analysis_followup_actions",
            "writing_feedback_records",
            "evidence_analysis_results",
            "evidence_items",
            "evidence_batches",
            "next_lesson_plan_sources",
            "next_lesson_plans",
            "next_lesson_recommendation_sources",
            "next_lesson_recommendations",
            "lesson_outcome_ai_suggestions",
            "lesson_outcome_reminders",
            "lesson_outcome_fact_revisions",
            "class_lesson_transitions",
            "material_objective_links",
            "ai_generation_audits",
            "class_action_items",
            "class_setup_drafts",
            "product_events",
            "lesson_outcomes",
            "class_lessons",
            "class_objectives",
            "classes",
        ):
            connection.execute(f"DROP TABLE IF EXISTS {table}")
        for column in _POST_LEGACY_MATERIAL_COLUMNS:
            if column in {str(row[1]) for row in connection.execute("PRAGMA table_info(materials)")}:
                connection.execute(f"ALTER TABLE materials DROP COLUMN {column}")
        connection.execute("DELETE FROM schema_versions WHERE version >= 6")
        connection.commit()


def _build_legacy_fixture(path: Path, *, populated: bool) -> None:
    initialize_database(path)
    _strip_v6_to_legacy_fixture(path)
    if not populated:
        return
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO users (
                telegram_user_id, username, first_name, last_name, language_code
            ) VALUES (51001, 'migration_teacher', 'Migration', 'Teacher', 'en')
            """
        )
        user_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            """
            INSERT INTO materials (
                user_id, material_type, subtype, title, level, topic,
                content, metadata_json
            ) VALUES (?, 'lesson', 'baseline', 'Legacy migration lesson', 'B1',
                      'Travel', '# Legacy lesson\n\nANSWER KEY\n1. Verified', '{}')
            """,
            (user_id,),
        )
        material_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            """
            INSERT INTO usage_events (user_id, event_type, material_type, material_id)
            VALUES (?, 'generation', 'lesson', ?)
            """,
            (user_id, material_id),
        )
        connection.execute(
            """
            INSERT INTO payments (
                user_id, order_id, purpose, amount, currency, status,
                callback_token_hash, is_sandbox, product_code, subscription_days
            ) VALUES (?, 'MIGRATION-ORDER', 'Migration verification', 149000, 'IRT',
                      'paid', 'migration-token-hash', 1, 'pro', 30)
            """,
            (user_id,),
        )
        payment_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            """
            INSERT INTO subscriptions (
                user_id, plan_code, source, source_payment_id, starts_at,
                expires_at, status, is_sandbox
            ) VALUES (?, 'pro', 'payment', ?, '2026-08-01T00:00:00Z',
                      '2026-09-01T00:00:00Z', 'active', 1)
            """,
            (user_id, payment_id),
        )
        connection.execute(
            """
            INSERT INTO feedback (user_id, rating, area, message)
            VALUES (?, 5, 'lesson', 'Migration verification feedback')
            """,
            (user_id,),
        )


@contextmanager
def _flags_disabled() -> Iterator[None]:
    previous = {env_name: os.environ.get(env_name) for env_name in FEATURE_ENV_VARS.values()}
    try:
        for env_name in FEATURE_ENV_VARS.values():
            os.environ[env_name] = "false"
        yield
    finally:
        for env_name, value in previous.items():
            if value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = value


def _verify_exports(connection: sqlite3.Connection) -> dict[str, bool]:
    row = connection.execute("SELECT * FROM materials ORDER BY id LIMIT 1").fetchone()
    if row is None:
        return {"word": True, "pdf": True, "not_applicable": True}
    material = dict(row)
    word_stream, _ = create_word_export(material)
    pdf_stream, _ = create_pdf_export(material)
    word_bytes = word_stream.read()
    pdf_bytes = pdf_stream.read()
    return {
        "word": word_bytes.startswith(b"PK"),
        "pdf": pdf_bytes.startswith(b"%PDF-"),
        "not_applicable": False,
    }


def verify_database(path: Path, label: str) -> dict[str, Any]:
    with _connect(path) as connection:
        before_counts = _counts(connection, LEGACY_TABLES)
        before_data = _legacy_data_fingerprint(connection)
        before_columns = {
            table: [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
            for table in LEGACY_TABLES
        }

    initialize_database(path)
    initialize_database(path)

    with _connect(path) as connection:
        after_counts = _counts(connection, LEGACY_TABLES)
        after_data = _legacy_data_fingerprint(connection)
        after_columns = {
            table: [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
            for table in LEGACY_TABLES
        }
        new_counts = _counts(connection, NEW_TABLES)
        version = int(connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0])
        foreign_key_errors = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
        exports = _verify_exports(connection)
        schema_fingerprint = _schema_fingerprint(connection)

    duplicate_columns = {
        table: len(columns) != len(set(columns)) for table, columns in after_columns.items()
    }
    missing_legacy_columns = {
        table: sorted(set(before_columns[table]) - set(after_columns[table]))
        for table in LEGACY_TABLES
    }
    passed = all(
        (
            before_counts == after_counts,
            before_data == after_data,
            version == SCHEMA_VERSION,
            not foreign_key_errors,
            not any(duplicate_columns.values()),
            not any(missing_legacy_columns.values()),
            exports["word"],
            exports["pdf"],
        )
    )
    return {
        "label": label,
        "passed": passed,
        "schema_version": version,
        "legacy_counts_before": before_counts,
        "legacy_counts_after": after_counts,
        "new_table_counts": new_counts,
        "legacy_data_preserved": before_data == after_data,
        "duplicate_columns": duplicate_columns,
        "missing_legacy_columns": missing_legacy_columns,
        "foreign_key_error_count": len(foreign_key_errors),
        "exports": exports,
        "schema_fingerprint_sha256": schema_fingerprint,
    }


def run_checks(real_copy: Path | None = None) -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="teacheros-day5-migration-") as temp_dir:
        temp_root = Path(temp_dir)
        empty_path = temp_root / "empty.db"
        initialize_database(empty_path)
        scenarios.append(verify_database(empty_path, "empty"))

        legacy_path = temp_root / "legacy-v5.db"
        _build_legacy_fixture(legacy_path, populated=False)
        scenarios.append(verify_database(legacy_path, "legacy-v5"))

        populated_path = temp_root / "populated-v5.db"
        _build_legacy_fixture(populated_path, populated=True)
        scenarios.append(verify_database(populated_path, "populated-v5"))

        if real_copy is not None:
            source = real_copy.expanduser().resolve()
            if not source.is_file():
                raise FileNotFoundError(f"Real-schema copy not found: {source}")
            copied_path = temp_root / "real-populated-copy.db"
            shutil.copy2(source, copied_path)
            scenarios.append(verify_database(copied_path, "real-populated-copy"))

    with _flags_disabled():
        flag_state = feature_flag_snapshot()
        rollback = {
            "all_surfaces_disabled": all(
                not state["effective"] for state in flag_state.values()
            ),
            "quick_create_default": quick_create_is_default(),
            "strategy": "additive_schema_feature_flags_off",
        }

    passed = all(scenario["passed"] for scenario in scenarios) and all(
        (rollback["all_surfaces_disabled"], rollback["quick_create_default"])
    )
    return {
        "day": 5,
        "passed": passed,
        "schema_version": SCHEMA_VERSION,
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "rollback": rollback,
        "privacy": "Counts and schema hashes only; no user content or identifiers.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the TeacherOS Day 5 migration twice.")
    parser.add_argument(
        "--real-copy",
        type=Path,
        help="Optional consistent older-schema backup to migrate only inside a temporary copy.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "day05" / "migration_report.json",
    )
    args = parser.parse_args()
    report = run_checks(args.real_copy)
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
