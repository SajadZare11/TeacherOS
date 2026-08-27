# TeacherOS Day 4 Incident Playbook

Status: pre-pilot operational contract. Use UTC in every incident record. Never paste evidence, prompts, secrets, payment credentials, or teacher/student identifiers into tickets or chat.

## Severity and authority

| Severity | Definition | Initial response | Authority |
|---|---|---|---|
| SEV-0 | Confirmed/credible cross-user or secret exposure; widespread harmful final decisions; systemic billing harm | Immediate containment, owner paged now | Incident commander may disable bot/provider/payment and revoke credentials |
| SEV-1 | Private-data exposure with bounded scope; safety invariant bypass; duplicate/incorrect charge | Contain within 30 minutes | Incident commander plus privacy/billing owner |
| SEV-2 | Harmful draft caught before approval; prolonged AI outage; deletion/retention job failure without confirmed exposure | Triage within 4 hours | Engineering owner |
| SEV-3 | Recoverable isolated quality or availability issue | Next business day | Feature owner |

Safety beats availability. The responder may disable a feature flag or provider without waiting for product approval. Preserve export and deletion access wherever technically safe.

## Universal first 30 minutes

1. Open an incident ID containing only date, severity, and random sequence.
2. Assign incident commander, technical lead, communications lead, and privacy/billing specialist as applicable.
3. Stop expansion: disable the narrowest safe flag/provider/route; revoke exposed secrets before investigation.
4. Preserve score-only logs, hashes, request IDs, UTC times, code/model/config versions, and access records. Do not copy raw content into the incident system.
5. Determine commit certainty and affected object-ID ranges using server-side queries with least privilege.
6. Block destructive cleanup until preservation needs are decided, except immediate credential revocation and access containment.
7. Start a decision log: UTC time, actor role, action, evidence ID/hash, and result.
8. Set the next update time and notification decision owner.

## Scenario A — data exposure or cross-user access

Triggers include wrong-owner content, evidence/prompt in logs, signed-URL leak, provider transmission without consent, secret exposure, or failed deletion.

Contain:

- Disable the affected read/mutation/evidence/provider path.
- Revoke signed URLs, sessions, callback tokens, and credentials that could expand access.
- Stop log export and backup replication if they contain exposed content; preserve originals under restricted incident custody.
- Run owner-bound queries to determine affected internal IDs. Do not contact accounts until identity mapping is independently checked.

Investigate and recover:

- Reproduce with synthetic accounts only.
- Identify first/last exposure, data classes, actors/providers, access/download evidence, backup/log copies, and deletion implications.
- Patch ownership/consent/redaction; add a regression test matching the failure.
- Purge unauthorized copies through application, cache, object store, analytics, provider, and backup-deletion workflows; retain legally required incident evidence in restricted form.

Notify:

- Privacy lead decides regulatory/provider/user notifications using applicable law and verified scope.
- Teacher notice states what happened, data classes, date range, containment, actions available, and contact route; do not speculate or expose another user.

Exit requires zero unauthorized access in regression tests, credential rotation, deletion reconciliation, notification decision, and signed owner/privacy approval.

## Scenario B — incorrect billing

Triggers include duplicate charge, wrong amount/currency/plan, paid-without-entitlement, entitlement-without-verified-payment, or quota charged after failed generation.

Contain:

- Disable the affected payment/settlement action, not account data controls.
- Preserve provider reference, internal order ID, amount/currency, idempotency result, and timestamps; never store card/bank credentials.
- Stop automated retries that could create another charge.

Recover:

- Reconcile provider status against local order/subscription in both directions.
- Correct entitlement without requiring another payment. Refund through the verified provider workflow when owed.
- Notify affected teachers with amount, currency, reference, action, expected settlement time, and support path.
- Add duplicate callback, amount/currency, sandbox/live, and atomic entitlement regression tests.

Exit requires provider/local reconciliation, affected teachers remedied, no duplicate settlement path, and billing-owner approval.

## Scenario C — harmful or unsupported output

Triggers include discriminatory/age-inappropriate material, unsafe instruction, answer-key error with material impact, injection success, or any final grade/diagnosis/mastered/secure/grouping claim without teacher approval.

Contain:

- Disable the affected model/prompt/feature flag and prevent cached output reuse.
- Mark dependent unapproved diagnoses/follow-ups invalid. Do not silently alter an already accepted teacher artifact; show a clear warning and revision option.
- Preserve response hash, case/teacher report random ID, model/prompt/schema versions, and validator results—raw content only in restricted evidence custody if necessary.

Recover:

- Reproduce with an artificial minimal case.
- Update deterministic rule, prompt boundary, schema, model routing, or refusal behavior.
- Add the case to the golden set without real content and rerun all 40 cases.
- If classroom use may have occurred, provide a plain correction and safe replacement; do not blame the teacher.

Exit requires all safety invariants at 100%, relevant human pedagogical review, affected-user decision, and Trust approval.

## Scenario D — unavailable AI service

Triggers include outage, timeout, rate limit, empty/malformed output, or unknown completion state.

Contain and recover:

- Keep the teacher's draft and state explicit commit certainty.
- Retry unknown requests with the same idempotency key; never consume quota twice.
- Offer retry later, editable manual/legacy workflow, and Home/Back actions.
- Disable only the failing provider/model where a tested safe fallback exists. Do not silently route private evidence to a provider with different terms.
- Publish status when user impact is sustained; avoid promising a restoration time without evidence.

Exit requires a successful synthetic health check, backlog/idempotency reconciliation, no duplicate quota/material records, and monitored gradual re-enable.

## Scenario E — suspected secret exposure

This is handled as data exposure at SEV-0/1. Revoke and rotate first. Search repository history, logs, artifacts, backups, CI, tickets, provider dashboards, and running processes by secret fingerprint/name without printing the value. Validate old credentials are rejected and new credentials are scoped. Never merely delete the visible copy while leaving the credential valid.

## Post-incident requirements

- Timeline and root cause use roles/random IDs, hashes, counts, and timestamps only.
- Record contributing controls, why detection did or did not work, and the exact regression test.
- Assign corrective actions with owner, due date, verification evidence, and rollback.
- Review provider/teacher notification, retention, deletion, backup, billing, and support implications.
- Re-enable only through the normal flag ladder; SEV-0/1 requires a written go/no-go decision.
