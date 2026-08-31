# Day 13 — Plan Next Lesson (Evidence-to-Action Engine)

Day 13 completes the closed teaching loop (`Class Setup → Plan → Teach → 30-Second Outcome → Plan Next Lesson`). When a teacher taps **🎯 Plan Next Lesson** on their class dashboard, TeacherOS inspects verified class history and recorded outcome facts, proposes the most appropriate next lesson, and generates a structured, classroom-ready lesson plan with strict timing and objective alignment.

---

## Pedagogical Modes

TeacherOS offers six distinct modes for next-lesson planning:

1. **🎯 Use recommendation (Auto)**: Auto-selects the optimal mode based on recorded class history and the latest outcome facts.
2. **🔄 Continue unfinished work**: Prioritizes completing and consolidating lessons that were recorded as partly completed or partly achieved.
3. **🔁 Reteach with support**: Proposes a fresh pedagogical route with scaffolding when recent concepts presented difficulty, without claiming permanent student weakness.
4. **🆕 Start a new topic**: Moves forward into the next curricular area with retrieval warm-ups, explicitly noting that a single outcome does not prove full mastery.
5. **📝 Prepare for assessment**: Focuses on observable evidence gathering when aligned with class goals or upcoming evaluations.
6. **✏ Choose manually**: Gives the teacher full control to type a custom topic while benefiting from class-aware profile context.

---

## Rationale & "Why this next?" Panel

- Every recommendation includes an explicit pedagogical rationale and an **Uncertainty Level**:
  - **LOW**: 2 or more teacher-approved outcome records are available.
  - **MEDIUM**: Exactly 1 outcome record is available; informs proposal but cannot prove mastery.
  - **HIGH**: No outcome records included; relies on general class profile and baseline objectives.
- The **"Why this next?"** view lists the exact historical records used (outcomes, class objectives, lessons) with fact summaries.

---

## Teacher Control & Safeguards

- **Priority Switcher**: Switch between *Balanced*, *Continuity first*, *Reteaching first*, and *Assessment first*.
- **Source Toggles**: Exclude or include individual history records with real-time recalculation of uncertainty.
- **Manual Input Guardrails**: Custom topic inputs reject PII (phone numbers, email addresses), control characters, and inputs outside the 2–300 character range.
- **Ignore Option**: Dismiss recommendations cleanly without affecting existing class history.
- **Follow-up Acceptance**: Post-generation feedback toolbar (`👍 Yes / 👎 Not quite`) records actionable adoption metrics.

---

## Timing Validation & Provenance

- Lesson generation enforces that section timings sum exactly to the class lesson duration (`timing_total_minutes == duration_minutes`).
- Approved objectives are linked to generated plans and materials.
- When saved, an immutable snapshot of all active sources is stored in `next_lesson_plan_sources`.

---

## Schema v13 & Database Safeguards

Schema v13 adds four tables with strict database triggers:
- `next_lesson_recommendations`: Drafts, modes, rationale, uncertainty, duration, and objective labels.
- `next_lesson_recommendation_sources`: Foreign-key links to class objectives, lessons, and outcomes with `included` toggles.
- `next_lesson_plans`: Completed lesson plans with timing total, material link, and validation scores.
- `next_lesson_plan_sources`: Immutable source snapshot records linking each completed plan to its exact inputs.
- Triggers enforce owner isolation, prevent cross-tenant access, block modification of saved plans, and forbid tampering with completed source links.

---

## Verification & Audit

```powershell
$env:PYTHONIOENCODING="utf-8"
& '.\.venv-day1\Scripts\python.exe' -m unittest discover -s tests -v
& '.\.venv-day1\Scripts\python.exe' backend/day13_acceptance_check.py
& '.\.venv-day1\Scripts\python.exe' backend/day1_to_day13_audit.py --test-count 118
& '.\.venv-day1\Scripts\python.exe' backend/check_project.py
```

*Note*: Engineering tests verify all 6 modes, uncertainty math, triggers, and timing validation. 4-week repeat-use adoption metrics remain `BLOCKED_NOT_FABRICATED` until observed live pilot evidence is gathered.
