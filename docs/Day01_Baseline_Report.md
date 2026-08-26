# TeacherOS Day 1 Baseline Report

**Date:** 2026-08-26

**Baseline target:** schema-v5 Telegram product before class-intelligence work

**Outcome:** recoverable source/database checkpoint tooling, verified critical-path baseline, and explicit operational inventory

## Executive result

The current product passes its project check and deterministic critical-path smoke suite. The suite covers all four generators' saved outputs, private library/search, Word/PDF export construction, feedback, account entitlement display, sandbox payment activation, admin aggregates, route registration, and API-failure recovery. The production database passed schema-v5 health checks with 4 users, 7 materials, 10 usage events, 4 payment records, 1 subscription, and 1 feedback record; no row content was printed or copied.

The original local `.venv` is broken because it references a removed Python 3.10 installation. A clean Python 3.12 environment created from `requirements.txt` passes. Replace the broken environment before operating the bot.

One P0 security follow-up remains outside this checkpoint's safe mutation scope: the published Git history contains a Telegram-token-shaped value in the formerly tracked `docs/secrets.txt`. The file is deleted from the current tree and ignored going forward, and Day 1 code backups deliberately use `git archive HEAD` so they do not copy repository history. Rotate the Telegram bot token immediately, then authorize a coordinated history rewrite and force-push if the old history must be sanitized.

## Verification commands

```powershell
.\.venv-day1\Scripts\python.exe -X utf8 backend/check_project.py
.\.venv-day1\Scripts\python.exe -X utf8 -m unittest discover -s tests -p "test_*.py" -v
.\.venv-day1\Scripts\python.exe -X utf8 backend/day1_measure_baseline.py --output docs/Day01_Baseline_Metrics.json
.\.venv-day1\Scripts\python.exe -X utf8 backend/day1_backup_restore.py --label pre-class-intelligence
```

## Critical-path regression matrix

| Critical path | Owner | Expected complete result | Day 1 evidence | Rollback/recovery |
|---|---|---|---|---|
| Lesson planner | `lesson_planner.py` + OpenRouter + database | Classroom-ready lesson persists with title, level, topic, structured steps, and answer key | PASS: saved lesson inspected in isolated schema-v5 database | Retry from a clean flow; restore app tag if handler regression; retain saved material |
| Activity generator | `activity_generator.py` + OpenRouter + database | Complete activity persists and is privately retrievable | PASS: saved output, type, and content inspected | Retry; switch back to Day 1 tag if callbacks regress |
| Worksheet generator | `worksheet_generator.py` + OpenRouter + database | Complete worksheet persists with usable answer key | PASS: saved worksheet and answer-key content inspected | Retry; roll back handler/prompt together |
| Assessment generator | `quiz_generator.py` + OpenRouter + database | Assessment persists with questions and marking/answer content | PASS: saved assessment content inspected | Retry; roll back handler/prompt together |
| Library and search | `teacher_library.py`, `library_search.py`, database | Owner can list/find material; another user cannot read it | PASS: search found all four records; cross-user read returned no record | Roll back application only; do not delete library rows |
| Word export | `word_document.py`, `word_export.py` | Valid DOCX contains saved title and answer key | PASS: ZIP signature and parsed document text inspected | Keep source material; retry export after app rollback |
| PDF export | `pdf_document.py`, `pdf_export.py` | Non-empty PDF with page objects is produced | PASS: PDF signature, size, and page object inspected | Keep source material; retry export after app rollback |
| Feedback | `feedback_panel.py`, database | Rating/comment persists and admin can review it | PASS: feedback saved, summarized, and moved to reviewed | Restore database backup only for data corruption |
| Account/usage | `account_panel.py`, `usage_tracking.py`, database | Private entitlement and usage summary render | PASS: entitlement loaded and account text inspected | Roll back application; retain usage events |
| Payment sandbox | `payment_panel.py`, `payment_server.py`, database | Created order moves to pending, verified paid, and activates one plan idempotently | PASS: offline local-sandbox lifecycle and ownership isolation | Never alter paid rows manually; restore paired database for corruption |
| Admin | `admin_panel.py`, database | Configured owner sees aggregate users/content/revenue/feedback; non-owner routes remain private | PASS: aggregate dashboard and admin routes inspected | Lock by removing `TEACHEROS_ADMIN_ID`; roll back app if authorization regresses |
| API failure | `openrouter_client.py`, calling handler | Timeout is caught; user receives a recovery-oriented message; process survives | PASS: forced timeout produced expected response | Retry later or change configured model; no database rollback |

This is an offline deterministic technical baseline. It does not call Telegram, OpenRouter, or ZarinPal and therefore does not claim live-provider latency or delivery success.

## Baseline journey measurements

The machine-readable measurements are in `docs/Day01_Baseline_Metrics.json`. They exclude network time and human think time and serve as a repeatable engineering comparison:

| Journey | Screens | Errors | Automated duration | Result |
|---|---:|---:|---:|---|
| First useful resource | 7 | 0 | 98.64 ms | PASS |
| Find and export | 3 | 0 | 118.17 ms | PASS |
| Recover from API failure | 2 | 1 expected injected timeout | 7.96 ms | PASS |

For the Day 28 comparison, repeat these automated measurements and add a five-teacher observed baseline including human completion time, hesitation, wrong taps, and provider wait time. Do not compare live human time against these offline milliseconds.

## Handler and callback inventory

### Commands

`/start`, `/help`, `/cancel`, `/library`, `/search`, `/usage`, `/upgrade`, `/plan`, `/payments`, `/feedback`, `/about`, `/privacy`, `/terms`, `/myid`, `/admin`, `/admin_users`, `/admin_stats`, `/admin_revenue`, `/admin_plans`, `/admin_feedback`, `/admin_grant`, and `/admin_revoke`.

### Callback namespaces

`lesson`/`lesson_*`, `activity_*`, `worksheet_*`, `quiz_*`, `library_*`, `search_*`, `usage_*`, `admin_*`, `account_*`, `feedback_*`, `info_*`, `payment_*`, `plan_*`, `export_*`, `pdf_*`, and legacy `menu_*`. Static callback-length analysis passes Telegram's 64-byte limit.

### Text-handler order

Search group 0; lesson topic group 1; activity topic group 2; worksheet topic group 3; assessment topic group 4; feedback text group 5; general AI chat group 6. Feature state guards prevent the general handler from consuming active-flow input.

## Schema v5 inventory

| Table | Purpose | Ownership/safety notes |
|---|---|---|
| `schema_versions` | Applied schema markers 1-5 | Highest version must remain 5 at this checkpoint |
| `users` | Telegram account identity metadata | `telegram_user_id` is unique |
| `materials` | Lesson/activity/worksheet/assessment content | Foreign key to user; owner-aware reads/deletes |
| `usage_events` | Generation and Word/PDF export events | Foreign keys; unique generation event per material |
| `payments` | ZarinPal/local-sandbox order lifecycle | Unique order, authority, callback hash, and provider reference constraints |
| `subscriptions` | Paid/manual plan entitlement windows | Linked to user and optionally source payment |
| `feedback` | Beta rating/comment workflow | Linked to user; admin status timestamps |

The initializer uses foreign keys, WAL mode, a busy timeout, indexes for owner/time/type/status lookup, and idempotent table/index creation. Payment columns `product_code` and `subscription_days` are added idempotently for legacy databases.

## External services

- Telegram Bot API: polling, commands, callbacks, message/document delivery.
- OpenRouter: general chat and four material generators; timeout 90 seconds with two client retries.
- ZarinPal: sandbox/live payment request and verification. Day 1 is sandbox with the local simulator; no real charge is authorized.
- Local payment callback HTTP server: bound by `PAYMENT_SERVER_HOST` and `PAYMENT_SERVER_PORT`.
- Static website: public product, privacy, terms, and Telegram entry point.
- SQLite: local schema-v5 application database and online backup source.

## Environment-variable catalog

Required secrets/settings: `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`.

Storage/admin: `TEACHEROS_DATABASE_PATH`, `TEACHEROS_ADMIN_ID`.

Payments: `ZARINPAL_SANDBOX`, `ZARINPAL_MERCHANT_ID`, `TEACHEROS_LOCAL_PAYMENT_SIMULATOR`, `PAYMENT_CALLBACK_BASE_URL`, `PAYMENT_SERVER_HOST`, `PAYMENT_SERVER_PORT`, `PAYMENT_TEST_AMOUNT_TOMAN`.

Plans/usage: `TEACHEROS_FREE_DAILY_LIMIT`, legacy `TEACHEROS_SUBSCRIPTION_DAYS`, `TEACHEROS_PRO_SUBSCRIPTION_DAYS`, `TEACHEROS_PREMIUM_SUBSCRIPTION_DAYS`, `TEACHEROS_PRO_PRICE_TOMAN`, `TEACHEROS_PREMIUM_PRICE_TOMAN`, `TEACHEROS_USAGE_TIMEZONE`, `PREMIUM_OPENROUTER_MODEL`.

Only names and non-secret defaults belong in documentation. Values stay in local `.env` or a deployment secret manager.

## Start, stop, backup, restore, and rollback

The exact procedures are in `docs/Day01_Operations_Runbook.md`. The new backup command:

1. refuses a dirty Git worktree;
2. archives only the current tracked tree, excluding `.git` history and ignored secrets/runtime data;
3. creates a consistent SQLite online backup;
4. restores code and database to an isolated directory;
5. verifies critical files, SHA-256 hashes, SQLite integrity, schema version, and critical table counts;
6. writes a JSON restore report below ignored `backups/day1/`.

## Day 1 acceptance status

- Clean checkpoint and exact innovation branch: completed after the Day 1 commit/tag operations recorded in Git.
- Code and database restore tests: implemented; actual report generated after the clean checkpoint.
- Critical paths have named owners, expected results, evidence, and rollback steps: complete.
- Complete generated results inspected rather than treating startup as safety: complete for deterministic offline outputs.
- Live Telegram/OpenRouter/ZarinPal delivery: not exercised; external smoke is intentionally separated from deterministic baseline to avoid accidental messages, spend, or real payment.
- Token rotation/history sanitation: P0, requires operator action and coordinated repository-history authorization.
