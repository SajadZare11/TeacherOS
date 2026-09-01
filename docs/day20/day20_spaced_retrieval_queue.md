# Day 20: Transparent Retrieval and Spaced-Review Queue

## 1. Executive Summary

**Day 20** implements a **transparent, deterministic retrieval and spaced-review queue** for English teachers. Previously taught language returns at useful intervals without black-box mastery algorithms or engagement gimmicks.

Status remains an honest, flexible **planning aid** under direct teacher control.

---

## 2. Pedagogical Architecture

### A. Six Language Categories Supported
1. **Vocabulary (`vocabulary`):** Lexical items, collocations, idiomatic expressions, topic-specific vocabulary.
2. **Grammar (`grammar`):** Structural patterns, tense contrast, modal verbs, complex sentences.
3. **Pronunciation (`pronunciation`):** Phonemic contrasts, word/sentence stress, intonation patterns, connected speech.
4. **Functional Language (`functional_language`):** Conversational formulas, negotiation phrases, polite requests, hedging.
5. **Common Errors (`common_error`):** Recurring L1-interference patterns, fossilized mistakes, false friends.
6. **Exam Strategies (`exam_strategy`):** Time-management techniques, skimming/scanning tactics, discourse markers.

### B. Four Source Types
- **`lesson`:** Language introduced during generated or taught lesson plans.
- **`evidence_analysis`:** High-frequency error clusters identified by the Evidence Analysis Copilot (Day 16).
- **`writing_feedback`:** Remedial targets highlighted by Writing Feedback (Day 17).
- **`manual`:** Custom items added directly by the teacher during or after class.

---

## 3. Spaced Retrieval Algorithm & Deterministic Transitions

### A. Configurable Interval Schedule
- **Default Schedule:** `[2, 7, 21, 45]` days.
- **Customizable:** Teachers can inspect and edit the schedule per class (e.g. `[1, 4, 10, 25]` for intensive courses).

### B. Three-Way Review Transitions
| Outcome | Stage Transition | Next Review Calculation |
| :--- | :--- | :--- |
| **Remembered** (`remembered`) | $\text{Stage} \leftarrow \min(\text{Stage} + 1, N-1)$ | $\text{Review Date} + \text{Intervals}[\text{Stage}_{\text{new}}]$ |
| **Partly Remembered** (`partly_remembered`) | $\text{Stage} \leftarrow \text{Stage}$ | $\text{Review Date} + \text{Intervals}[\text{Stage}]$ |
| **Forgotten** (`forgotten`) | $\text{Stage} \leftarrow \max(0, \text{Stage} - 1)$ | $\text{Review Date} + \text{Intervals}[\text{Stage}_{\text{new}}]$ |

### C. Anti-Hijacking Load Cap
- **Cap:** Maximum **5 due items** per lesson warm-up block.
- **Rationale:** Prevents accumulated backlogs from overwhelming a 45-to-60 minute lesson.

---

## 4. State Lifecycle & Edge-Case Handling

```
[Introduced] ──► [Active] ──(Due Date Arrives)──► [Due]
                    │                              │
                    ├───► [Snoozed] (1/3/7 days) ──┘ (Reactivates automatically)
                    ├───► [Paused] ◄──► [Resumed]
                    ├───► [Archived]
                    └───► [Manual Schedule Override]
```

1. **Empty State:** Friendly confirmation when all items are up to date.
2. **Overdue State:** Overdue items surface prioritized by earliest due date, capped to 5.
3. **Snooze State:** Postpones item by 1, 3, or 7 days without advancing interval stage.
4. **Pause / Resume:** Excludes item from due queries until explicitly resumed.
5. **Archive:** Soft-removes item from active queue without destroying historical logs.
6. **Deleted Source:** Setting `source_id = NULL` preserves queue items if the original lesson plan is deleted.
7. **Manual Override:** Teacher can directly set next review date, stage, or confidence level.

---

## 5. Database Schema (Version 20)

### `retrieval_review_items` Table
- `id` (INTEGER PRIMARY KEY)
- `item_uuid` (TEXT UNIQUE)
- `user_id` (INTEGER NOT NULL, FK users)
- `class_id` (INTEGER NOT NULL, FK classes)
- `category` (TEXT NOT NULL, CHECK in 6 categories)
- `prompt_text` (TEXT NOT NULL)
- `target_answer` (TEXT NOT NULL)
- `notes` (TEXT)
- `source_type` (TEXT NOT NULL, CHECK in 4 sources)
- `source_id` (INTEGER)
- `interval_stage` (INTEGER NOT NULL DEFAULT 0)
- `interval_days_json` (TEXT NOT NULL DEFAULT '[2, 7, 21, 45]')
- `confidence` (TEXT NOT NULL DEFAULT 'medium')
- `status` (TEXT NOT NULL DEFAULT 'active')
- `introduced_at` (TEXT NOT NULL)
- `last_reviewed_at` (TEXT)
- `next_review_date` (TEXT NOT NULL)
- `snoozed_until` (TEXT)
- `review_count` (INTEGER NOT NULL DEFAULT 0)
- `created_at` / `updated_at` (TEXT NOT NULL)

### `retrieval_review_logs` Table
- `id` (INTEGER PRIMARY KEY)
- `item_id` (INTEGER NOT NULL, FK retrieval_review_items)
- `user_id` / `class_id` (INTEGER NOT NULL)
- `review_date` (TEXT NOT NULL)
- `result` (TEXT NOT NULL)
- `stage_before` / `stage_after` (INTEGER NOT NULL)
- `next_date_after` (TEXT NOT NULL)
- `created_at` (TEXT NOT NULL)

---

## 6. Verification & Test Coverage

- **Automated Tests:** `tests/test_day20_retrieval_review.py` (all tests passing).
- **Acceptance Gate:** `backend/day20_acceptance_check.py` (PASS).
- **Cumulative Audit:** `backend/day1_to_day20_audit.py` (PASS).
- **Telegram Constraints:** All callback strings bounded to $\le 64$ bytes.
