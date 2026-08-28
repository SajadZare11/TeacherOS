# Day 6 — My Classes information architecture

Day 6 introduces a flag-gated home that separates recurring class work from fast one-off creation. With `TEACHEROS_FEATURE_CLASSES=false`, the original six-button home remains unchanged.

## Flagged home

- **My Classes** — recurring teaching with explicit saved context.
- **Quick Create** — the existing lesson, activity, worksheet, and assessment tools, using their original callbacks.
- **Analyze Work** — requires the teacher to choose an owned active class before a class-linked screen appears.
- **Search** and **Account** — preserve their existing routes; Library, Usage, Plans, Payments, Feedback, and policies remain reachable through Account.

Active and archived classes have separate lists. Empty states explain the value of class memory before requesting data. Every class-linked screen prints the verified class name, and archived class context is read-only. Revisioned callbacks are treated only as locators: the service rechecks owner and revision before rendering.

## Recovery and rollback

Malformed, stale, deleted, revision-mismatched, and unauthorized class callbacks all produce the same recovery view. It reveals no class details, states that no change was made, and provides inline refresh and home actions.

Disabling the Classes flag immediately restores the original Quick Create home. It does not delete class records.

## Verification status

The machine report in `outputs/day06/navigation_report.json` verifies route coverage, legacy callback preservation, callback size, callback grammar, archived read-only behavior, screen escapes, and flag-off rollback.

The five-person hallway test is an external evidence gate. Its protocol is ready in [Hallway_Test_Protocol.md](Hallway_Test_Protocol.md), but no participant results are invented. The rollout decision remains on hold until at least four of five real participants independently choose My Classes for recurring work and Quick Create for one-off work.
