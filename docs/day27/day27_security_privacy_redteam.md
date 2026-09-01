# TeacherOS Day 27: Red-Team Security, Multi-Tenant Isolation, Prompt Defense, and Privacy Deletion

## 1. Executive Summary & Outcome
Day 27 verifies security, anti-tamper boundaries, prompt injection disarming, file upload safety, and GDPR-compliant hard deletion across TeacherOS. Security and AI abuse cases are implemented and tested as product requirements rather than policy prose.

---

## 2. Red-Team Attack Vectors & Protections

### A. Multi-Tenant Cross-User Attack Defense
- **Cross-User Class & Evidence Attacks**: Every service function (`class_service`, `evidence_analysis_service`, `progress_report_service`, `ui_service`) enforces strict owner scoping (`user_id = ?` and `FOREIGN KEY (class_id, user_id)`). Attacker attempts to query, pin, modify, or delete a victim's resources return `None` or `False` with 0 records touched.
- **Guessed / Forged Telegram Callbacks**: Base36-encoded object IDs passed in callback payloads (`v1|...`) are verified against the calling user's registered ID before any state change is allowed.
- **Unauthorized Admin Route Access**: Protected via `is_admin_telegram_user()` matching against configured owner IDs.

### B. Filename Traversal & File Safety ([`backend/security_service.py`](file:///e:/0/Work/Website/TeacherOS/Pycharm%20ode/backend/security_service.py))
- **Path Traversal Sanitization**: `validate_safe_filename()` neutralizes `../`, `..\`, forward/backward slashes, null bytes (`\x00`), control characters, and reserved Windows device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`).
- **File Content & Magic Header Verification**: `validate_file_content()` checks binary signatures (`%PDF-`, `PK\x03\x04`, valid UTF-8) and enforces a strict 10MB payload ceiling.

### C. Adversarial Prompt Injection & Exfiltration Disarming
- **Pattern Detection**: `is_potential_prompt_injection()` detects system override attempts, instruction reset commands (`"ignore previous instructions"`), and prompt/data exfiltration queries.
- **Delimiter Sanitization**: `sanitize_prompt_input()` neutralizes structural delimiters (`<|im_start|>`, `<|im_end|>`, `[INST]`, `[/INST]`, `SYSTEM:`) and bounds text length (25,000 chars) to prevent denial-of-wallet bloat attacks.

### D. Privacy Hard Deletion & Automated Retention ([`backend/privacy_retention_service.py`](file:///e:/0/Work/Website/TeacherOS/Pycharm%20ode/backend/privacy_retention_service.py))
- **Class Data Purge**: `hard_delete_class_data()` cascades immediate permanent deletion across curriculum units, lesson history, outcomes, evidence batches, analyses, writing feedback, follow-up actions, differentiations, review items, progress reports, and pinned materials.
- **Account Right-to-be-Forgotten**: `hard_delete_user_account()` permanently deletes the user record and cascades across all associated platform data.
- **Automated Retention Job**: `run_retention_cleanup_job()` purges unlinked draft evidence older than plan retention windows while preserving approved progress reports and lesson facts.

---

## 3. Database Architecture (Schema v27)

### `security_audit_logs` Table
```sql
CREATE TABLE IF NOT EXISTS security_audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_uuid TEXT NOT NULL UNIQUE,
    user_id INTEGER,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    target_resource TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    ip_address TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);
```

---

## 4. Verification & Acceptance
- **Day 27 Acceptance Check (`backend/day27_acceptance_check.py`)**: **10/10 checks passed**.
- **Unit Test Suite (`tests/test_day27_security_redteam.py`)**: 10 dedicated unit tests passing.
- **Full Cumulative Test Suite**: **272 tests passing (0 failures, 0 errors)** in 102.5s.
- **Project Syntax Check (`backend/check_project.py`)**: 158 Python files verified with Schema v27.
