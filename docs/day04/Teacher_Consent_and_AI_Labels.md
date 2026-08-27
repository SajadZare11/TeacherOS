# Teacher Consent, Anonymization Warning, and AI Labels

Status: draft for comprehension, privacy, and legal review. These strings are not yet displayed in the bot.

## Evidence consent screen

**Help TeacherOS suggest your next teaching step (optional)**

You can add anonymized student work or simple class counts. TeacherOS will send only this evidence and the minimum approved class context to its AI provider to create a draft extraction and follow-up suggestion.

Before uploading, remove names, faces, usernames, contact details, student IDs, school identifiers, health/disability information, and any writing unrelated to this lesson. Do not upload confidential records or secrets.

Your default raw-evidence retention is shown before confirmation. You can choose a shorter period or delete the evidence immediately after review. Uploading is optional; you can continue without evidence.

Buttons:

- `I understand — choose evidence`
- `Continue without evidence`
- `Back`

Consent is not complete until the teacher chooses a retention period and taps `Confirm and process` on the review screen.

## Retention confirmation

**Review before processing**

- Purpose: create a teacher-reviewed evidence summary and follow-up proposal for this class.
- Raw evidence: delete after review / 24 hours / plan default shown as an exact date and time.
- Approved summary: keep with this class until you delete it or the class.
- Provider: show provider name, model family, provider retention/training statement, and link to current details.

`Confirm and process` means the teacher has reviewed the anonymization warning and agrees to this specific processing. Changing purpose, provider, or retention beyond what was shown requires fresh consent.

## Evidence extraction label

**AI draft — check against the original**

TeacherOS may miss, misread, or invent details. Edit or reject this extraction. It will not be used for a diagnosis or follow-up until you approve it.

## Diagnosis label

**Teaching hypothesis — not a fact, grade, or diagnosis**

This AI proposal is based only on the approved evidence listed below. It cannot establish that a learner has mastered, is secure in, or is unable to learn a skill. It cannot make a high-stakes grade or permanent learner group. Approve, edit, or reject it before it affects the next lesson.

## Follow-up label

**Suggested teaching action — teacher decides**

Check the objective, evidence links, classroom fit, age appropriacy, time, and materials. Nothing changes in the next lesson until you accept or edit this suggestion.

## Generated-material label

**AI-generated draft**

Review accuracy, answer keys, timing, instructions, level, cultural suitability, and safeguarding before classroom use. TeacherOS supports preparation; it does not replace professional judgment.

## Failure and insufficient-evidence copy

**TeacherOS could not produce a reliable draft**

No diagnosis or learner claim was created. You can review the evidence, enter anonymous structured counts, try again later, delete it, or continue without evidence.

## Deletion confirmation

**Delete this evidence?**

TeacherOS will permanently delete the raw file, extracted text, thumbnails, and processing cache. If you also delete the approved summary, any unapproved diagnosis or follow-up that depends on it will be invalidated. This cannot be undone.
