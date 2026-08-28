from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 9
_UTC_NOW = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"


def apply_schema_v9(connection: sqlite3.Connection) -> None:
    """Add privacy-safe AI request provenance and operational telemetry."""
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS ai_generation_audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE CHECK (
                length(trim(request_id)) BETWEEN 8 AND 100
            ),
            user_id INTEGER NOT NULL,
            class_id INTEGER,
            feature TEXT NOT NULL CHECK (
                feature IN (
                    'general_chat', 'lesson', 'activity',
                    'worksheet', 'assessment'
                )
            ),
            prompt_contract TEXT NOT NULL CHECK (
                length(trim(prompt_contract)) BETWEEN 1 AND 80
            ),
            prompt_version TEXT NOT NULL CHECK (
                length(trim(prompt_version)) BETWEEN 1 AND 40
            ),
            prompt_hash_sha256 TEXT NOT NULL CHECK (
                length(prompt_hash_sha256) = 64
            ),
            context_hash_sha256 TEXT NOT NULL CHECK (
                length(context_hash_sha256) = 64
            ),
            source_record_ids_json TEXT NOT NULL DEFAULT '{{}}',
            provider TEXT NOT NULL CHECK (length(trim(provider)) BETWEEN 1 AND 40),
            model TEXT NOT NULL CHECK (length(trim(model)) BETWEEN 1 AND 160),
            status TEXT NOT NULL DEFAULT 'started' CHECK (
                status IN (
                    'started', 'succeeded', 'safe_failure',
                    'provider_failure', 'timeout'
                )
            ),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 3),
            repair_attempted INTEGER NOT NULL DEFAULT 0 CHECK (repair_attempted IN (0, 1)),
            latency_ms INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),
            input_tokens INTEGER CHECK (input_tokens IS NULL OR input_tokens >= 0),
            output_tokens INTEGER CHECK (output_tokens IS NULL OR output_tokens >= 0),
            cost_microusd INTEGER CHECK (cost_microusd IS NULL OR cost_microusd >= 0),
            error_code TEXT CHECK (
                error_code IS NULL OR length(trim(error_code)) BETWEEN 1 AND 80
            ),
            created_at TEXT NOT NULL DEFAULT {_UTC_NOW},
            completed_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_audits_owner_created "
        "ON ai_generation_audits(user_id, created_at DESC, id DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_audits_status_created "
        "ON ai_generation_audits(status, created_at DESC, id DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_audits_class_created "
        "ON ai_generation_audits(user_id, class_id, created_at DESC, id DESC)"
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_ai_audits_class_owner_insert
        BEFORE INSERT ON ai_generation_audits
        WHEN NEW.class_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM classes WHERE id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT, 'ownership mismatch'); END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_ai_audits_class_owner_update
        BEFORE UPDATE OF class_id, user_id ON ai_generation_audits
        WHEN NEW.class_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM classes WHERE id = NEW.class_id AND user_id = NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT, 'ownership mismatch'); END
        """
    )
    connection.execute(
        "INSERT OR IGNORE INTO schema_versions(version, applied_at) "
        f"VALUES (?, {_UTC_NOW})",
        (SCHEMA_VERSION,),
    )
