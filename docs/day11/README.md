# Day 11 — Trustworthy lesson lifecycle and history

Day 11 separates a generated resource from a lesson that a teacher actually planned or taught. TeacherOS no longer treats generation as teaching activity.

## Shipped lifecycle

- Every class-linked lesson material creates exactly one `generated` lesson record with an immutable material link.
- **Use as Next Lesson** asks for Today, Tomorrow, Next class, or Later before moving the record to `planned`.
- If another lesson is already planned, TeacherOS shows the conflict and requires an explicit Replace action. Replacement cancels the earlier plan while preserving its material and history.
- Teachers can cancel a planned lesson without deleting its resource, or mark it taught exactly once.
- State transitions are explicit and restricted: `generated → planned → taught` or `planned → cancelled`. Generated and cancelled records never count as taught.

## Dashboard and history

The class dashboard shows only the current planned lesson as **Next lesson**. A chronological Lesson History screen lists generated, planned, taught, and cancelled records, labels each state, links the resource ID, and exposes Mark as Taught / Cancel only for planned lessons.

Callbacks carry durable lesson and class identifiers, so history actions recover after a process restart without depending on Telegram session memory. Every read and mutation is owner-scoped; stale, cross-owner, archived, and invalid transitions fail closed.

## Auditability and measurement

Schema v11 adds lifecycle state/version fields and an append-only `class_lesson_transitions` ledger. Database triggers prevent changing a lesson's underlying material, deleting a linked resource, rewriting transitions, or attaching another user's/class's resource.

Conversion measurement counts only recorded `generated → planned` and `planned → taught` transitions. Low conversion is reported as workflow friction; TeacherOS does not invent teaching activity, mastery, progress, outcomes, or review schedules from generated-only records.

## Verification

Run:

```powershell
.\.venv-day1\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-day1\Scripts\python.exe backend/day11_acceptance_check.py
.\.venv-day1\Scripts\python.exe backend/day1_to_day11_audit.py --test-count 89
.\.venv-day1\Scripts\python.exe backend/check_project.py
```

Reports are written to `outputs/day11/acceptance_report.json` and `outputs/day11/days01-11_audit.json`.
