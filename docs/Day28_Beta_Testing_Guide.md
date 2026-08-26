# TeacherOS Day 28 — Real Teacher Beta Test

## Objective

Test TeacherOS with 10 real English teachers and record where they become confused, blocked, or disappointed.

Day 28 is not for adding new features. The goal is to collect evidence that tells you what to fix on Day 29.

## Fast feedback flow

TeacherOS now uses a one-tap rating flow:

1. The tester opens **Account → Rate TeacherOS** or sends `/feedback`.
2. They choose one rating from **Very frustrating** to **Excellent**.
3. Ratings 2–5 are saved immediately. A comment is optional.
4. Only **Very frustrating** requires a short explanation.

The rating is saved automatically in the database. The owner can review reports under **Account → Admin → Feedback** and mark them **Reviewed** or **Resolved**.

## Recruit 10 testers

Choose English teachers who actually prepare lessons or classroom materials. A useful mix is:

- 3 private tutors
- 3 language-institute teachers
- 2 online teachers
- 2 school or university teachers

Do not recruit only close friends who will praise the product. Ask them to be direct.

## Tester mission

Each tester should complete these tasks without you explaining where every button is:

1. Open `@Teacheros1_bot` and send `/start`.
2. Create one B1 lesson plan about travel.
3. Create one speaking activity about technology.
4. Create one vocabulary worksheet about food.
5. Create one short grammar assessment about the present perfect.
6. Open Library and find one generated item.
7. Search for one topic they used.
8. Open Account and inspect Usage and My Plan.
9. Rate TeacherOS using **Account → Rate TeacherOS** or `/feedback`.

The four generations fit inside the default Free plan's daily allowance.

## What you must observe

Do not immediately help the tester. Write down:

- The first button they hesitate over
- Any wording they misunderstand
- Any Back button they look for
- Any result they think is too long, weak, or unusable
- Any feature they expect but cannot find
- Any error message
- The task they abandon
- How long the full mission takes

## Severity rules

- **Critical:** The bot crashes, loses data, exposes private data, charges incorrectly, or the tester cannot continue.
- **High:** A core generator, Library, Search, or export does not work.
- **Medium:** The tester can continue but needs help or misunderstands the interface.
- **Low:** Cosmetic issue, minor wording problem, or optional improvement.

## Day 28 success criteria

- 10 real teachers start the test.
- At least 8 complete the full mission.
- Every tester submits an in-bot rating.
- No Critical issue remains undocumented.
- You can name the three most frequent problems.
- You do not add unrelated features before reviewing the evidence.

## Owner review

In Telegram:

1. Send `/start`.
2. Open **Account**.
3. Open **Admin**.
4. Tap **Feedback**.
5. Read each report.
6. Tap **Review** when you have examined it.
7. Tap **Resolve** only after the problem is actually fixed.

To export all reports:

```bash
python backend/export_beta_feedback.py
```

The CSV file will appear here:

```text
exports/beta_feedback.csv
```

## Day 29 decision rule

Fix problems in this order:

1. Critical issues
2. High-severity issues reported by multiple testers
3. The most common confusion point
4. Output-quality complaints repeated by multiple testers
5. Medium and Low issues

Do not build a new feature because one tester casually suggests it. Add it only when it supports the core TeacherOS workflow and multiple users need it.
