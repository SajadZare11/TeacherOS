# TeacherOS Day 24: Telegram Speed, Clarity, Accessibility, Localization, and Mini App Decision

## 1. Executive Summary & Outcome
Day 24 polishes the entire TeacherOS Telegram bot interface for phone-native speed, clarity, screen-reader accessibility, language localization, and class context permanence. Teachers never wonder what the bot is doing, which class is active, or how to navigate between teaching tools.

---

## 2. Key Architecture & Features

### A. Centralized String Catalog & Localization (`backend/string_catalog.py`)
- Standardizes all English product copy across commands, navigation, class contexts, errors, and flows.
- Isolates Persian billing, plan descriptions, and support copy for modular localization.
- Safe dynamic string interpolation via `tr(key, lang="en", **kwargs)` with automatic fallback to English if a localized string is unavailable.
- Supported languages: English (`en`) and Persian (`fa`).

### B. Screen-Reader Accessibility & Progressive Disclosure
- Eliminates emoji-only meaning. Every status badge provides explicit textual indicators:
  - `[Status: Approved]`
  - `[Status: Draft]`
  - `[Status: Needs Review]`
  - `[Status: Active]`
  - `[Status: Secure]`
  - `[Status: Needs Support]`
- Keyboard layout hygiene: maximum 2–3 buttons per row to avoid cramped tap targets on small mobile screens.
- Explicit active class header indicator on every class-aware screen:
  `🏫 Active Class: {class_name} · Level: {level}`.

### C. 3-Step First-Run Onboarding Walkthrough
- Compact, interactive 3-step walkthrough introducing new teachers to the core loop without tutorial friction:
  - **Step 1: Set Up Your Class** (CEFR level, age group, goals).
  - **Step 2: Plan & Teach** (Materials generation, 30-second outcome check-in).
  - **Step 3: Evidence to Action** (Formative diagnoses, differentiation, spaced retrieval, reports).
- Tracked via `user_ui_preferences.onboarding_completed`.

### D. Pinned Favorites & Class-Aware Search (`backend/ui_service.py`)
- Teachers can pin favorite materials directly to an active class for 1-tap reuse during lessons.
- Fast, scoped search across materials belonging to the active class.
- Persisted via `user_pinned_materials` with complete multi-tenant isolation.

---

## 3. Database Architecture (Schema v24)

### `user_ui_preferences` Table
```sql
CREATE TABLE IF NOT EXISTS user_ui_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    language_code TEXT NOT NULL DEFAULT 'en' CHECK (language_code IN ('en', 'fa')),
    compact_mode INTEGER NOT NULL DEFAULT 0 CHECK (compact_mode IN (0, 1)),
    onboarding_completed INTEGER NOT NULL DEFAULT 0 CHECK (onboarding_completed IN (0, 1)),
    last_active_class_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (last_active_class_id) REFERENCES classes(id) ON DELETE SET NULL
);
```

### `user_pinned_materials` Table
```sql
CREATE TABLE IF NOT EXISTS user_pinned_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    class_id INTEGER NOT NULL,
    material_id INTEGER NOT NULL,
    pinned_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
    UNIQUE (user_id, class_id, material_id)
);
```

---

## 4. Telegram Mini App Architectural Decision Record (ADR)

### Context:
Telegram supports both native inline keyboards / chat flows and Telegram Mini Apps (embedded web views).

### Decision:
**Retain Native Telegram Chat & Inline Keyboards for Days 1–30 Core Loop; Defer Mini App to Post-Pilot Expansion.**

### Rationale:
1. **Speed & Latency**: Native Telegram inline callbacks respond in $<100$ms over cellular connections without loading external web assets or rendering JavaScript bundles.
2. **Offline Resilience & Data Usage**: Teachers in low-bandwidth environments experience zero asset load failures when using native bot messages and inline keyboards.
3. **Pilot Clarity**: The primary goal of Days 1–30 is proving whether teachers complete the weekly teaching loop (plan $\to$ teach $\to$ check-in $\to$ evidence $\to$ follow-up). Native chat flows eliminate webview session authentication and browser compatibility variables.
4. **Trigger for Future Mini App**: If post-Day 30 pilot feedback reveals that teachers frequently review dense student writing batches ($\ge 20$ essays simultaneously) or comprehensive curriculum heatmaps where vertical chat scrolling creates friction, a dedicated Telegram Mini App will be built specifically for the **Evidence Analysis Workbench & Curriculum Matrix**.

---

## 5. Verification & Acceptance
- **Day 24 Acceptance Check (`backend/day24_acceptance_check.py`)**: **9/9 checks passed**.
- **Test Suite (`tests/test_day24_telegram_polish.py`)**: 10 dedicated unit tests passing.
- **Cumulative Test Suite**: **244 tests passing (0 failures, 0 errors)** in 83.5s.
- **Project Syntax & Callback Length Check (`backend/check_project.py`)**: 143 files verified, all callback data $\le 64$ bytes.
