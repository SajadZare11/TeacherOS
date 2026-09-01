# TeacherOS Day 25: Centralized Entitlements and Commercial Value Packaging

## 1. Executive Summary & Outcome
Day 25 centralizes all commercial tier capabilities, plan limits, and upgrade telemetry into an integrated entitlement engine ([`backend/entitlement_service.py`](file:///e:/0/Work/Website/TeacherOS/Pycharm%20ode/backend/entitlement_service.py)). The free tier remains completely functional for genuine classroom teaching, while paid tiers (Pro & Premium) directly improve recurring teaching productivity, ongoing class memory, multi-class management, and report exports.

---

## 2. Plan Tier Architecture & Capabilities

| Capability / Resource | Free Tier | Pro Tier (149k Toman / 30d) | Premium Tier (420k Toman / 90d) |
| :--- | :--- | :--- | :--- |
| **Active Class Profiles** | 1 class | 10 classes | Unlimited |
| **Daily Generations** | 10 / day | 50 / day | Unlimited |
| **Evidence Batches / Class** | 2 active batches | 20 active batches | Unlimited |
| **Evidence Items / Batch** | 5 items | 35 items | 100 items |
| **Data Retention** | 30 days | 90 days | 365 days |
| **Differentiation Engine** | Basic | Full (Support / Core / Challenge + 9 Adaptations) | Full (All Modes) |
| **Progress Reports Export** | In-app Preview only | Word (.docx) & PDF (.pdf) Exports | Word & PDF Exports + Priority Branding |
| **Spaced Retrieval Items** | 5 items / lesson | 15 items / lesson | 30 items / lesson |
| **Priority AI Model Routing** | Standard | Standard | Priority Tier (`PREMIUM_OPENROUTER_MODEL`) |

---

## 3. Database Architecture (Schema v25)

### `entitlement_events` Table
Tracks commercial funnel telemetry across teacher interactions:
```sql
CREATE TABLE IF NOT EXISTS entitlement_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_uuid TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'viewed', 'dismissed', 'checkout_started',
            'paid', 'failed', 'refunded', 'cancelled',
            'entitlement_restored'
        )
    ),
    plan_code TEXT NOT NULL,
    feature_key TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

---

## 4. Key Engineering Guarantees

1. **Centralized Decision Authority**:
   - Zero ad-hoc `if plan == 'pro'` checks in Telegram UI handlers. All feature gates query `check_feature_access(telegram_user_id, feature_key)`.
2. **Outcome-Oriented Upgrade Prompts**:
   - Upgrade modals explain tangible pedagogical outcomes (e.g. managing 10 classes with dedicated memory, downloading formatted PDF reports) rather than technical jargon ("tokens", "API credits", or "compute hours").
3. **Free Teaching Loop Guarantee**:
   - Free accounts can complete at least 1 genuine end-to-end teaching loop (Class Setup $\to$ Lesson Planning $\to$ Outcome Check-in $\to$ Evidence Diagnosis $\to$ Differentiation $\to$ Spaced Retrieval $\to$ Report Preview) before hitting an upgrade boundary.
4. **Idempotent Billing & Subscriptions**:
   - Payment order verification (`mark_payment_paid`) is idempotent; duplicate gateway callbacks or connection retries cannot create duplicate subscription periods or corrupt active entitlements.

---

## 5. Verification & Acceptance
- **Day 25 Acceptance Check (`backend/day25_acceptance_check.py`)**: **9/9 checks passed**.
- **Unit Test Suite (`tests/test_day25_entitlements.py`)**: 8 dedicated unit tests passing.
- **Full Cumulative Test Suite**: **252 tests passing (0 failures, 0 errors)** in 87.0s.
- **Project Syntax Check (`backend/check_project.py`)**: 147 Python files verified with Schema v25 and bounded 64-byte callbacks.
