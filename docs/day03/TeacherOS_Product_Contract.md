# TeacherOS Day 3 Product Contract

Status: **buildable draft; not approved for class-intelligence implementation**

Date: 2026-08-26

Authoritative machine-readable sources: `contracts/day03/product_contract.json` and `contracts/day03/screens.json`

## 1. Decision status

This document freezes the product mechanics, safety boundaries, measurement language, navigation contract, and rollout gates for the flagship loop. It does not claim customer validation.

The Day 2 evidence gate is closed: zero eligible interviews and zero confirmed pilot recruits are recorded. The target segment, anti-segment, jobs, willingness to pay, and class-loop limits therefore remain hypotheses. Class-intelligence flags stay off until the gate opens. Safety, privacy, ownership, measurement, rollback, and deletion work can be specified now because they control risk rather than assert teacher preference.

## 2. Frozen promise

> TeacherOS remembers each class, turns evidence into the next best teaching action, and produces classroom-ready English materials in minutes—under teacher control.

Every phrase is testable:

- **remembers each class:** saved context is reused and can be reviewed, corrected, exported, or deleted by its owner;
- **turns evidence into the next best teaching action:** evidence is converted only into a proposal, never an autonomous fact or decision;
- **classroom-ready English materials:** the output can be used or edited by a teacher, not merely admired as prose;
- **in minutes:** elapsed and active time are measured without fabricating time saved;
- **under teacher control:** the teacher approves extracted evidence and diagnosis, chooses the follow-up, and controls deletion.

## 3. User and job hypotheses

The provisional beachhead is an independent English teacher who teaches at least two recurring lessons per week, uses Telegram daily, and personally plans or adapts materials. This definition must be replaced or confirmed by Day 2 evidence.

The provisional anti-segment is a teacher who has no recurring class continuity, cannot use Telegram during preparation, or is required to use centrally prescribed materials without adaptation. TeacherOS may still help them through legacy one-off generators, but the flagship loop is not designed around them.

Hypothesized jobs, in priority order:

1. Reuse accurate class context without retyping it.
2. Produce the next usable lesson/resource quickly.
3. Capture what happened without writing a long report.
4. Turn trustworthy evidence into a teacher-approved adjustment.
5. Carry that adjustment into the next lesson and preserve continuity.

No job is considered validated until it maps to repeated witnessed behavior in the Day 2 workbook.

## 4. Flagship closed loop

The unit of value is one completed teaching loop for one teacher-owned class:

`class setup → plan → teach → 30-second outcome → evidence → approved diagnosis → follow-up → next lesson`

A loop begins when a class resource is associated with a new `loop_id`. It becomes complete exactly once when an accepted follow-up is attached to a durably saved next lesson for the same class. Downloading a resource, opening a screen, uploading evidence, or merely generating a diagnosis does not complete a loop.

### Stage acceptance

| Stage | Durable result | Teacher control | Failure-safe behavior |
|---|---|---|---|
| Class setup | Minimal class profile | Review/edit/delete | Draft resumes; duplicate creates are prevented |
| Plan | Versioned resource tied to class and loop | Edit brief, regenerate, accept | Unknown generation result retries idempotently |
| Teach | Explicit taught status and optional date | Teacher confirms; never inferred | Repeated tap opens the saved outcome step |
| 30-second outcome | Structured, bounded result | Review/edit before evidence approval | Draft persists; no essay required |
| Evidence | Consented upload or structured counts plus approved extraction | Approve/edit/reject/delete | Insufficient extraction creates no finding |
| Approved diagnosis | Versioned proposal tied to approved evidence | Approve/edit/reject | Unapproved proposal cannot affect planning |
| Follow-up | Accepted teacher action | Accept/edit/reject | Rejection makes no class mutation |
| Next lesson | New resource with accepted follow-up attached | Detach or edit brief | Completion uses an idempotent outbox event |

## 5. Experience and navigation contract

The canonical wireflow and state inventory are in `Telegram_Wireflow.md` and `contracts/day03/screens.json`.

Rules:

1. Home foregrounds **My Classes** when `classes_v1` is enabled. Existing lesson, activity, worksheet, assessment, search, account, and payment surfaces remain available during rollout.
2. Telegram asks at most one short free-text question per message. Level, cadence, learner-count band, outcomes, and decisions use buttons. Saved class context is reused. A future Telegram Web App may improve multi-field editing but is not an MVP dependency.
3. Every screen has an inline Back, Cancel, Done, or Main menu route. `/start` and other commands are accelerators, never escape hatches.
4. Draft state survives validation and transient service errors when safe. Every progress state terminates in success, a specific retry, or a safe parent screen.
5. Destructive actions and AI-derived diagnoses require explicit confirmation. Opening, downloading, or exporting never implies teaching, evidence approval, or diagnosis approval.
6. A stale, unauthorized, missing, or revision-mismatched callback reveals no private object details and routes to a fresh recovery keyboard.

### Compact callback contract

New class-loop callbacks use:

`v1|<domain>|<action>|<base36_object_id>|<base36_revision>`

The payload is a locator, not authority. Object ownership and revision are checked server-side. Payloads remain below Telegram's 64-byte limit. Mutations are idempotent. The existing underscore callbacks remain supported while legacy screens are migrated; new class-loop code must not add another callback grammar.

## 6. Scope

### In scope for the class-loop MVP

- Teacher-owned class profile with a minimal editable context and timeline.
- A class-aware planning brief that reuses saved context.
- Versioned generated resource and explicit **Mark taught** action.
- A structured outcome designed for completion in roughly 30 seconds.
- Optional evidence consent, upload/manual counts, extraction review, and deletion.
- Diagnosis as an editable teacher-approved proposal, never an autonomous label.
- Editable/rejectable follow-up attached to the next lesson.
- Complete, privacy-bounded funnel events and north-star measurement.
- Default-off flags, per-object ownership, stale-state recovery, export, downgrade, and deletion behavior.
- Compatibility with existing generators, library, account, Free/Pro/Premium subscription, and payment foundation.

### Explicit non-goals

- Student accounts, parent portals, direct student messaging, attendance, grading, or a school LMS.
- Automatic diagnosis, high-stakes assessment, clinical/special-education inference, or claims about a learner's ability.
- Biometric, emotion, face, or voice identification.
- Storing student names or unredacted evidence by default.
- Autonomous changes to a class profile or next lesson.
- A general chat assistant or broad curriculum marketplace.
- Replacing the existing payment provider, exports, or legacy generators during the first class-loop rollout.
- Enforcing proposed class-loop price limits before willingness-to-pay evidence.
- Counting synthetic tests, sandbox payments, generated resources, or uploads as teacher value.

## 7. Functional requirements

### Identity and ownership

- Every class-loop object belongs to an internal user and ultimately to one `class_id`.
- Reads and mutations join through the authenticated Telegram user; callback IDs alone confer no access.
- Child objects cannot be reparented across teachers. Logs do not contain Telegram IDs, names, class labels, prompt text, generated text, or evidence content.

### Data model contract

The implementation must support version/revision and timestamps for: class, loop, resource, outcome, evidence, evidence extraction, diagnosis, follow-up, and deletion job. Evidence, diagnosis, and follow-up retain explicit status transitions. A diagnosis references the exact approved evidence version; a follow-up references the exact approved diagnosis version.

### AI boundary

- Class context is assembled from explicit saved fields and approved prior objects only.
- Uploaded evidence is not used until consent is recorded; extracted content is not used until approved.
- The model produces proposals with uncertainty and traceable source-version references.
- Unsafe, insufficient, or conflicting evidence produces a neutral failure state, not a confident invention.
- Teacher edits are first-class versions and are never silently overwritten by regeneration.

### Reliability

- Creation, generation commit, taught marking, outcome save, approval, acceptance, deletion, and loop completion are idempotent.
- A transactional outbox separates durable product state from analytics delivery.
- Timeouts disclose whether a commit is known, failed, or unknown. Unknown mutations retry with the same key.
- Feature rollback does not delete data or make export/deletion inaccessible.

## 8. Analytics and success criteria

The north-star metric is **weekly completed teaching loops**, counted as distinct `loop_id` values producing `loop_completed` in a seven-day UTC window.

The activation funnel is fixed before feature code:

1. `class_created`
2. `class_resource_generated`
3. `lesson_marked_taught`
4. `outcome_saved`
5. `evidence_approved`
6. `followup_accepted`
7. `loop_completed`

Event definitions, timestamps, owners, properties, privacy classes, retention, deduplication, and prohibited fields live in `product_contract.json`. Funnel reporting must show eligible denominators, step conversion, median time between steps, and the percentage of users/classes affected by each flag variant. Do not infer causality from a small pilot.

Only work reasonably expected to improve one or more of these measures is approved: activation, weekly completed teaching loops, verified time saved, trust, retention, or paid conversion. Trust is a constraint, not a vanity score: unauthorized access, unapproved diagnosis application, consent bypass, or failed deletion is a stop-ship incident.

### Working metric definitions

- **Activation:** an eligible new teacher reaches `class_resource_generated` within seven days of `class_created`; also report stricter first-loop activation separately.
- **Verified time saved:** teacher-confirmed bounded comparison captured by `time_saved_verified`; never calculate it merely from response latency.
- **Trust:** teacher-control usage and correction rates plus incident-free denominators; a correction is not automatically a failure.
- **Retention:** eligible teacher has `loop_completed` in two distinct rolling weeks; report small cohorts as counts and percentages.
- **Paid conversion:** non-sandbox `subscription_activated` divided by eligible teachers exposed to the relevant paid proposition.

## 9. Privacy, retention, and deletion

Analytics never contains raw prompt text, generated material, teacher/class names, Telegram IDs, free text, or student evidence. Internal random IDs connect product events. Raw evidence storage is separated from analytics and encrypted with least-privilege access.

The full deletion matrix is machine-readable in `product_contract.json`. Key behavior:

- resource deletion is owner-only and confirmed;
- raw evidence deletion removes blobs, OCR text, thumbnails, and caches immediately;
- deleting an approved summary invalidates dependent unapproved proposals;
- class deletion explains the cascade and offers a choice for independently saved resource copies;
- downgrade never deletes content; excess classes are read-only but exportable/deletable;
- account deletion revokes access immediately and completes purge/anonymization within 30 days;
- retained billing/audit records are minimized and irreversibly separated from product identity where legally required.

Existing material deletion already checks teacher ownership and requires confirmation. Class, evidence, account, cascade, and analytics deletion are specifications—not claims about current implementation.

## 10. Plans and entitlements

Current behavior is the baseline: Free permits 10 successful generations per configured usage day; Pro and Premium have no daily generation cap; Premium can use a configured priority model. Existing prices and durations remain configuration, not product research evidence.

The proposed class-loop limits in `product_contract.json` are pricing hypotheses. They remain unenforced behind `class_entitlements_v1` until Day 2 willingness-to-pay evidence, sandbox/live billing tests, disclosure copy, downgrade tests, and rollback checks pass. Quotas are consumed only after durable success. Sandbox subscriptions never count as paid conversion.

## 11. Feature flags and rollout

All eight class-intelligence flags default to off. Dependencies enforce this order:

`classes → class planning → teach/outcome → evidence review → diagnosis approval → follow-up`

Analytics and class entitlements are independently reversible. Rollout order is owner account, internal/synthetic evaluation, explicit pilot allowlist, then percentage rollout. Disabling a flag preserves readable/exportable/deletable teacher data and leaves legacy generation available.

## 12. Release gates

No class-intelligence implementation or pilot is approved until the relevant gates in `product_contract.json` pass.

Current state:

- **G1 Research — BLOCKED:** Day 2 is closed.
- **G2 Comprehension — PENDING:** no eligible teacher has completed the unaided wireflow test.
- **G3 Navigation — SPECIFIED:** machine-checkable contract exists; implementation tests are future work.
- **G4 Analytics — SPECIFIED:** event catalog is machine-checkable; emission code is future work.
- **G5 Trust — PENDING:** consent, access, evaluation, retention, and deletion implementation are not complete.
- **G6 Value — PENDING:** no pilot value evidence exists.
- **G7 Rollback — SPECIFIED:** default-off flags and rollback outcomes are defined; drill is future work.

The contract is structurally ready for review, but approval remains blocked. The Day 3 validator must not relabel research or comprehension as complete.

## 13. Teacher comprehension acceptance test

Use one eligible independent teacher at minimum; target three before implementation freeze. Do not coach or explain until the test ends.

1. Show only the wireflow and screens, starting at Home.
2. Ask: “What do you think this home screen is for?”
3. Ask the teacher to narrate what happens from creating a class through the next lesson.
4. Point to outcome, evidence, diagnosis, and follow-up in a shuffled order and ask who controls each change.
5. Ask how they would go back from evidence upload, recover an expired screen, reject a diagnosis, and delete evidence.
6. Ask what they believe is stored and whether uploading evidence is required.
7. Record only anonymous ID, eligibility, pass/fail per task, observed confusion, and suggested copy changes. Keep names/recordings outside Git.

Pass requires an unaided correct explanation of Home and all eight loop stages, plus correct identification of Back, reject, consent/optional evidence, and delete controls. A failure changes the wireflow/copy and requires a fresh test; it must not be reframed as validation.

## 14. Open decisions

- Confirm or replace target/anti-segment and top jobs from Day 2 evidence.
- Decide whether evidence is common enough for the core activation path or should be an optional advanced branch.
- Validate the 30-second outcome with observed completion time.
- Validate plan limits, retention promises, and willingness to pay.
- Choose exact allowed evidence formats and maximum sizes after threat modeling and cost testing.
- Decide whether class setup needs a Telegram Web App after observing setup friction; do not pre-build it.

## 15. Approval record

| Role | Required decision | Current state |
|---|---|---|
| Research | Day 2 evidence gate | Blocked |
| Product | Promise, loop, scope, comprehension | Draft / comprehension pending |
| Trust | Consent, evidence boundary, deletion | Draft |
| Engineering | callbacks, ownership, flags, rollback | Specified, not implemented |
| Data | event schema and privacy enforcement | Specified, not implemented |
| Billing | class entitlements and downgrade behavior | Hypothesis / disabled |
