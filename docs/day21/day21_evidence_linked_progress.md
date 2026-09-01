# Day 21: Evidence-Linked Class Progress, Not Decorative Analytics

## 1. Pedagogical Intent & Principles
Teachers do not need gamified progress rings, arbitrary completion percentages, or vanity usage graphs. They need to know:
1. **What is active**: Which can-do syllabus objectives are currently being practiced.
2. **What needs support**: Which targets have shown observed difficulties in recent lessons or student work and require scaffolding.
3. **What is teacher-confirmed secure**: Which objectives have met repeated evidence and have been explicitly validated by the teacher.
4. **What is due next**: Overdue spaced retrieval items, unrecorded outcomes, or next instructional steps.
5. **Where every claim came from**: 100% traceable linkage to source lesson plans, outcome check-ins, or approved evidence batches.

---

## 2. Core Architectural Components

### A. Schema v21 (`backend/day21_migration.py`)
- **`proposed_class_objectives`**:
  Stores AI/system-extracted syllabus targets awaiting teacher review.
  Columns: `id`, `proposal_uuid`, `user_id`, `class_id`, `source_type`, `source_id`, `objective_text`, `category`, `proposed_status`, `confidence`, `rationale`, `status` (`pending`, `approved`, `rejected`), timestamps.
- **`objective_evidence_links`**:
  Traceable claim links connecting class objectives to specific lesson outcomes, evidence analysis records, writing feedbacks, or manual observations.
  Columns: `id`, `link_uuid`, `objective_id`, `user_id`, `class_id`, `source_type`, `source_id`, `support_level` (`introduced`, `observed_working`, `needs_support`, `secure_confirmed`), `evidence_excerpt`, `teacher_confirmed`, `created_at`.
- **`class_objectives` Extensions**:
  Added `category`, `is_secure`, `secure_confirmed_at`, and `support_level` columns with cascade foreign keys and owner trigger validation.

---

### B. Service Layer (`backend/class_progress_service.py`)
- **`propose_objective`**: Safely extracts or proposes can-do objectives.
- **`approve_proposed_objective`**: Mandatory teacher approval gate moving proposals to `class_objectives`.
- **`reject_proposed_objective`**: Dismisses unwanted proposals without polluting active context.
- **`update_objective_status`**: Explicit state machine (`current`, `needs_support`, `secure`, `paused`, `archived`) with audit logging.
- **`get_class_health_card`**: Evaluates active targets, review backlog, and unrecorded outcomes to suggest the highest-priority instructional decision.
- **`get_class_progress_overview`**: Transparent assembly with counts and chronological timeline.
- **`handle_deleted_source`**: Orphan-safe handling that nullifies source IDs without deleting teacher-approved targets.

---

### C. Telegram UI & Keyboards (`backend/class_progress_panel.py` & `backend/class_progress_keyboards.py`)
- Namespace `v1|pr|{action}|{object_id}|{revision}` using base36 encoding.
- All callback data strictly bounded $\le 64$ bytes.
- Interactive status picker, proposed target review, source evidence tracing, and one-tap health card navigation.

---

## 3. Verification & Acceptance
- **Automated Tests**: 215 tests running across the repository with 0 failures and 0 errors.
- **Acceptance Gate**: `day21_acceptance_check.py` evaluated all 11 criteria as **PASS**.
- **Multi-Tenant Isolation**: Verified across cross-user reading, modifying, and trigger-blocked insertions.
