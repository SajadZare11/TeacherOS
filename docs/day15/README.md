# Day 15 — Privacy-First Evidence Inbox

Day 15 inaugurates **Phase 3 (Student Evidence, Formative Insights & Differentiation)** by delivering the **Evidence Inbox**, enabling teachers to safely submit, organize, preview, and delete anonymized student work without exposing raw student data to logs, telemetry, or permanent persistence.

---

## 1. Supported Input Formats

- **Pasted Plain Text / Telegram Text Messages**: Direct chat input or multi-student pastes with intelligent splitting.
- **`.txt` File Uploads**: Validated UTF-8 text documents (with CP1252/Latin-1 fallback).
- **`.docx` File Uploads**: Validated Microsoft Word documents parsed safely using `python-docx` across paragraphs and table structures.
- **Explicit Deferral**: `.pdf`, audio files (`.mp3`, `.m4a`, `.wav`, `.ogg`), and image formats (`.jpg`, `.png`) are deferred safely with clear messaging explaining that OCR and audio consent verification are required before release.

---

## 2. Ingestion & Multi-Student Auto-Splitting

The evidence engine recognizes diverse student boundary conventions:
- Explicit separator lines (`---`, `===`, `***`)
- Student header markers (`Student 1:`, `Student A:`, `Learner 2:`, `[Pupil B]`, `S1:`)
- Double newline boundaries for unstructured paragraphs
- Automatic assignment of clean anonymous labels (`Student 1`, `Student 2`, `Student A`, etc.)

---

## 3. Privacy Safeguards & Data Minimization

| Guardrail | Enforcement |
| :--- | :--- |
| **No Raw Evidence in Logs** | Telemetry logs record only `batch_id`, `item_count`, `evidence_type`, and `retention_policy`. Zero student writing appears in stdout/stderr/product events. |
| **Anonymous Student Labels** | Real student names, emails, and phone numbers are discouraged. Teacher can edit labels (e.g. `Pair A`, `Group 1`) at any time. |
| **Privacy Confirmation** | Submissions require explicit teacher confirmation before persistence. |
| **Automated Retention** | Supported policies: `7_days` (short-term), `30_days` (recommended default), `until_deleted`, `manual_only`. Automated `purge_expired_evidence` wipes raw content. |
| **Deletion Control** | Immediate soft-delete and purge of individual student items or whole batches with automatic cascade updates. |
| **Multi-Tenant Isolation** | Database triggers and owner-scoped queries strictly block cross-user access. |

---

## 4. Schema v15 Database Architecture

Schema v15 adds two core tables:
- `evidence_batches`: Metadata, class link, format, item count, retention policy, and deletion timestamps.
- `evidence_items`: Individual student responses, anonymous label, word/char counts, and deletion status.
- Triggers: Enforce active class ownership, block cross-tenant updates, and synchronize active item counts.

---

## 5. Verification Commands

```powershell
# 1. Run Complete Unit Test Suite (138 Tests)
& "Pycharm ode/.venv-day1/Scripts/python.exe" -m unittest discover -s "Pycharm ode/tests" -v

# 2. Run Day 15 Acceptance Check
& "Pycharm ode/.venv-day1/Scripts/python.exe" "Pycharm ode/backend/day15_acceptance_check.py"

# 3. Run Days 1–15 Master Audit
& "Pycharm ode/.venv-day1/Scripts/python.exe" "Pycharm ode/backend/day1_to_day15_audit.py" --test-count 138

# 4. Check Project Health
& "Pycharm ode/.venv-day1/Scripts/python.exe" "Pycharm ode/backend/check_project.py"
```
