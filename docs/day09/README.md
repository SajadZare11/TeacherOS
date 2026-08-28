# Day 9 — Shared AI context, validation, and provenance

Day 9 replaces product-level direct model calls with one bounded pipeline:

`request → structured JSON → schema validation → pedagogical validation → one repair → safe failure or render`

## Shipped architecture

- `class_context.py` builds owner-scoped context for quick-create or a verified class. It includes profile, teacher-saved current objectives, recent lessons and approved outcomes, due review, the evidence-workflow availability state, recent material formats, fixed safety constraints, and the current request.
- Context lists have fixed recency caps, free text is clipped, every missing value is explicitly `unknown` or `not_available`, and the serialized context is reduced to a deterministic token budget.
- `prompt_contracts.py` owns feature contracts, versions, prompt loading/replacement, the strict JSON response contract, and repair instructions.
- `validators.py` requires exactly `{"content": "..."}`, applies length/section checks, rejects prompt-trace leakage, and exposes content only when both validation stages pass.
- `ai_gateway.py` owns OpenRouter routing, a 24-second total deadline, one transient-provider retry, one validation repair, telemetry aggregation, and the final render boundary.
- `ai_audit.py` stores only hashes, controlled source record IDs, provider/model, status, attempts, latency, token counts, and cost when the provider returns it. It has no prompt, response, content, or reasoning column.
- Schema v9 adds owner-scoped `ai_generation_audits` with database-level cross-owner protection.
- Lesson, activity, worksheet, assessment, and general-chat model calls now all enter through the shared gateway. The four generators keep their confirmation state after failure; general chat tells the teacher to resend the still-visible message.

## Safety and privacy decisions

- Class display names, learner identities, outcome notes, saved material content, raw prompts, raw responses, and hidden reasoning are not written to AI audit logs.
- Current objectives are treated as approved only when they are teacher-saved and have `status='current'`.
- Only outcomes with `status='approved'` enter context.
- Evidence summaries remain explicitly unavailable until the evidence workflow exists; Day 9 does not invent a future table or evidence.
- Missing and unauthorized class IDs produce the same unavailable outcome.
- Malformed or pedagogically invalid output is repaired once. A second failure raises a controlled error; invalid text is never returned to a teacher-facing handler.

## Verification

The automated suite covers empty, normal, very long, unauthorized, adversarial, and mixed-language contexts; paired-user isolation; schema migration/idempotency; audit privacy; strict JSON; pedagogical rejection; one repair; safe failure; provider retry; centralized routing; and visible retry preservation.

Engineering gate: **PASS** (72 automated tests).

The gateway enforces schema-valid display and a 24-second internal deadline against the plan's under-25-second target. Production p95 remains **NOT_RUN** because no live teacher generation sample was supplied or fabricated; the v9 audit table now captures the latency required to calculate it honestly.

## Operational commands

```powershell
python backend/day9_ai_pipeline_check.py
python -m unittest discover -s tests -v
python backend/check_project.py
```

The machine-readable result is written to `outputs/day09/pipeline_report.json`.
