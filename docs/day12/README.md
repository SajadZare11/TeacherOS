# Day 12 — Post-lesson truth in three taps

Day 12 adds a fast, factual outcome check-in after a lesson is explicitly marked taught. It does not infer mastery, require prose, or create an outcome for generated, planned, cancelled, archived-class, or cross-owner lessons.

## Teacher flow

1. Mark a planned lesson as taught. TeacherOS immediately asks for the overall result: Achieved, Partly achieved, or Needs reteaching.
2. Choose No major difficulty for the normal path, or select one or more categories: language/concept, instructions, pace/time, participation, materials, or assessment check.
3. Choose Completed, Partly completed, or Not completed. This third tap saves the facts before any prose prompt.
4. Optionally add a short teacher note, skip it, correct the three answers, or clear a prior note.

The class dashboard and outcome-capture rate update immediately. The correction path updates the same active outcome and appends an immutable, content-minimized fact revision instead of creating a duplicate.

## Reminder behavior

- A teacher may explicitly choose one hour, 18:00 local, 20:00 local, or tomorrow at 09:00 local.
- Each choice creates one durable, one-shot reminder. It never repeats automatically.
- A delivered reminder may be explicitly snoozed again, with a hard maximum of three delivered prompts per lesson.
- Saving an outcome completes any pending reminder. Future snoozes stay out of Today until due.
- Failed Telegram delivery is retried after a 15-minute transport backoff and does not count as a delivered prompt.

## Data and trust safeguards

- Schema v12 adds structured difficulty, completion, capture source, fact version, saved time, and note-update time to `lesson_outcomes`.
- `lesson_outcome_fact_revisions` is append-only through product services, rejects rewriting, and stores no note text; it records only note presence and a SHA-256 digest. Owner/account cascades remain deletable.
- `lesson_outcome_ai_suggestions` is a separate table, so future AI proposals cannot overwrite or masquerade as teacher-recorded facts.
- `lesson_outcome_reminders` is owner-scoped to an explicitly taught lesson.
- Database triggers prevent duplicate active outcomes, incomplete three-tap saves, ownership changes, and revision rewriting.
- Optional notes reject control characters, email addresses, phone numbers, and content over 1,000 characters. The UI also warns against student names or sensitive information.

## Verification

```powershell
& '.\.venv-day1\Scripts\python.exe' -m unittest discover -s tests -v
& '.\.venv-day1\Scripts\python.exe' backend/day12_acceptance_check.py
& '.\.venv-day1\Scripts\python.exe' backend/day1_to_day12_audit.py --test-count 105
& '.\.venv-day1\Scripts\python.exe' backend/day5_migration_check.py --real-copy 'backups\teacheros_20260831_210050_day11-final-v11.db'
```

Engineering tests prove the three-screen/tap structure, but they are not an observed teacher timing study. The under-30-second observation and the pilot's 60% recording-rate target remain `BLOCKED_NOT_FABRICATED` until real teacher evidence exists.
