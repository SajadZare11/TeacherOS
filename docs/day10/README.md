# Day 10 — Class-aware generators

Day 10 makes the four proven generators class-aware while preserving Quick Create as a complete class-free path.

## Shipped behavior

- The class dashboard starts lesson, activity, worksheet, and assessment flows with an owner-verified class ID and revision.
- Saved CEFR level is inherited by all four flows. Lesson duration is also inherited by Lesson Planner. A fully populated class-aware lesson asks for topic and grammar only: two teacher inputs instead of Day 1's four, a 50% reduction.
- Confirmation screens offer explicitly labelled **ONE-TIME** overrides. Overrides live only in the Telegram session and never call a class-profile update.
- Cancel returns to the verified class. Stale, archived, cross-owner, disabled-flag, and malformed class entry points fail closed.
- Quick Create still starts the original class-free flows and persists materials with a null `class_id`.

## Persistence and validation

Schema v10 adds dedicated material provenance fields, quality scores, and owner-checked `material_objective_links`. A class-linked save is atomic: invalid class or objective ownership rolls the whole save back.

Before display, generated resources must pass structured-output and pedagogical checks plus visible Day 10 checks for timing, instructions, CEFR level, and resource requirements. Worksheets and assessments require answer keys. A class-linked assessment with current objectives also requires visible objective alignment. One repair is allowed; the second failure remains a safe failure.

## Post-generation toolbar

Every saved result exposes Save, Word, PDF, Adapt, Regenerate with change, and Report Problem. A class-linked lesson also exposes Use as Next Lesson. Save and Use as Next Lesson are idempotent. Adapt/regenerate creates a new library record and never overwrites the original. Problem reports store the teacher's submitted description and material ID, not the material content.

Class-linked materials appear in the class library and remain visible in the general library and search.

## Verification

The Day 10 acceptance report contains a 48-case matrix:

`4 generators × 2 modes (quick/class) × 6 behaviors (override, cancel, retry, save, Word export, PDF export)`

Run:

```powershell
python backend/day10_acceptance_check.py
python -m unittest discover -s tests -v
python backend/day1_to_day10_audit.py --test-count 79
python backend/check_project.py
```

Reports are written to `outputs/day10/acceptance_report.json` and `outputs/day10/days01-10_audit.json`.
