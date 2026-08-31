# Day 17 — Writing Feedback Copilot around Revision

Day 17 continues **Phase 3 (Student Evidence, Formative Insights & Differentiation)** by building the **Writing Feedback Copilot**, empowering teachers to produce kind, prioritized, rubric-aware formative feedback centered on student revision.

---

## 1. Core Principles & Architecture

| Invariant | Enforcement |
| :--- | :--- |
| **Strengths First** | Begins with genuine praise of linguistic strengths and communicative achievement before offering revision targets. |
| **Prioritized Focus ($\le 3$)** | Limits feedback targets to at most three (1–3) prioritized areas to prevent cognitive overload and preserve learner motivation. |
| **Separate Accuracy vs Style** | Categorizes feedback into **Corrections** (grammatical accuracy/inflection) and **Suggestions** (lexical upgrade, sentence combining, flow). |
| **One Actionable Revision Task** | Provides exactly one concrete, immediate revision exercise (e.g., "Upgrade 2 sentences using cohesive transition words"). |
| **No Full Rewriting by Default** | Strictly preserves student voice and agency rather than rewriting their entire essay. |
| **Rubric Scoring Draft Label** | If a rubric is provided, criteria breakdowns are labeled as draft scores requiring teacher confirmation. If no rubric is provided, feedback remains separated from grades. |
| **Dual Clean Copies** | Produces both a **Clean Student Feedback Copy** (free of internal class analytics/tokens) and an **Annotated Teacher Diagnostic Copy** (.docx and .pdf). |
| **Teacher Approval Gate** | All feedback starts as a draft (`approved = 0`) and requires teacher review before export or student sharing. |

---

## 2. Schema v17 Database Structure

- `writing_feedback_records`:
  - `id`: Primary key.
  - `feedback_uuid`: Unique public identifier (`wf-XXXXXXXX`).
  - `user_id`, `class_id`, `evidence_item_id`: Owner and relational foreign keys.
  - `student_label` & `student_level`: Student metadata (e.g. "Ali", "B1").
  - `feedback_mode`: Depth mode (`light`, `balanced`, `detailed`, `rubric`).
  - `task_prompt`, `rubric_name`, `rubric_json`: Task and rubric context.
  - `feedback_json`: Structured diagnosis JSON containing strengths, priorities, corrections, suggestions, and revision task.
  - `teacher_comments`: Editable teacher feedback notes.
  - `revision_task`: Concrete revision exercise.
  - `student_copy_text` & `teacher_copy_text`: Rendered copies.
  - `estimated_minutes_saved`: Estimated time saved per piece (~12 min).
  - `approved`, `approved_at`, `status`: Approval lifecycle (`draft` $\rightarrow$ `approved`).

---

## 3. Verification Commands

```powershell
# Set UTF-8 encoding in PowerShell
$env:PYTHONIOENCODING="utf-8"

# 1. Run Complete Unit Test Suite (166 Tests)
& "Pycharm ode/.venv-day1/Scripts/python.exe" -m unittest discover -s "Pycharm ode/tests" -v

# 2. Run Day 17 Acceptance Check
& "Pycharm ode/.venv-day1/Scripts/python.exe" "Pycharm ode/backend/day17_acceptance_check.py"

# 3. Run Days 1–17 Master Audit
& "Pycharm ode/.venv-day1/Scripts/python.exe" "Pycharm ode/backend/day1_to_day17_audit.py" --test-count 166

# 4. Check TeacherOS Project Health
& "Pycharm ode/.venv-day1/Scripts/python.exe" "Pycharm ode/backend/check_project.py"
```
