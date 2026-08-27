# Day 5 — Safe class memory foundation

Day 5 ships schema version 6 and an owner-scoped service layer behind disabled-by-default feature flags. It does not add a Classes button or change the six-button Quick Create home screen.

## Delivered

- Additive, repeatable schema migration for `classes`, `class_objectives`, `class_lessons`, `lesson_outcomes`, and `product_events`.
- Nullable `materials.class_id`, preserving every legacy material and caller.
- Foreign keys, explicit status checks, UTC timestamps, ownership-aware composite indexes, and database-level cross-owner link guards.
- `class_service.py`, whose class-ID operations always require the requesting Telegram user.
- Independent flags for classes, continuity, evidence, differentiation, reports, and entitlements.
- Empty, legacy-v5, populated-v5, and real-populated-v5-copy migration rehearsals, each applied twice.

## Acceptance result

| Gate | Result |
|---|---|
| No lost legacy rows or changed legacy data | Pass |
| No duplicate columns | Pass |
| No foreign-key violations | Pass |
| User B cannot read, modify, archive, link to, or infer User A's class | Pass |
| Word and PDF exports survive migration | Pass |
| Quick Create remains default with Classes off | Pass |
| Rollback requires no destructive down migration | Pass |

The machine-readable evidence is in `outputs/day05/migration_report.json`. It contains counts and schema hashes only—never user identifiers or content.

See [Migration_and_Rollback.md](Migration_and_Rollback.md) for the operator runbook and [Schema_Contract.md](Schema_Contract.md) for data and ownership rules.
