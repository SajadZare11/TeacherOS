# TeacherOS Day 26: System Hardening, Reliability, Backups, and Observability

## 1. Executive Summary & Outcome
Day 26 establishes production-grade hardening, reliability protections, automated database backup rotation, verified disaster restore drills, and low-overhead system observability across TeacherOS. The bot fails visibly and recoverably without losing teacher choices or exposing sensitive data.

---

## 2. Key Architecture & Features

### A. Structured Operational Error Categories ([`backend/resilience.py`](file:///e:/0/Work/Website/TeacherOS/Pycharm%20ode/backend/resilience.py))
- **`TeacherOSError`**: Root structured exception containing subsystem labels and recommended operational actions.
- **`ProviderTimeoutError`**: Raised on AI provider latency spikes; triggers bounded exponential backoff with jitter.
- **`ProviderInvalidResponseError`**: Raised on empty/malformed responses; triggers structured regeneration.
- **`DatabaseLockError`**: Raised on SQLite busy timeouts; retries safely with backoff and jitter.
- **`DiskSpaceLowError`**: Raised when server storage capacity drops below safe operational threshold (100MB).
- **`ExportFailureError`**: Raised on Word/PDF rendering issues; provides actionable debugging without exposing customer text.

### B. Bounded Retry with Exponential Backoff & Jitter
- Synchronous and asynchronous retry wrappers (`execute_with_retry` and `execute_with_retry_async`) protecting network, database, and gateway calls against transient blips.

### C. Sensitive Data Redaction
- Automatic sanitization in logs and telemetry for:
  - OpenRouter API keys (`sk-or-v1-...` $\to$ `sk-or-v1-[REDACTED]`)
  - Telegram Bot tokens (`[BOT_TOKEN_REDACTED]`)
  - Bearer tokens (`Bearer [REDACTED]`)
  - Email addresses (`user@domain.com` $\to$ `u***@domain.com`)
  - Payment card PANs (`4111 1111 1111 1234` $\to$ `****-****-****-1234`)

### D. Automated SQLite Backups, Rotation & Restore Drill ([`backend/backup_service.py`](file:///e:/0/Work/Website/TeacherOS/Pycharm%20ode/backend/backup_service.py))
- Online SQLite backup using `source.backup(target)` with `PRAGMA busy_timeout = 15000` (safe for WAL mode).
- Automatic backup rotation keeping the newest 7 backups and deleting older archives.
- Automated restore drill: copies backup to a clean directory and validates `PRAGMA integrity_check` and `PRAGMA foreign_key_check`.
- Disk capacity safety check via `check_disk_space()`.

### E. System Observability & Telemetry Snapshots ([`backend/observability.py`](file:///e:/0/Work/Website/TeacherOS/Pycharm%20ode/backend/observability.py))
- Live calculation of latency percentiles ($p50$ and $p95$).
- Tracking of subsystem failures (provider timeouts, database lock events, export rendering errors).
- Periodic health snapshot persistence in `system_health_snapshots` (Schema v26).
- Aggregated health telemetry endpoint without PII.

---

## 3. Database Architecture (Schema v26)

### `system_health_snapshots` Table
```sql
CREATE TABLE IF NOT EXISTS system_health_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_uuid TEXT NOT NULL UNIQUE,
    latency_p50_ms REAL NOT NULL,
    latency_p95_ms REAL NOT NULL,
    provider_failures_count INTEGER NOT NULL DEFAULT 0,
    db_locks_count INTEGER NOT NULL DEFAULT 0,
    export_failures_count INTEGER NOT NULL DEFAULT 0,
    disk_free_mb REAL NOT NULL,
    schema_version INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
```

---

## 4. Verification & Acceptance
- **Day 26 Acceptance Check (`backend/day26_acceptance_check.py`)**: **8/8 checks passed**.
- **Unit Test Suite (`tests/test_day26_hardening.py`)**: 10 dedicated unit tests passing.
- **Full Cumulative Test Suite**: **262 tests passing (0 failures, 0 errors)** in 98.4s.
- **Project Syntax Check (`backend/check_project.py`)**: 153 Python files verified with Schema v26.
