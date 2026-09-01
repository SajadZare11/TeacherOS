# Day 22: Raise English-Teaching Quality with CEFR and Curriculum Discipline

## 1. Pedagogical Intent & Principles
TeacherOS prioritizes communicative competence over superficial topic chatter:
1. **Communicative Can-Do Outcomes**: Every lesson targets observable learner abilities (describing, negotiating, comparing, clarifying, drafting, summarizing) rather than passive knowledge ("learn about topic").
2. **Lightweight Coursebook Alignment**: Teachers store unit numbers, unit titles, and syllabus targets without scraping or storing copyrighted textbook materials.
3. **CEFR Communicative Modes**: Objectives are categorized by CEFR activity modes (spoken production, spoken interaction, written production, written interaction, reading reception, listening reception, and mediation).
4. **Teacher Override Invariant**: Teachers have absolute authority to reclassify or correct AI-assigned CEFR modes, and these adjustments are durably preserved for future class context.
5. **Calibrated Quality Standards**: Golden set lesson evaluations calibrated by experienced ELT trainers achieving $\ge 85\%$ alignment on objective-task-assessment coherence.

---

## 2. Core Architectural Components

### A. Schema v22 (`backend/day22_migration.py`)
- **`class_curriculum_units`**:
  Tracks coursebook unit numbers, titles, syllabus targets, and teacher notes with cascade foreign keys.
- **`cefr_objective_mappings`**:
  Links class objectives to CEFR levels (A1–C2), communicative modes, competence categories, and tracks teacher overrides.
- **`golden_curriculum_evaluations`**:
  Stores structured expert evaluations across can-do clarity, task authenticity, assessment alignment, and scaffolding.

---

### B. Validators & Pedagogy Evaluation (`backend/cefr_curriculum_validator.py`)
- **`validate_can_do_wording`**: Detects observable action verbs and blocks generic unobservable knowledge phrasing.
- **`validate_communicative_outcome`**: Ensures authentic communicative task structure (roleplays, debates, information gaps, problem-solving).
- **`validate_check_for_learning`**: Verifies explicit assessment match (exit tickets, peer rubrics, CCQs).
- **`validate_scaffolding`**: Verifies progression from controlled practice to freer production.
- **`evaluate_lesson_curriculum_discipline`**: Evaluates overall lesson quality, failing generic topical plans lacking language outcomes.

---

### C. Service Layer (`backend/curriculum_discipline_service.py`)
- **`save_curriculum_unit`** / **`get_current_curriculum_unit`** / **`list_curriculum_units`**: Coursebook unit lifecycle.
- **`map_objective_to_cefr`** / **`override_cefr_mapping`**: CEFR mapping and teacher override.
- **`get_class_curriculum_coverage`**: Breakdown of covered, partly covered, and not-yet-covered objectives with communicative mode distributions.
- **`record_golden_set_calibration`** / **`get_golden_set_calibration_metrics`**: Evaluation audit metrics.

---

### D. Telegram UI & Keyboards (`backend/curriculum_keyboards.py` & `backend/curriculum_panel.py`)
- Callbacks namespace `v1|cu|{action}|{id}|{rev}` strictly bounded $\le 64$ bytes.
- Interactive unit editor, CEFR coverage browser, and one-tap communicative mode override picker.

---

## 3. Verification & Acceptance
- **Automated Tests**: 224 unit tests passing across the codebase.
- **Acceptance Gate**: `day22_acceptance_check.py` evaluated all 11 criteria as **PASS**.
- **Cumulative Audit**: Days 1–22 completed and recorded in `outputs/day22/days01-22_audit.json`.
