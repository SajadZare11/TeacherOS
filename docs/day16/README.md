# Day 16 — Evidence Analysis & Transparent Findings

Day 16 extends **Phase 3 (Student Evidence, Formative Insights & Differentiation)** by turning raw evidence batches into transparent, cited, calibrated, and teacher-editable pedagogical findings.

---

## 1. Core Architecture & Transparent Invariants

| Invariant | Enforcement |
| :--- | :--- |
| **Evidence Traceability** | Every finding (strength, common error, misconception, next priority) strictly references valid `evidence_item_ids` and anonymous student labels. No floating or unsubstantiated claims. |
| **Deterministic Counts & Zero Fake Percentages** | Counts reflect database items exactly. Prohibits hallucinated decimal percentages (e.g. "87.4% error rate"). Frequency bands (`few`, `some`, `many`, `most`) are used for qualitative generalization. |
| **Calibrated Uncertainty** | Sample size determines uncertainty: `high` ($\le 2$ items) with explicit Limited Evidence Notice; `medium` ($3–5$ items) with Moderate Sample Notice; `low` ($\ge 6$ items). |
| **Teacher Approval Gate** | Findings start as drafts (`approved = 0`). Findings require explicit teacher approval before influencing lesson recommendations or learning objectives. |
| **Minimal Summary Persistence** | When approved, a standalone minimal pedagogical summary is stored. If raw evidence is purged or deleted later, the approved summary and provenance metadata remain intact. |
| **Zero Raw Evidence Telemetry** | Telemetry product events (`evidence_batch_analyzed`, `evidence_analysis_approved`) log only metadata (`batch_id`, `response_count`, `uncertainty`), never student writing. |

---

## 2. Schema v16 Database Structure

- `evidence_analysis_results`:
  - `id`: Auto-incrementing primary key.
  - `analysis_uuid`: Unique public identifier (`ea-XXXXXXXX`).
  - `batch_id`, `class_id`, `user_id`: Immutable multi-tenant foreign keys.
  - `response_count`: Total active student responses analyzed.
  - `findings_json`: Structured JSON containing strengths, common errors, misconceptions, next priorities, and temporary groups.
  - `uncertainty` & `uncertainty_reason`: Calibrated confidence levels (`low`, `medium`, `high`).
  - `limited_evidence_notice`: Prominent warning banner for small sample sizes.
  - `approved`, `approved_summary`, `approved_at`: Teacher approval state.
  - Triggers: Enforce active batch ownership and freeze approved findings against illicit tampering.

---

## 3. Verification Commands

```powershell
# Set UTF-8 encoding in PowerShell
$env:PYTHONIOENCODING="utf-8"

# 1. Run Complete Unit Test Suite (152 Tests)
& "Pycharm ode/.venv-day1/Scripts/python.exe" -m unittest discover -s "Pycharm ode/tests" -v

# 2. Run Day 16 Acceptance Check
& "Pycharm ode/.venv-day1/Scripts/python.exe" "Pycharm ode/backend/day16_acceptance_check.py"

# 3. Run Days 1–16 Master Audit
& "Pycharm ode/.venv-day1/Scripts/python.exe" "Pycharm ode/backend/day1_to_day16_audit.py" --test-count 152

# 4. Check TeacherOS Project Health
& "Pycharm ode/.venv-day1/Scripts/python.exe" "Pycharm ode/backend/check_project.py"
```
