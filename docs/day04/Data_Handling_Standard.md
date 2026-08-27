# TeacherOS Day 4 Data Handling Standard

Status: pre-pilot contract. Technical enforcement is required before student evidence is enabled.

The authoritative machine-readable rules are in `contracts/day04/data_policy.json`. When product copy, code, provider terms, and this standard disagree, processing must fail closed until the conflict is reviewed.

## Classification decision

Classify a field by its most sensitive possible value, not its table or screen. Combining low-risk fields can raise the classification. A private class label is class context even if it resembles public text; an API key remains a secret even when accidentally pasted into evidence.

| Class | Typical examples | Default retention | Logging | Backup | LLM/provider rule |
|---|---|---|---|---|---|
| Public product data | Help, public templates, plan names | Current life plus source history | Allowed without private concatenation | Normal code/config backup | May be sent if needed |
| Teacher account data | Internal user ID, Telegram ID, subscription, payment reference | Account life; limited billing exceptions | IDs, handles, tokens, URLs, and support free text prohibited | Encrypted; deletion reconciled within 30 days | Never send account identifiers to an LLM |
| Class context | CEFR band, cadence, goal, approved outcome | Until class/account deletion; review inactive classes after 12 months | Random IDs and bounded enums only | Encrypted; tombstones replayed on restore | Minimum approved fields; replace class label with random reference |
| Student evidence | Anonymized work, observations, approved extraction | Raw: 7 days Free, 30 Pro, 90 Premium unless shorter | Content, filenames, OCR, URLs, prompts, responses prohibited | Excluded from general backups | Consent first; no-training/zero-retention where supported; untrusted data only |
| Secret | Bot/API keys, callback tokens, encryption keys | Operational minimum; rotate on incident/change | Always prohibited | Excluded from code/database backups | Only to the authenticating service, never AI/analytics |

## Collection and consent

1. The feature works without evidence; upload is optional.
2. Before upload, state the purpose, provider processing, retention choice, deletion behavior, and AI limitations.
3. Require an affirmative, unbundled consent action. No preselected consent.
4. Warn the teacher to remove names, faces, contact details, IDs, health/disability details, and unrelated writing.
5. Reject unsupported files and obvious secrets before persistence or provider transmission.
6. Record consent version, purpose, retention choice, class/evidence random IDs, and UTC time—never evidence content in the consent event.

## Processing boundary

- Run ownership, consent, file-type/size, malware, secret/identifier, and retention checks before transmission.
- Construct prompts from fixed system instructions plus a delimited `UNTRUSTED_EVIDENCE` block.
- Evidence cannot select tools, alter policy, request secrets, change approval state, or become a system/developer message.
- Tool execution is disabled for evidence analysis.
- Store provider request ID, model ID, latency, token counts, bounded status, and content hash only. Do not store prompts/responses in analytics or evaluation output.
- A model output is a draft. Deterministic validation occurs before the teacher sees or approves it.

## Retention and deletion

The privacy-conscious default is short raw-evidence retention by plan: 7/30/90 days. Teachers can choose shorter retention or immediate deletion. Longer retention is never silently selected after upgrade.

Raw evidence deletion removes the object, OCR text, thumbnails, temporary files, signed URLs, and processing caches immediately. Deleting an approved summary invalidates dependent unapproved diagnoses/follow-ups. General backups exclude raw evidence. Class/account tombstones are replayed before any restored database becomes reachable.

## Logging and observability

Allowed: random internal IDs, operation, model identifier, schema version, consent state, bounded file-size/type bands, latency, token counts, error class, check results, hashes, and UTC timestamps.

Prohibited: Telegram IDs/handles, teacher or class labels, student names, filenames, evidence/OCR, free text, prompts, responses, signed URLs, authorization headers, callback tokens, payment URLs, and secrets. Exceptions are not approved through debug flags; they require an incident-scoped, access-controlled design review.

## Provider approval checklist

- Purpose and exact transmitted fields documented.
- No-training control/terms confirmed.
- Retention and deletion terms documented and within disclosed TeacherOS limits.
- Regions and subprocessors recorded.
- TLS, access control, incident notification, deletion support, and security review complete.
- Zero content logging verified in application and provider configuration.
- Failure/refusal/timeout behavior tested.
- Provider change has an owner, rollback, and teacher-notice decision.

Until every item is approved, `evidence_review_v1` stays off.
