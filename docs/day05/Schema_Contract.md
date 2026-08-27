# Schema v6 contract

## Ownership invariant

Every class-scoped row carries `user_id`. Composite foreign keys bind objectives and lessons to `(class_id, user_id)` and outcomes to `(class_lesson_id, class_id, user_id)`. Triggers apply the same rule to optional material and event links.

The service never fetches or mutates a class using a class ID alone. It also requires the requesting Telegram user ID. Missing and unauthorized IDs produce the same `None` or `False` result, preventing class-existence inference.

Database trigger failures use the generic message `ownership mismatch`; they do not reveal which referenced record exists.

## Tables

| Table | Purpose | Explicit lifecycle/status |
|---|---|---|
| `classes` | Stable teacher-owned class profile | `active`, `archived` |
| `class_objectives` | Prioritized learning objectives | `current`, `met`, `paused`, `archived` |
| `class_lessons` | A class-specific lesson record, optionally linked to a material | `draft`, `planned`, `taught`, `cancelled`, `archived` |
| `lesson_outcomes` | Structured result and support signal for a class lesson | `draft`, `saved`, `approved`, `archived` |
| `product_events` | Idempotent product/operational event record | `pending`, `delivered`, `failed` |

All newly generated timestamps use UTC ISO-8601 text ending in `Z`. Optional externally supplied timestamps remain text so later rollout days can define their exact UI contract without rewriting Day 5 data.

## Compatibility

- Existing material inserts omit `class_id`; SQLite stores `NULL`.
- Existing material queries and exports continue to work without class awareness.
- Deleting a class nulls direct material links and deletes its class-owned objectives and lessons according to their foreign-key rules.
- `event_uuid` is unique, making product-event writes idempotent.
- Schema version is 6.
