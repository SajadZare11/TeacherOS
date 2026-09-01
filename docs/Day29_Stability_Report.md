# TeacherOS Day 29 — Stability and UX Fixes

## Objective

Fix defects and remove dead ends. Do not add unrelated product features.

## Fixes included

1. **Generator retry without re-entering data**
   - Lesson, Activity, Worksheet, and Assessment choices stay saved when OpenRouter fails.
   - The user can tap Generate again instead of restarting the entire form.

2. **No dead-end cancellation screens**
   - Cancelled and expired generator sessions now show the main menu immediately.
   - `/cancel` and the global error message also show the main menu.

3. **Cleaner topic input**
   - Extra spaces and line breaks are normalized before a topic is saved or displayed.

4. **Owner navigation preserved**
   - Returning to Account after feedback keeps the owner-only Admin button visible.

5. **Correct daily reporting timezone**
   - Admin “today” usage and payment metrics now use the configured TeacherOS timezone, which defaults to Asia/Tehran.

6. **Safer payment-server restarts**
   - The local callback server reuses its port cleanly after a restart.
   - Port conflicts now produce a clear error with the exact remedy.

7. **Reliable dependency installation**
   - `requirements.txt` is now standard UTF-8 instead of UTF-16.

8. **Stronger project check**
   - `backend/check_project.py` now checks Python syntax, requirements encoding, required packages, callback payload lengths, the website Telegram link, environment settings, prompts, payments, and the database.

9. **Beta documentation corrected**
   - Day 28 instructions now match the fast one-tap feedback flow.

## Verification command

```bash
python backend/check_project.py
```

The final line should be:

```text
✅ Day 29 stability check passed
```

## Automated acceptance gate

The offline Day 29 gate checks every stability contract without requiring Telegram,
OpenRouter, or a payment provider:

```bash
python backend/day29_acceptance_check.py
```

It writes `outputs/day29/acceptance_report.json` and must print `DAY 29 ACCEPTANCE: PASS`.
The full regression suite includes the same gate and currently runs 281 tests.
