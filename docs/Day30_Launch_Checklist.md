# TeacherOS Day 30 — Progressive Launch Checklist

Day 30 is a controlled pilot launch, not a claim of product-market fit. The
operator must complete the checks below before inviting teachers and record the
decision in the pilot tracker.

## 1. Prepare a recoverable release

Run these commands from the project root:

```bash
python backend/backup_teacheros.py --label day30-prelaunch
python backend/check_project.py
python website/check_website.py
python backend/launch_check.py --mode beta
```

The backup command verifies SQLite integrity before returning success. Keep the
backup path in the operator log. Do not commit `.env`, database files, or tokens.

For a real paid launch, use `--mode paid` only after replacing every production
placeholder, configuring a public HTTPS callback, disabling both sandbox flags,
and completing a verified payment test. Sandbox mode must remain enabled for the
beta cohort.

## 2. Invite progressively

1. Enable the class-loop feature flags in the deployment environment.
2. Invite five teachers first and run the complete mission: create a class, save a
   class-aware material, plan and teach a lesson, record the outcome, capture
   limited anonymized evidence, review/approve the rationale, use a follow-up, and
   export an approved report.
3. Give each teacher the [Day 28 mission](Day28_Beta_Testing_Guide.md) and the
   [privacy notice](../website/privacy.html). Never ask for learner names or
   sensitive identifiers.
4. Invite the remaining 5–10 teachers only after the first five complete their
   onboarding without a Critical or P1 defect.

## 3. Monitor every day

Record aggregate values from **Account → Admin** and the pilot tracker:

- weekly verified teaching loops (the north-star metric);
- class activation within 24 hours;
- outcome recording, evidence-to-follow-up, and week-two return;
- median verified minutes saved per active teacher;
- approval/correction rates and unsupported-claim incidents;
- p95 generation latency, provider errors, model cost, and payment outcomes;
- privacy, deletion, billing, and support incidents;
- the step where each drop-off occurred (setup, planning, teaching, outcome, or
  follow-up).

Schedule neutral interviews on Day 3, Day 7, and Day 14. Contact drop-offs at the
step where they stopped; do not coach them into a positive answer or hide a
usability failure.

## 4. Day 14 decision gate

Use observed cohort data, never fixture results. Continue scaling only if all of
these are true:

- at least 10 teachers invited, 7 classes created, 5 complete a verified loop;
- at least 4 return in week two and 3 use evidence-to-action;
- median reported time saved is at least 30 minutes per active teacher/week;
- at least 3 teachers say they would be very disappointed to lose TeacherOS;
- at least 2 show genuine willingness to pay or prepay;
- zero severe privacy, reliability, or billing complaints remain unresolved.

If a threshold fails, choose one explicit outcome: scale the loop, repair the
named bottleneck, reposition the segment, or stop/defer the feature. Do not claim
“number one”, product-market fit, automatic mastery, objective grading, or
universal time savings from a 10–15 teacher pilot.

## Automated gate

```bash
python backend/day30_acceptance_check.py
```

This offline gate checks the launch files, release diagnostics, backup integrity,
privacy/terms links, pricing drift protection, and the Day 14 decision thresholds
in this checklist. It writes `outputs/day30/acceptance_report.json` and must print
`DAY 30 ACCEPTANCE: PASS`.
