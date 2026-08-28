# Day 7 — Two-minute resumable class setup

Day 7 replaces the Day 6 setup introduction with a durable, button-first setup flow. The Classes flag remains the rollout boundary; Quick Create is unchanged when the flag is off.

## Collected context

The flow collects only a private class label, CEFR or explicit Not sure, age band, class-size range, usual duration, main goal, weak areas, optional coursebook/unit, available equipment, and teaching preferences. Every screen explains how the field improves output.

No screen asks for student names, disabilities, health information, birthdays, or sensitive learner profiles. The only required typed answer is a class label of at most ten words. Coursebook/unit is optional and may be skipped.

## Reliability

- Every selection is persisted immediately in one owner-scoped draft.
- Every step provides Back, Save Draft, and Cancel.
- Cancel never discards implicitly; discard requires a separate confirmation.
- Resume survives lost Telegram context or process restarts.
- Final review exposes an edit route for every field.
- Completion uses both a unique idempotency key and the durable draft ID, so duplicate Save taps return the same class.
- Unknown and Not sure are stored in `setup_profile_json`, never guessed or collapsed into an unexplained null.
- The last class can be used as a template only when an owned class already exists.
- Central `class_creation_access_for_user()` applies plan limits only when the Entitlements flag is enabled; a blocked completion preserves the draft.

## Measurement

Privacy-safe product events record `class_setup_started`, `class_setup_completed`, and `class_setup_abandoned`. Completed and abandoned events include elapsed seconds; abandoned events include only the field name, not entered content.

The machine report is in `outputs/day07/setup_report.json`. The required three-person timing observation is external and remains NOT RUN until real observations are recorded using [Observed_Setup_Test.md](Observed_Setup_Test.md).
