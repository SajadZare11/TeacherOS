# Day 8 — Class dashboard and Today queue

Day 8 turns an owned class into one short, action-oriented home screen. The verified class name appears first, followed by one visually dominant **Plan Next Lesson** action. Analyze Work, Create Materials, Record Outcome, Progress, Library, and Profile remain secondary.

## Compact dashboard

The initial phone-sized message shows only the compact profile, next planned lesson, latest recorded outcome, latest unresolved controlled difficulty, review-due count, pending-analysis count when non-zero, and a clean no-history instruction. Full profile fields, history counts, and the UTC last-active timestamp open through **More details**.

No mastery, diagnosis, teaching, or approval state is inferred. Until later rollout gates open, class-aware generation and evidence analysis screens explicitly identify their limits and leave the existing generators as one-off tools.

## Today queue

The owner-scoped queue orders five durable states:

1. unfinished class setup;
2. taught lesson missing an outcome;
3. pending analysis approval;
4. planned lesson;
5. due review.

Future-dated reviews stay out of Today. Every queue callback either resumes the durable setup draft or reopens an owned, revision-checked class surface.

## Profile and lifecycle safety

All ten Day 7 profile fields are editable one at a time. Button choices commit one field; multi-select changes remain local until **Save this field**; typed name/coursebook values are normalized and bounded. Updates require owner, active status, and the expected class revision.

Archive and restore each require a separate confirmation callback. They update status only: linked materials, lessons, outcomes, action items, and history remain stored. Archived profiles are read-only until restored. Opening or acting on a class refreshes `last_active_at` without invalidating the current revisioned keyboard.

## Verification status

The machine report is `outputs/day08/dashboard_report.json`. It verifies primary/secondary action hierarchy, all five Today states, ten editable profile fields, destructive confirmations, callback grammar, and Telegram's byte limit.

The plan's five-second/80% usability measure requires real observers and remains **NOT RUN**. Use [Usability_Test_Protocol.md](Usability_Test_Protocol.md); do not infer or fabricate participant results.
