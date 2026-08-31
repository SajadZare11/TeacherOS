# Day 18 — Connect Approved Analysis Directly to Teaching Action

Day 18 continues **Phase 3 (Student Evidence, Formative Insights & Differentiation)** by closing the gap between diagnosis and immediate pedagogical execution.

---

## 1. Core Principles & Action Types

| Action Type | Pedagogical Focus |
| :--- | :--- |
| **Reteaching Lesson** | Guided discovery with CCQs, paired error spotting, communicative production, and formative exit tickets. |
| **Targeted Practice Worksheet** | Part A (Spot/Underline), Part B (Sentence Rewrite), Part C (Application), with full diagnostic Answer Key. |
| **Differentiated Practice** | Three-tier progression: 🟢 Support (sentence frames/word bank), 🟡 Core (standard), 🟣 Challenge (reasoning/extension). |
| **Temporary Group Activity** | Fluid grouping protocol with structured roles (**Rule Captain**, **Sentence Editor**, **Reporter**) for editing clinics. |
| **Quick Reassessment** | 10-minute formative check with diagnostic items and a 4-point scoring rubric. |
| **Targeted Homework** | Self-audit review, revision practice, and metacognitive reflection prompt. |

---

## 2. Invariants & Provenance Protection

1. **Only Approved Analysis**: Attempting to generate follow-up actions from draft or rejected analyses is strictly blocked by database triggers and service validators.
2. **What This Addresses**: Every material explicitly cites `What this addresses: Analysis [ea-UUID] — Target: [Gap Title]`.
3. **Class Library Integration**: Automatically creates an owner-scoped, class-linked material in the `materials` table and registers a persistent record in `material_evidence_links`.
4. **Purge Resilience**: Deleting underlying raw student evidence batches preserves the follow-up action and class library materials with full diagnostic integrity.
5. **Distinctive Value Metric**: Tracks the complete conversion pipeline `analysis_approved` $\rightarrow$ `followup_created` $\rightarrow$ `followup_accepted`.

---

## 3. Verification Commands

```powershell
# Set UTF-8 encoding in PowerShell
$env:PYTHONIOENCODING="utf-8"

# 1. Run Complete Unit Test Suite (180 Tests)
& "Pycharm ode/.venv-day1/Scripts/python.exe" -m unittest discover -s "Pycharm ode/tests" -v

# 2. Run Day 18 Acceptance Check
& "Pycharm ode/.venv-day1/Scripts/python.exe" "Pycharm ode/backend/day18_acceptance_check.py"

# 3. Run Days 1–18 Master Audit
& "Pycharm ode/.venv-day1/Scripts/python.exe" "Pycharm ode/backend/day1_to_day18_audit.py" --test-count 180

# 4. Check TeacherOS Project Health
& "Pycharm ode/.venv-day1/Scripts/python.exe" "Pycharm ode/backend/check_project.py"
```
